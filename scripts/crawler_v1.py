from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from scripts.convert_raw_documents import (
    light_clean_text,
    map_source_type,
    normalize_tags as normalize_document_tags,
    normalize_target_group,
    sha256_text,
    source_reliability,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ==============================================================================
# COMMON UTILITIES & DOCUMENT CONTRACT
# ==============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]
CRAWLER_NAME = "scripts/crawler_v1.py"

DOCUMENT_KEYS = [
    "doc_id",
    "schema_version",
    "target_group",
    "target_groups",
    "source_url",
    "source_type",
    "source_name",
    "title",
    "language",
    "clean_text",
    "content_hash",
    "published_at",
    "retrieved_at",
    "source_reliability",
    "tlp",
    "tags",
    "metadata",
]

ALLOWED_SOURCE_TYPES = {
    "security_report",
    "vendor_report",
    "knowledge_base",
    "government_notice",
    "news",
    "social_forum",
    "blog",
    "other",
}


def project_root() -> Path:
    return REPO_ROOT


def data_root() -> Path:
    return Path(os.getenv("CRAWLER_DATA_ROOT", str(REPO_ROOT / "data")))


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip().lower()).strip("._-")
    return slug or "keyword"


def output_dir_for(target_group: str) -> Path:
    return data_root() / "cleaned" / safe_slug(target_group)


SOURCE_NAMES = ("qianxin", "thehackernews", "unit42", "freebuf")
SOURCE_MASK = (1 << len(SOURCE_NAMES)) - 1


def sources_from_mask(source_mask: int) -> List[str]:
    if source_mask <= 0:
        raise ValueError("source mask must be greater than zero")
    if source_mask & ~SOURCE_MASK:
        raise ValueError(f"source mask exceeds {len(SOURCE_NAMES)} bits")
    return [
        source_name
        for index, source_name in enumerate(SOURCE_NAMES)
        if source_mask & (1 << index)
    ]


def next_doc_number(output_dir: Path, target_group: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{safe_slug(target_group)}_"
    max_number = 0
    for path in output_dir.glob(f"{prefix}[0-9][0-9][0-9].json"):
        match = re.fullmatch(rf"{re.escape(prefix)}(\d{{3}})\.json", path.name)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max_number + 1


def existing_source_urls(output_dir: Path) -> set:
    urls = set()
    if not output_dir.exists():
        return urls
    for path in output_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            url = data.get("source_url")
            if isinstance(url, str) and url:
                urls.add(url)
        except Exception:
            continue
    return urls


def normalize_tags(tags: Optional[Iterable[object]]) -> List[str]:
    if not tags:
        return []
    result = []
    seen = set()
    for tag in tags:
        text = str(tag).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_beautiful_soup():
    from bs4 import BeautifulSoup

    return BeautifulSoup


def get_requests_module():
    import requests

    return requests


def get_playwright_runtime():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    return async_playwright, Stealth


def build_contract_record(
    *,
    doc_id: str,
    target_group: str,
    source_url: str,
    source_type: str,
    source_name: str,
    title: str,
    language: str,
    raw_text: str,
    published_date: str = "",
    crawl_time: Optional[str] = None,
    tags: Optional[Iterable[object]] = None,
) -> dict:
    if language not in {"zh", "en"}:
        raise ValueError(f"Invalid language: {language}")
    clean_text = light_clean_text(raw_text)
    standard_target_group = normalize_target_group(target_group)
    standard_source_name = source_name.strip()
    standard_source_type = map_source_type(source_type, standard_source_name)
    document_tags = normalize_document_tags(tags)
    if standard_source_type not in document_tags:
        document_tags.append(standard_source_type)

    record = {
        "doc_id": safe_slug(doc_id),
        "schema_version": "1.0",
        "target_group": standard_target_group,
        "target_groups": [standard_target_group],
        "source_url": source_url or "",
        "source_type": standard_source_type,
        "source_name": standard_source_name,
        "title": title or "",
        "language": language,
        "clean_text": clean_text,
        "content_hash": sha256_text(clean_text),
        "published_at": published_date or None,
        "retrieved_at": crawl_time or utc_now(),
        "source_reliability": source_reliability(standard_source_name),
        "tlp": "TLP:CLEAR",
        "tags": document_tags,
        "metadata": {
            "collector": "data",
            "crawler": CRAWLER_NAME,
            "legacy_source_type": source_type,
            "cleaning": "crawler_selector_plus_light_format_cleaning",
        },
    }
    return {key: record[key] for key in DOCUMENT_KEYS}


def write_contract_record(output_dir: Path, target_group: str, doc_number: int, record: dict) -> Path:
    doc_id = f"{safe_slug(target_group)}_{doc_number:03d}"
    record["doc_id"] = doc_id
    standard_target_group = normalize_target_group(target_group)
    record["target_group"] = standard_target_group
    record["target_groups"] = [standard_target_group]
    file_path = output_dir / f"{doc_id}.json"
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return file_path


def validate_contract_record(record: dict) -> None:
    if list(record.keys()) != DOCUMENT_KEYS:
        raise ValueError(f"Record keys do not match contract: {list(record.keys())}")
    if not record["doc_id"]:
        raise ValueError("doc_id is empty")
    if not record["target_group"]:
        raise ValueError("target_group is empty")
    if not record["target_groups"]:
        raise ValueError("target_groups is empty")
    if not record["source_url"]:
        raise ValueError("source_url is empty")
    if record["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {record['source_type']}")
    if not record["source_name"]:
        raise ValueError("source_name is empty")
    if not record["title"]:
        raise ValueError("title is empty")
    if record["language"] not in {"zh", "en"}:
        raise ValueError(f"Invalid language: {record['language']}")
    if not record["clean_text"]:
        raise ValueError("clean_text is empty")
    if not str(record["content_hash"]).startswith("sha256:"):
        raise ValueError("content_hash must start with sha256:")
    if record["source_reliability"] not in {"A", "B", "C", "D", "unknown"}:
        raise ValueError(f"Invalid source_reliability: {record['source_reliability']}")
    if record["tlp"] not in {"TLP:CLEAR", "TLP:GREEN", "TLP:AMBER", "TLP:RED"}:
        raise ValueError(f"Invalid tlp: {record['tlp']}")
    if not isinstance(record["tags"], list):
        raise ValueError("tags must be a list")
    if not isinstance(record["metadata"], dict):
        raise ValueError("metadata must be an object")


# ==============================================================================
# CRAWLER 1: QIANXIN TI (Synchronous)
# ==============================================================================

class QianxinCrawler:
    BASE_URL = "https://ti.qianxin.com"
    BLOG_URL = f"{BASE_URL}/blog"
    TIMEOUT = 30
    DELAY_MIN = 1.5
    DELAY_MAX = 4.0
    HEADERS = {
        "User-Agent": "Mozilla/5.0 Chrome/120",
        "Accept": "text/html",
        "Accept-Language": "zh-CN",
    }

    @classmethod
    def fetch_text(cls, url: str, retries: int = 3) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                req = Request(url, headers=cls.HEADERS)
                with urlopen(req, timeout=cls.TIMEOUT) as response:
                    return response.read().decode("utf-8", "replace")
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < retries:
                    sleep_for = min(2 * attempt, 6)
                    log.warning("Fetch failed (%s), retrying in %ss: %s", exc, sleep_for, url)
                    time.sleep(sleep_for)
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    @staticmethod
    def clean_text(text: str) -> str:
        text = text.replace(" ", " ").replace(" ", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def parse_author_line(cls, text: str) -> Tuple[str, str, str]:
        text = cls.clean_text(text)
        match = re.match(r"(?P<date>\d{4}-\d{2}-\d{2})\s+By\s+(?P<author>.*?)\s*\|\s*(?P<category>.+)", text)
        if not match:
            return "", "", ""
        return match.group("date"), match.group("author").strip(), match.group("category").strip()

    @staticmethod
    def extract_nuxt_script(html: str) -> str:
        match = re.search(r"<script>\s*window\.__NUXT__=(.*?)</script>", html, re.S)
        return match.group(1) if match else ""

    @classmethod
    def extract_article_urls_from_nuxt(cls, html: str) -> List[str]:
        script = cls.extract_nuxt_script(html)
        if not script:
            return []
        urls: List[str] = []
        pattern = r"['\"](https://ti\.qianxin\.com/blog/articles/[^'\"),<>\\\s]+)['\"]"
        for match in re.finditer(pattern, script):
            url = match.group(1).rstrip("/")
            if url not in urls:
                urls.append(url)
        return urls

    @classmethod
    def parse_cards(cls, html: str) -> List[Dict[str, object]]:
        soup = get_beautiful_soup()(html, "html.parser")
        cards: List[Dict[str, object]] = []
        for card in soup.select(".art-container"):
            title_el = card.select_one(".title-home")
            if not title_el:
                continue
            title = cls.clean_text(title_el.get_text(" ", strip=True))
            if not title:
                continue
            author_el = card.select_one(".author")
            publish_date, author, category = cls.parse_author_line(author_el.get_text(" ", strip=True) if author_el else "")
            abstract_el = card.select_one(".brief")
            tags = []
            for tag_el in card.select(".s-tag"):
                tag = cls.clean_text(tag_el.get_text(" ", strip=True))
                if tag and tag not in tags:
                    tags.append(tag)
            cards.append({
                "title": title,
                "author": author,
                "publish_date": publish_date,
                "category": category,
                "abstract": cls.clean_text(abstract_el.get_text("\n", strip=True)) if abstract_el else "",
                "tags": tags,
            })
        return cards

    @classmethod
    def total_pages_from_html(cls, html: str) -> int:
        script = cls.extract_nuxt_script(html)
        pages = [int(value) for value in re.findall(r"pageTotal:(\d+)", script)]
        return max(pages) if pages else 1

    @classmethod
    def extract_detail(cls, html: str, article_url: str) -> Dict[str, object]:
        soup = get_beautiful_soup()(html, "html.parser")
        title_el = soup.select_one(".article-page .title-detail") or soup.select_one(".title-detail")
        body_el = soup.select_one(".article-page .main-body") or soup.select_one(".main-body")
        author_el = soup.select_one(".article-page .page-header .text-grey-12")

        title = cls.clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
        raw_text = cls.clean_text(body_el.get_text("\n", strip=True)) if body_el else ""
        _, author, category = cls.parse_author_line(author_el.get_text(" ", strip=True) if author_el else "")

        tags = []
        for tag_el in soup.select(".article-page .s-tag, .s-tags .s-tag"):
            tag = cls.clean_text(tag_el.get_text(" ", strip=True))
            if tag and tag not in tags:
                tags.append(tag)

        publish_date = ""
        publish_match = re.search(r"publish_time=['\"](\d{4}-\d{2}-\d{2})", html)
        if publish_match:
            publish_date = publish_match.group(1)

        if not title or not raw_text:
            raise ValueError(f"Could not extract title/content from {article_url}")

        return {
            "title": title,
            "raw_text": raw_text,
            "author": author,
            "category": category,
            "publish_date": publish_date,
            "tags": tags,
        }

    @classmethod
    def urls_match_card_titles(cls, urls: Iterable[str], cards: List[Dict[str, object]]) -> Dict[str, str]:
        pending = {str(card["title"]): "" for card in cards}
        for url in urls:
            try:
                html = cls.fetch_text(url)
                title = cls.extract_detail(html, url)["title"]
            except Exception as exc:
                log.warning("Could not verify candidate URL %s: %s", url, exc)
                continue
            if title in pending and not pending[title]:
                pending[title] = url.rstrip("/")
            time.sleep(random.uniform(0.3, 0.8))
        return {title: url for title, url in pending.items() if url}

    @classmethod
    def collect_articles(cls, keyword: str) -> List[Dict[str, object]]:
        encoded_keyword = quote(keyword.strip(), safe="")
        first_url = f"{cls.BLOG_URL}/tag/{encoded_keyword}/"
        log.info("Loading Qianxin TI tag page: %s", first_url)
        try:
            first_html = cls.fetch_text(first_url)
        except Exception:
            return []

        total_pages = cls.total_pages_from_html(first_html)
        log.info("Detected %s Qianxin TI tag result page(s)", total_pages)

        all_cards: List[Dict[str, object]] = []
        all_candidate_urls: List[str] = []
        pages = [(1, first_html)]

        for page_num in range(2, total_pages + 1):
            for url in (f"{cls.BLOG_URL}/tag/{encoded_keyword}/{page_num}", f"{cls.BLOG_URL}/tag/{encoded_keyword}/{page_num}/"):
                try:
                    html = cls.fetch_text(url, retries=1)
                    if cls.parse_cards(html):
                        pages.append((page_num, html))
                        break
                except Exception:
                    continue

        for page_num, html in pages:
            cards = cls.parse_cards(html)
            urls = cls.extract_article_urls_from_nuxt(html)
            log.info("Qianxin TI Page %s: found %s card(s), %s candidate article URL(s)", page_num, len(cards), len(urls))
            all_cards.extend(cards)
            for url in urls:
                if url not in all_candidate_urls:
                    all_candidate_urls.append(url)

        title_to_url = cls.urls_match_card_titles(all_candidate_urls, all_cards)
        articles: List[Dict[str, object]] = []
        seen_titles = set()
        for card in all_cards:
            title = str(card["title"])
            if title in seen_titles:
                continue
            seen_titles.add(title)
            item = dict(card)
            item["url"] = title_to_url.get(title, "")
            articles.append(item)

        log.info("Collected %s Qianxin TI item(s), %s with crawlable HTML detail URLs", len(articles), sum(1 for item in articles if item.get("url")))
        return articles

    @classmethod
    def build_output(cls, article_url: str, detail: Dict[str, object], fallback: Dict[str, object], target_group: str, doc_number: int) -> Dict[str, object]:
        tags = list(detail.get("tags") or fallback.get("tags") or [])
        category = detail.get("category") or fallback.get("category")
        if category and category not in tags:
            tags.append(str(category))
        raw_text = str(detail["raw_text"])
        return build_contract_record(
            doc_id=f"{target_group}_{doc_number:03d}",
            target_group=target_group,
            source_url=article_url,
            source_type="threat_report",
            source_name="奇安信威胁情报中心",
            title=str(detail.get("title") or fallback.get("title") or ""),
            language="zh",
            raw_text=raw_text,
            published_date=str(detail.get("publish_date") or fallback.get("publish_date") or ""),
            tags=tags,
        )

    @classmethod
    def run(cls, keyword: str, limit: Optional[int] = None) -> None:
        target_group = safe_slug(keyword)
        output_dir = output_dir_for(target_group)
        failed_log = data_root() / f"failed_qianxin_ti_{target_group}.log"
        output_dir.mkdir(parents=True, exist_ok=True)
        seen_urls = existing_source_urls(output_dir)
        next_number = next_doc_number(output_dir, target_group)

        articles = cls.collect_articles(keyword)
        success_count = 0
        skip_count = 0
        fail_count = 0
        for index, article in enumerate(articles, 1):
            title = str(article.get("title", ""))
            article_url = str(article.get("url") or "")
            log.info("[Qianxin %s/%s] Processing: %s", index, len(articles), title[:80])
            try:
                if not article_url:
                    raise ValueError("No crawlable HTML detail URL found; likely a PDF-only item")
                if article_url in seen_urls:
                    skip_count += 1
                    log.info("  Skipped existing URL")
                    continue
                time.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))
                detail = cls.extract_detail(cls.fetch_text(article_url), article_url)
                output = cls.build_output(article_url, detail, article, target_group, next_number)
                validate_contract_record(output)
                path = write_contract_record(output_dir, target_group, next_number, output)
                next_number += 1
                seen_urls.add(article_url)
                success_count += 1
                log.info("  Saved: %s", path.name)
                if limit is not None and success_count >= limit:
                    break
            except Exception as exc:
                fail_count += 1
                log.error("  Failed: %s", exc)
                with failed_log.open("a", encoding="utf-8") as handle:
                    handle.write(f"{datetime.now().isoformat()} | {title} | {article_url or '-'} | {exc}\n")

        log.info("Qianxin TI Done! Success: %s, Skipped: %s, Failed: %s", success_count, skip_count, fail_count)


# ==============================================================================
# CRAWLER 2: THE HACKER NEWS (Synchronous)
# ==============================================================================

class TheHackerNewsCrawler:
    DEFAULT_LABEL_URL = "https://thehackernews.com/search/label/APT28"
    DELAY_MIN = 1.5
    DELAY_MAX = 3.5
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"[-]", " ", text)
        text = re.sub(r"\xa0", " ", text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def fetch_html(cls, session: requests.Session, url: str, retries: int = 3) -> str:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(url, headers=cls.HEADERS, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as exc:
                last_error = exc
                log.warning("Fetch failed (%s/%s): %s -> %s", attempt, retries, url, exc)
                time.sleep(2 * attempt)
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    @classmethod
    def parse_label_page(cls, html: str):
        soup = get_beautiful_soup()(html, "lxml")
        articles = []
        seen = set()

        cards = soup.select(".body-post")
        if not cards:
            cards = soup.select("a.story-link")

        for card in cards:
            link = card if getattr(card, "name", None) == "a" else card.select_one("a.story-link[href], a[href*='.html']")
            if not link:
                continue
            href = link.get("href", "").strip()
            if not re.match(r"^https://thehackernews\.com/\d{4}/\d{2}/[^/#?]+\.html$", href):
                continue
            if href in seen:
                continue
            seen.add(href)

            title_el = card.select_one(".home-title") or link
            excerpt_el = card.select_one(".home-desc")
            date_el = card.select_one(".h-datetime")
            label_el = card.select_one(".item-label")

            articles.append({
                "url": href,
                "title": cls.clean_text(title_el.get_text(" ", strip=True) if title_el else link.get_text(" ", strip=True)),
                "excerpt": cls.clean_text(excerpt_el.get_text(" ", strip=True) if excerpt_el else ""),
                "date_text": cls.clean_text(date_el.get_text(" ", strip=True) if date_el else ""),
                "label_text": cls.clean_text(label_el.get_text(" ", strip=True) if label_el else ""),
            })

        pager = soup.select_one("#Blog1_blog-pager-older-link[href], #blog-pager-older-link[href], .blog-pager a.blog-pager-older-link[href]")
        next_url = pager.get("href", "").strip() if pager else ""
        return articles, next_url

    @classmethod
    def parse_date(cls, date_text: str) -> str:
        date_text = cls.clean_text(date_text)
        match = re.search(r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", date_text)
        if not match:
            return ""
        try:
            return datetime.strptime(match.group(1), "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return ""

    @classmethod
    def parse_article_page(cls, html: str, fallback_title: str, fallback_date: str):
        soup = get_beautiful_soup()(html, "lxml")

        title_el = soup.select_one("h1.story-title, .story-title, h1")
        title = cls.clean_text(title_el.get_text(" ", strip=True) if title_el else fallback_title)

        body_el = soup.select_one("#articlebody, .articlebody.clear, .articlebody")
        raw_text = cls.clean_text(body_el.get_text("\n", strip=True) if body_el else "")

        date = fallback_date
        meta_text = cls.clean_text(soup.select_one(".postmeta").get_text(" ", strip=True)) if soup.select_one(".postmeta") else ""
        parsed_meta_date = cls.parse_date(meta_text)
        if parsed_meta_date:
            date = parsed_meta_date

        tags = []
        for tag_el in soup.select(".tags a, .postmeta .p-tags a, a[rel='tag']"):
            tag = cls.clean_text(tag_el.get_text(" ", strip=True))
            if tag and tag not in tags and len(tag) < 50:
                tags.append(tag)

        if not tags:
            category_el = soup.select_one(".postmeta .p-tags, .p-tags")
            category = cls.clean_text(category_el.get_text(" ", strip=True) if category_el else "")
            if category:
                tags.append(category)

        return {
            "title": title,
            "raw_text": raw_text,
            "publish_date": date,
            "tags": tags,
        }

    @staticmethod
    def build_output(article_url: str, detail: dict, target_group: str, doc_number: int):
        return build_contract_record(
            doc_id=f"{target_group}_{doc_number:03d}",
            target_group=target_group,
            source_url=article_url,
            source_type="news_article",
            source_name="The Hacker News",
            title=detail["title"],
            language="en",
            raw_text=detail["raw_text"],
            published_date=detail["publish_date"],
            tags=detail["tags"],
        )

    @classmethod
    def collect_all_articles(cls, session: requests.Session, start_url: str, limit: Optional[int] = None):
        all_articles = []
        seen_urls = set()
        seen_pages = set()
        page_url = start_url
        page_num = 1

        while page_url and page_url not in seen_pages:
            seen_pages.add(page_url)
            log.info("THN Fetching label page %s: %s", page_num, page_url)
            try:
                html = cls.fetch_html(session, page_url)
            except Exception:
                break
            articles, next_url = cls.parse_label_page(html)
            log.info("  Found %s article cards", len(articles))

            if not articles:
                break

            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    all_articles.append(article)
                    if limit and len(all_articles) >= limit:
                        break

            if limit and len(all_articles) >= limit:
                break

            page_url = next_url
            page_num += 1
            if page_url:
                time.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))

        log.info("Collected %s THN unique article URLs", len(all_articles))
        return all_articles

    @classmethod
    def run(cls, keyword: str, limit: Optional[int] = None):
        target_group = safe_slug(keyword)
        output_dir = output_dir_for(target_group)
        failed_log = data_root() / f"failed_thehackernews_{target_group}.log"
        output_dir.mkdir(parents=True, exist_ok=True)
        seen_urls = existing_source_urls(output_dir)
        next_number = next_doc_number(output_dir, target_group)

        label_url = f"https://thehackernews.com/search/label/{quote(keyword)}"

        session = get_requests_module().Session()
        articles = cls.collect_all_articles(session, label_url, None)

        success_count = 0
        skip_count = 0
        fail_count = 0
        for idx, article in enumerate(articles, start=1):
            url = article["url"]
            title = article.get("title", "")
            log.info("[THN %s/%s] Fetching: %s... (%s)", idx, len(articles), title[:70], url)
            if url in seen_urls:
                skip_count += 1
                log.info("  Skipped existing URL")
                continue
            try:
                time.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))
                html = cls.fetch_html(session, url)
                detail = cls.parse_article_page(html, title, cls.parse_date(article.get("date_text", "")))
                if not detail["raw_text"]:
                    raise ValueError("Empty article content")

                output = cls.build_output(url, detail, target_group, next_number)
                validate_contract_record(output)
                path = write_contract_record(output_dir, target_group, next_number, output)
                next_number += 1
                seen_urls.add(url)
                success_count += 1
                log.info("  Saved: %s", path.name)
                if limit is not None and success_count >= limit:
                    break
            except Exception as exc:
                fail_count += 1
                log.error("  Failed: %s", exc)
                with open(failed_log, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().isoformat()} | {url} | {exc}\n")

        log.info("THN Done! Success: %s, Skipped: %s, Failed: %s", success_count, skip_count, fail_count)


# ==============================================================================
# CRAWLER 3: PALO ALTO UNIT 42 (Asynchronous)
# ==============================================================================

class Unit42Crawler:
    SEARCH_API = "https://paloaltonetworksintranet.org.coveo.com/rest/search/v2"
    BASE_URL = "https://www.paloaltonetworks.com"
    SOURCE_NAME = "Palo Alto Unit 42"
    SOURCE_TYPE = "threat_report"
    LANGUAGE = "en"
    PAGE_SIZE = 20
    DELAY_MIN = 2
    DELAY_MAX = 5

    @staticmethod
    async def collect_articles(page, keyword: str):
        all_articles = []
        log.info("Loading Unit42 search page for '%s' to extract Coveo token...", keyword)
        await page.goto(
            f"{Unit42Crawler.BASE_URL}/search/unit42search#q={keyword}",
            wait_until="networkidle",
            timeout=30000,
        )
        await page.wait_for_timeout(3000)

        token_resp = await page.evaluate(
            """async () => {
                try {
                    const r = await fetch('/apps/pan/public/coveosearch.getaccesstoken.json');
                    return await r.json();
                } catch (e) {
                    return null;
                }
            }"""
        )
        if not token_resp or not token_resp.get("token"):
            raise RuntimeError("Failed to get Coveo access token")
        access_token = token_resp["token"]
        log.info("Got Coveo access token: %s...", access_token[:10])

        async def fetch_page(first_result: int):
            req_body = (
                f"q={keyword}&searchHub=Unit42%20Site%20Search&locale=en"
                f"&pipeline=WWW%20Unit42%20Site%20Search&firstResult={first_result}&numberOfResults={Unit42Crawler.PAGE_SIZE}"
                f"&sortCriteria=relevancy"
            )
            return await page.evaluate(
                f"""async (args) => {{
                    try {{
                        const r = await fetch('{Unit42Crawler.SEARCH_API}?organizationId=paloaltonetworksintranet', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'Authorization': `Bearer ${{args.token}}`
                            }},
                            body: args.body
                        }});
                        return await r.json();
                    }} catch (e) {{
                        return null;
                    }}
                }}""",
                {"token": access_token, "body": req_body},
            )

        log.info("Fetching Unit42 page 1 via Coveo API...")
        resp = await fetch_page(0)
        if not resp or "results" not in resp:
            raise RuntimeError("Failed to get Coveo search results")

        total = int(resp.get("totalCount") or 0)
        results = resp.get("results", []) or []
        all_articles.extend(results)
        log.info("Total Unit42 articles: %s, got %s from page 1", total, len(results))

        total_pages = math.ceil(total / Unit42Crawler.PAGE_SIZE)
        for page_num in range(2, total_pages + 1):
            await asyncio.sleep(random.uniform(Unit42Crawler.DELAY_MIN, Unit42Crawler.DELAY_MAX))
            first_result = (page_num - 1) * Unit42Crawler.PAGE_SIZE
            log.info("Fetching Unit42 page %s/%s via Coveo API...", page_num, total_pages)
            resp = await fetch_page(first_result)
            page_results = resp.get("results", []) if resp else []
            all_articles.extend(page_results)
            log.info("  Got %s articles", len(page_results))

        log.info("Collected %s Unit42 result(s)", len(all_articles))
        return all_articles

    @staticmethod
    def clean_html(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    async def extract_article_detail(page, article_url: str):
        await page.goto(article_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        raw_text = ""
        content_selectors = [
            "article",
            ".entry-content",
            ".post-content",
            "[itemprop='articleBody']",
            ".blog-content",
            ".blog-post-content",
            ".text-content",
            "main",
            "body",
        ]
        for selector in content_selectors:
            content_el = await page.query_selector(selector)
            if content_el:
                raw_text = (await content_el.inner_text()).strip()
                if len(raw_text) > 100:
                    break

        tags = []
        tag_els = await page.query_selector_all(".tags a, [class*='tag'] a, a[rel='tag']")
        for tag_el in tag_els:
            tag = (await tag_el.inner_text()).strip()
            if tag and tag.lower() not in {"tags", "tag"} and len(tag) < 50 and tag not in tags:
                tags.append(tag)
        return raw_text, tags

    @staticmethod
    def published_date_from_meta(article_meta: dict) -> str:
        raw = article_meta.get("raw", {}) or {}
        date_timestamp = raw.get("date")
        if not date_timestamp:
            return ""
        try:
            ts = float(date_timestamp)
            if ts > 10000000000:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""

    @classmethod
    async def run(cls, keyword: str, limit: Optional[int] = None):
        target_group = safe_slug(keyword)
        output_dir = output_dir_for(target_group)
        output_dir.mkdir(parents=True, exist_ok=True)
        failed_log = output_dir.parent.parent / f"failed_unit42_{target_group}.log"
        seen_urls = existing_source_urls(output_dir)
        next_number = next_doc_number(output_dir, target_group)

        async_playwright, Stealth = get_playwright_runtime()
        stealth = Stealth()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            await stealth.apply_stealth_async(context)
            page = await context.new_page()
            articles = await cls.collect_articles(page, keyword)
            success_count = 0
            skip_count = 0
            fail_count = 0
            for index, article in enumerate(articles, 1):
                article_url = article.get("uri", "") or article.get("clickUri", "")
                if not article_url:
                    continue
                title = cls.clean_html(article.get("title", ""))
                log.info("[Unit42 %s/%s] Fetching: %s... (%s)", index, len(articles), title[:70], article_url)
                if article_url in seen_urls:
                    skip_count += 1
                    log.info("  Skipped existing URL")
                    continue
                try:
                    await asyncio.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))
                    raw_text, tags = await cls.extract_article_detail(page, article_url)
                    if not raw_text:
                        raise ValueError("Empty article content")
                    record = build_contract_record(
                        doc_id=f"{target_group}_{next_number:03d}",
                        target_group=target_group,
                        source_url=article_url,
                        source_type=cls.SOURCE_TYPE,
                        source_name=cls.SOURCE_NAME,
                        title=title,
                        language=cls.LANGUAGE,
                        raw_text=raw_text,
                        published_date=cls.published_date_from_meta(article),
                        tags=tags,
                    )
                    validate_contract_record(record)
                    path = write_contract_record(output_dir, target_group, next_number, record)
                    next_number += 1
                    seen_urls.add(article_url)
                    success_count += 1
                    log.info("  Saved: %s", path.name)
                    if limit is not None and success_count >= limit:
                        break
                except Exception as exc:
                    fail_count += 1
                    log.error("  Failed: %s", exc)
                    with failed_log.open("a", encoding="utf-8") as handle:
                        handle.write(f"{datetime.now().isoformat()} | {article_url} | {exc}\n")
            await browser.close()

        log.info("Unit42 Done! Success: %s, Skipped: %s, Failed: %s", success_count, skip_count, fail_count)


# ==============================================================================
# CRAWLER 4: FREEBUF (Asynchronous)
# ==============================================================================

class FreebufCrawler:
    SEARCH_API = "https://www.freebuf.com/fapi/frontend/search/article"
    BASE_URL = "https://www.freebuf.com"
    SOURCE_NAME = "FreeBuf"
    SOURCE_TYPE = "news_article"
    LANGUAGE = "zh"
    PAGE_SIZE = 20
    DELAY_MIN = 2
    DELAY_MAX = 5

    @staticmethod
    def clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    async def collect_articles(cls, page, keyword: str):
        all_articles = []
        first_response = None
        encoded_keyword = quote(keyword, safe="")

        async def capture_api(response):
            nonlocal first_response
            if "fapi/frontend/search/article" in response.url and first_response is None:
                try:
                    first_response = await response.json()
                except Exception:
                    pass

        page.on("response", capture_api)
        log.info("Loading FreeBuf search page for '%s'...", keyword)
        await page.goto(
            f"{cls.BASE_URL}/search?search={encoded_keyword}&activeType=1&society_id=0&society_name=",
            wait_until="networkidle",
            timeout=30000,
        )
        await page.wait_for_timeout(5000)
        page.remove_listener("response", capture_api)

        if not first_response or "data" not in first_response:
            raise RuntimeError("Failed to capture FreeBuf search API response")

        total = int(first_response["data"].get("total_count") or 0)
        data_list = first_response["data"].get("data_list", []) or []
        all_articles.extend(data_list)
        log.info("Total Freebuf articles: %s, got %s from page 1", total, len(data_list))

        total_pages = math.ceil(total / cls.PAGE_SIZE)
        for pg in range(2, total_pages + 1):
            await asyncio.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))
            api_url = f"{cls.SEARCH_API}?content={encoded_keyword}&articleType=&year=&time=0&page={pg}&limit={cls.PAGE_SIZE}"
            log.info("Fetching Freebuf page %s/%s via API...", pg, total_pages)
            resp = await page.evaluate(
                """async (apiUrl) => {
                    const r = await fetch(apiUrl);
                    return await r.json();
                }""",
                api_url,
            )
            page_articles = resp.get("data", {}).get("data_list", []) if resp else []
            all_articles.extend(page_articles)
            log.info("  Got %s articles from page %s", len(page_articles), pg)

        log.info("Collected %s FreeBuf articles", len(all_articles))
        return all_articles

    @classmethod
    async def extract_article_detail(cls, page, article_url: str):
        await page.goto(article_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        content_el = await page.query_selector(".content-detail")
        raw_text = (await content_el.inner_text()).strip() if content_el else ""

        tags = []
        tag_els = await page.query_selector_all(".article-tags a, .article-tags span, .tag-box a, .tag-list a")
        for tag_el in tag_els:
            tag = (await tag_el.inner_text()).strip()
            if tag and tag not in {"标签"} and len(tag) < 30 and tag not in tags:
                tags.append(tag)
        return raw_text, tags

    @staticmethod
    def published_date_from_meta(article_meta: dict) -> str:
        published = article_meta.get("post_date", "") or ""
        return published.split(" ", 1)[0] if " " in published else published

    @classmethod
    async def run(cls, keyword: str, limit: Optional[int] = None):
        target_group = safe_slug(keyword)
        output_dir = output_dir_for(target_group)
        output_dir.mkdir(parents=True, exist_ok=True)
        failed_log = output_dir.parent.parent / f"failed_freebuf_{target_group}.log"
        seen_urls = existing_source_urls(output_dir)
        next_number = next_doc_number(output_dir, target_group)

        async_playwright, Stealth = get_playwright_runtime()
        stealth = Stealth()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            await stealth.apply_stealth_async(context)
            page = await context.new_page()
            articles = await cls.collect_articles(page, keyword)
            success_count = 0
            skip_count = 0
            fail_count = 0
            for index, article in enumerate(articles, 1):
                article_url = cls.BASE_URL + article.get("url", "")
                title = cls.clean_html(article.get("post_title", ""))
                log.info("[Freebuf %s/%s] Fetching: %s... (%s)", index, len(articles), title[:70], article_url)
                if article_url in seen_urls:
                    skip_count += 1
                    log.info("  Skipped existing URL")
                    continue
                try:
                    await asyncio.sleep(random.uniform(cls.DELAY_MIN, cls.DELAY_MAX))
                    raw_text, tags = await cls.extract_article_detail(page, article_url)
                    if not raw_text:
                        raise ValueError("Empty article content")
                    if not tags and article.get("category"):
                        tags = [article["category"]]
                    record = build_contract_record(
                        doc_id=f"{target_group}_{next_number:03d}",
                        target_group=target_group,
                        source_url=article_url,
                        source_type=cls.SOURCE_TYPE,
                        source_name=cls.SOURCE_NAME,
                        title=title,
                        language=cls.LANGUAGE,
                        raw_text=raw_text,
                        published_date=cls.published_date_from_meta(article),
                        tags=tags,
                    )
                    validate_contract_record(record)
                    path = write_contract_record(output_dir, target_group, next_number, record)
                    next_number += 1
                    seen_urls.add(article_url)
                    success_count += 1
                    log.info("  Saved: %s", path.name)
                    if limit is not None and success_count >= limit:
                        break
                except Exception as exc:
                    fail_count += 1
                    log.error("  Failed: %s", exc)
                    with failed_log.open("a", encoding="utf-8") as handle:
                        handle.write(f"{datetime.now().isoformat()} | {article_url} | {exc}\n")
            await browser.close()

        log.info("Freebuf Done! Success: %s, Skipped: %s, Failed: %s", success_count, skip_count, fail_count)


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Unified Web Crawler for Threat Intel Sources")
    parser.add_argument("--keyword", required=True, help="Keyword to search (e.g., APT28, Kimsuky)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of items to crawl per source")
    parser.add_argument("--sources", type=int, required=True, help="Local source bitmask")

    args = parser.parse_args()
    keyword = args.keyword
    limit = args.limit
    sources = set(sources_from_mask(args.sources))

    log.info(f"Starting unified crawl for '{keyword}' with limit {limit}")
    failed = False

    # Synchronous crawlers
    if "qianxin" in sources:
        log.info("--- Running Qianxin TI Crawler ---")
        try:
            QianxinCrawler.run(keyword, limit)
        except Exception as e:
            failed = True
            log.exception(f"Qianxin TI crawler failed: {e}")

    if "thehackernews" in sources:
        log.info("--- Running The Hacker News Crawler ---")
        try:
            TheHackerNewsCrawler.run(keyword, limit)
        except Exception as e:
            failed = True
            log.exception(f"The Hacker News crawler failed: {e}")

    # Asynchronous crawlers
    if "unit42" in sources:
        log.info("--- Running Unit42 Crawler ---")
        try:
            await Unit42Crawler.run(keyword, limit)
        except Exception as e:
            failed = True
            log.exception(f"Unit42 crawler failed: {e}")

    if "freebuf" in sources:
        log.info("--- Running Freebuf Crawler ---")
        try:
            await FreebufCrawler.run(keyword, limit)
        except Exception as e:
            failed = True
            log.exception(f"Freebuf crawler failed: {e}")

    log.info("--- All crawlers finished. ---")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
