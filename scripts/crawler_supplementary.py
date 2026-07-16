"""
补充数据爬虫 v1 - HTTP请求版本
处理可以直接HTTP请求的网站：Chainalysis、TRM Labs、Microsoft、SecureList

使用方式：
    python scripts/crawler_supplementary.py --source chainalysis --keyword Lazarus --limit 20
    python scripts/crawler_supplementary.py --source trmlabs --keyword Lazarus --limit 20
    python scripts/crawler_supplementary.py --source microsoft,securelist --keyword Lazarus --limit 20
    python scripts/crawler_supplementary.py --source all --keyword Lazarus --limit 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
CRAWLER_NAME = "scripts/crawler_supplementary.py"

DOCUMENT_KEYS = [
    "doc_id", "schema_version", "target_group", "target_groups",
    "source_url", "source_type", "source_name", "title",
    "language", "clean_text", "content_hash", "published_at",
    "retrieved_at", "source_reliability", "tlp", "tags", "metadata",
]

SOURCE_RELIABILITY_MAP = {
    "Chainalysis": "B",
    "TRM Labs": "B",
    "Microsoft": "B",
    "SecureList": "B",
}

MIN_CONTENT_LENGTH = 400

# 关键词别名映射
KEYWORD_ALIASES = {
    "kimsuky": ["Kimsuky", "APT43", "Velvet Chollima", "Emerald Sleet", "Thallium", "Springtail"],
    "apt28": ["APT28", "Fancy Bear", "Sofacy", "Sednit", "Pawn Storm", "Strontium", "Forest Blizzard"],
    "lazarus": ["Lazarus", "Hidden Cobra", "APT38", "Bluenoroff", "Andariel", "Zinc"],
}

# ==============================================================================
# 工具函数
# ==============================================================================

def safe_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip().lower()).strip("._-") or "unknown"

def output_dir_for(target_group: str) -> Path:
    return REPO_ROOT / "data" / "cleaned" / safe_slug(target_group)


SOURCE_NAMES = ("chainalysis", "trmlabs", "microsoft", "securelist")
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
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            url = data.get("source_url")
            if isinstance(url, str) and url:
                urls.add(url)
        except Exception:
            continue
    return urls

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

def light_clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def normalize_target_group(value: str) -> str:
    mapping = {
        "apt28": "APT28", "fancy bear": "APT28", "sofacy": "APT28",
        "lazarus": "Lazarus", "hidden cobra": "Lazarus", "apt38": "Lazarus",
        "bluenoroff": "Lazarus", "andariel": "Lazarus",
        "kimsuky": "Kimsuky", "apt43": "Kimsuky", "velvet chollima": "Kimsuky",
    }
    return mapping.get(value.lower(), value)

def get_keyword_aliases(keyword: str) -> List[str]:
    return KEYWORD_ALIASES.get(keyword.lower(), [keyword])

def fetch_url(url: str, timeout: int = 30, retries: int = 3) -> str:
    from urllib.request import Request, urlopen
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    last_error = None
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")

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
    tags: Optional[List[str]] = None,
) -> dict:
    clean_text = light_clean_text(raw_text)
    target_group = normalize_target_group(target_group)
    if not tags:
        tags = []
    return {
        "doc_id": safe_slug(doc_id),
        "schema_version": "1.0",
        "target_group": target_group,
        "target_groups": [target_group],
        "source_url": source_url,
        "source_type": source_type,
        "source_name": source_name,
        "title": title,
        "language": language,
        "clean_text": clean_text,
        "content_hash": sha256_text(clean_text),
        "published_at": published_date or None,
        "retrieved_at": utc_now(),
        "source_reliability": SOURCE_RELIABILITY_MAP.get(source_name, "B"),
        "tlp": "TLP:CLEAR",
        "tags": tags,
        "metadata": {
            "collector": "data",
            "crawler": CRAWLER_NAME,
            "cleaning": "light_format_cleaning",
        },
    }

def validate_contract_record(record: dict) -> None:
    if list(record.keys()) != DOCUMENT_KEYS:
        raise ValueError(f"Record keys mismatch: {list(record.keys())}")
    if not record["doc_id"]:
        raise ValueError("doc_id is empty")
    if not record["source_url"]:
        raise ValueError("source_url is empty")
    if not record["clean_text"]:
        raise ValueError("clean_text is empty")
    if len(record["clean_text"]) < MIN_CONTENT_LENGTH:
        raise ValueError(f"clean_text too short: {len(record['clean_text'])} chars")

def write_contract_record(output_dir: Path, target_group: str, doc_number: int, record: dict) -> Path:
    doc_id = f"{safe_slug(target_group)}_{doc_number:03d}"
    record["doc_id"] = doc_id
    file_path = output_dir / f"{doc_id}.json"
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return file_path

# ==============================================================================
# 通用爬虫基类
# ==============================================================================

class GenericCrawler:
    """通用爬虫基类 - 使用HTTP请求"""
    
    def __init__(self, source_name: str, source_type: str, base_url: str = ""):
        self.source_name = source_name
        self.source_type = source_type
        self.base_url = base_url
    
    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索文章 - 子类可覆盖"""
        aliases = get_keyword_aliases(keyword)
        log.info(f"{self.source_name}: 搜索关键词 {aliases}")
        
        all_articles = []
        seen_urls = set()
        
        for alias in aliases:
            search_url = self.base_url.format(keyword=quote(alias))
            log.info(f"  搜索 '{alias}' at {search_url}")
            
            try:
                html = fetch_url(search_url)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                
                articles = self.extract_article_links(soup, search_url)
                for art in articles:
                    if art['url'] not in seen_urls:
                        seen_urls.add(art['url'])
                        all_articles.append(art)
                
                time.sleep(1)
            except Exception as e:
                log.warning(f"  搜索 '{alias}' 失败: {e}")
        
        log.info(f"{self.source_name}: 找到 {len(all_articles)} 篇文章")
        return all_articles[:limit]
    
    def extract_article_links(self, soup, base_url: str) -> List[Dict]:
        """提取文章链接 - 子类可覆盖"""
        articles = []
        seen = set()
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            if len(text) < 20:
                continue
            
            if not href.startswith('http'):
                href = urljoin(base_url, href)
            
            if href in seen:
                continue
            
            # 过滤掉导航链接
            if any(x in href.lower() for x in ['/tag/', '/category/', '/page/', '/author/']):
                continue
            
            seen.add(href)
            articles.append({"url": href, "title": text[:200], "date": ""})
        
        return articles

    def fetch_article(self, url: str) -> Dict:
        """获取文章全文，精确提取正文和发布日期"""
        html = fetch_url(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 提取正文
        content_el = soup.select_one(".new-rich-text, .main-post-section .w-richtext")
        if content_el:
            raw_text = content_el.get_text(separator="\n", strip=True)
        else:
            main_el = soup.select_one("main")
            if main_el:
                raw_text = main_el.get_text(separator="\n", strip=True)
            else:
                raw_text = soup.get_text(separator="\n", strip=True)

        # 提取发布日期（修正：取最后一个 .info-text.blue2）
        date_els = soup.select(".blog-post-info-div .info-text.blue2")
        if len(date_els) >= 2:
            date_el = date_els[-1]  # 最后一个通常是日期
        elif len(date_els) == 1:
            date_el = date_els[0]
        else:
            date_el = None
        published_date = date_el.get_text(strip=True) if date_el else ""

        return {
            "title": title,
            "raw_text": raw_text,
            "date": published_date,
            "tags": []  # 页面无显式标签
        }
    
    def run(self, keyword: str, limit: int = 20) -> List[Dict]:
        """运行爬虫"""
        target_group = normalize_target_group(keyword)
        output_dir = output_dir_for(target_group)
        output_dir.mkdir(parents=True, exist_ok=True)
        seen_urls = existing_source_urls(output_dir)
        next_number = next_doc_number(output_dir, target_group)
        
        articles = self.search(keyword, limit)
        
        success_count = 0
        for idx, article in enumerate(articles, 1):
            url = article["url"]
            if url in seen_urls:
                log.info(f"  [{idx}/{len(articles)}] 跳过(重复URL)")
                continue
            
            log.info(f"  [{idx}/{len(articles)}] 获取: {article['title'][:50]}...")
            
            try:
                time.sleep(random.uniform(2.0, 4.0))
                detail = self.fetch_article(url)
                
                if not detail["raw_text"] or len(detail["raw_text"]) < MIN_CONTENT_LENGTH:
                    log.warning(f"    跳过: 内容过短 ({len(detail['raw_text'])} chars)")
                    continue


                record = build_contract_record(
                    doc_id=f"{target_group}_{next_number:03d}",
                    target_group=target_group,
                    source_url=url,
                    source_type=self.source_type,
                    source_name=self.source_name,
                    title=detail["title"] or article.get("title", ""),
                    language="en",
                    raw_text=detail["raw_text"],
                    published_date=detail["date"] or article.get("date", ""),
                    tags=[keyword],
                )
                validate_contract_record(record)
                path = write_contract_record(output_dir, target_group, next_number, record)
                seen_urls.add(url)
                next_number += 1
                success_count += 1
                log.info(f"    保存: {path.name}")
            except Exception as e:
                log.error(f"    失败: {e}")
        
        log.info(f"{self.source_name} 完成! 成功: {success_count}/{len(articles)}")
        return []

# ==============================================================================
# Chainalysis 爬虫 - HTTP请求
# ==============================================================================

class ChainalysisCrawler(GenericCrawler):
    """Chainalysis爬虫 - 使用HTTP请求，增强字段提取"""
    SOURCE_NAME = "Chainalysis"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://www.chainalysis.com"

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE, f"{self.BASE_URL}/?s={{keyword}}")

    def extract_article_links(self, soup, base_url: str) -> List[Dict]:
        """提取Chainalysis文章链接（保持不变）"""
        articles = []
        seen = set()
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if '/blog/' not in href or href.endswith('/blog/') or href.endswith('/blog'):
                continue
            if len(text) < 20:
                continue
            if not href.startswith('http'):
                href = urljoin(self.BASE_URL, href)
            if href in seen:
                continue
            seen.add(href)
            articles.append({"url": href, "title": text[:200], "date": ""})
        return articles

    def fetch_article(self, url: str) -> Dict:
        """重写：提取标题、正文、发布日期、标签"""
        html = fetch_url(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title_el = soup.select_one("h1.h1-alt, h1.entry-title, h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 正文：优先使用 .post-content，若不存在则回退
        content_el = soup.select_one(".single-post__content .post-content")
        if not content_el:
            content_el = soup.select_one(".post-content")
        if content_el:
            # 移除干扰元素（如广告、脚本等）
            for tag in content_el.select("script, style, .related-posts, .post-content__tags, .heateor_sss_sharing_container"):
                tag.decompose()
            raw_text = content_el.get_text(separator="\n", strip=True)
        else:
            raw_text = soup.get_text(separator="\n", strip=True)

        # 发布日期：从 .date 或 meta 获取
        date_str = ""
        date_el = soup.select_one(".date")
        if date_el:
            date_str = date_el.get_text(strip=True)  # 例如 "August 28, 2020"
        else:
            # 备选：从 meta property 获取
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"]  # ISO格式

        # 标签：从 .post-content__tag 获取
        tags = []
        tag_els = soup.select(".post-content__tag")
        for tag_el in tag_els:
            tag_text = tag_el.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)

        return {
            "title": title,
            "raw_text": raw_text,
            "date": date_str,
            "tags": tags
        }


# ==============================================================================
# Microsoft 爬虫 - 完整优化版（含日期提取）
# ==============================================================================

class MicrosoftCrawler(GenericCrawler):
    """Microsoft安全博客爬虫 - 支持别名过滤、摘要检查、日期提取"""
    SOURCE_NAME = "Microsoft"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://www.microsoft.com"

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE, f"{self.BASE_URL}/en-us/security/blog/search/?s={{keyword}}")

    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索Microsoft文章 - 使用别名，并检查标题、URL和摘要"""
        aliases = get_keyword_aliases(keyword)
        log.info(f"Microsoft: 搜索关键词 {aliases}")

        all_articles = []
        seen_urls = set()

        for alias in aliases:
            search_url = f"{self.BASE_URL}/en-us/security/blog/search/?s={quote(alias)}"
            log.info(f"  搜索 '{alias}' at {search_url}")

            try:
                html = fetch_url(search_url, timeout=30)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                articles = self._extract_articles_from_page(soup)
                for art in articles:
                    if art['url'] not in seen_urls:
                        seen_urls.add(art['url'])
                        all_articles.append(art)

                time.sleep(1)
            except Exception as e:
                log.warning(f"  搜索 '{alias}' 失败: {e}")

        # 使用所有别名进行过滤（检查标题、URL、摘要）
        aliases_lower = [a.lower() for a in aliases]
        filtered = []
        for art in all_articles:
            title_lower = art.get('title', '').lower()
            url_lower = art.get('url', '').lower()
            desc_lower = art.get('description', '').lower()

            if any(
                alias in title_lower or
                alias in url_lower or
                alias in desc_lower
                for alias in aliases_lower
            ):
                filtered.append(art)

        log.info(
            f"Microsoft: 找到 {len(all_articles)} 篇文章，其中 {len(filtered)} 篇与关键词 '{keyword}' 或其别名相关"
        )
        return filtered[:limit]

    def _extract_articles_from_page(self, soup) -> List[Dict]:
        """从搜索结果页提取文章链接、标题和摘要（日期留空，在fetch时补全）"""
        articles = []
        for card in soup.select('.card-block'):
            link = card.select_one('.card-block__title a[href]')
            if not link:
                continue

            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title:
                continue

            if not href.startswith('http'):
                href = urljoin(self.BASE_URL, href)

            desc_elem = card.select_one('.card-block__excerpt')
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            articles.append({
                "url": href,
                "title": title[:200],
                "description": description[:500],
                "date": ""  # 留空，在fetch_article中补充
            })
        return articles

    def fetch_article(self, url: str) -> Dict:
        """获取文章全文，提取标题、正文、发布日期"""
        html = fetch_url(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 正文：优先 .post-content，其次 article
        content_el = soup.select_one(".post-content, article")
        if content_el:
            for tag in content_el.select("script, style, .related-posts, .post-content__tags"):
                tag.decompose()
            raw_text = content_el.get_text(separator="\n", strip=True)
        else:
            raw_text = soup.get_text(separator="\n", strip=True)

        # 日期：从 meta 或 time 标签提取
        published_date = ""
        # 优先使用 meta property
        meta_date = soup.find("meta", property="article:published_time")
        if meta_date and meta_date.get("content"):
            published_date = meta_date["content"]
        else:
            # 备选：time 标签
            time_el = soup.select_one("time[datetime]")
            if time_el:
                published_date = time_el.get("datetime", "")
            if not published_date:
                # 再尝试从文本中找日期（如 "August 30, 2024"）
                date_pattern = r"([A-Z][a-z]+ \d{1,2}, \d{4})"
                match = re.search(date_pattern, raw_text[:500])  # 仅搜索开头部分
                if match:
                    published_date = match.group(1)

        return {
            "title": title,
            "raw_text": raw_text,
            "date": published_date,
            "tags": []
        }


# ==============================================================================
# SecureList 爬虫 - 完整优化版（含日期提取）
# ==============================================================================

class SecureListCrawler(GenericCrawler):
    """SecureList爬虫 - 使用HTTP请求，优化过滤逻辑，提取日期"""
    SOURCE_NAME = "SecureList"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://securelist.com"

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE, f"{self.BASE_URL}/?s={{keyword}}")

    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        aliases = get_keyword_aliases(keyword)
        log.info(f"SecureList: 搜索关键词 {aliases}")

        all_articles = []
        seen_urls = set()

        for alias in aliases:
            search_url = f"{self.BASE_URL}/?s={quote(alias)}"
            log.info(f"  搜索 '{alias}' at {search_url}")

            try:
                html = fetch_url(search_url, timeout=30)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                articles = self._extract_articles_from_page(soup)
                for art in articles:
                    if art['url'] not in seen_urls:
                        seen_urls.add(art['url'])
                        all_articles.append(art)

                time.sleep(1)
            except Exception as e:
                log.warning(f"  搜索 '{alias}' 失败: {e}")

        aliases_lower = [a.lower() for a in aliases]
        filtered = []
        for art in all_articles:
            title_lower = art.get('title', '').lower()
            url_lower = art.get('url', '').lower()
            desc_lower = art.get('description', '').lower()

            if any(
                alias in title_lower or
                alias in url_lower or
                alias in desc_lower
                for alias in aliases_lower
            ):
                filtered.append(art)

        log.info(
            f"SecureList: 找到 {len(all_articles)} 篇文章，其中 {len(filtered)} 篇与关键词 '{keyword}' 或其别名相关"
        )
        return filtered[:limit]

    def _extract_articles_from_page(self, soup) -> List[Dict]:
        articles = []
        for article in soup.select('article.c-card'):
            link = article.select_one('a.c-card__link[href]')
            if not link:
                continue

            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title:
                continue

            if not href.startswith('http'):
                href = urljoin(self.BASE_URL, href)

            desc_elem = article.select_one('.c-card__desc p')
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            articles.append({
                "url": href,
                "title": title[:200],
                "description": description[:500],
                "date": ""  # 留空，在fetch时补全
            })
        return articles

    def fetch_article(self, url: str) -> Dict:
        """获取文章全文，提取标题、正文、发布日期"""
        html = fetch_url(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 正文：优先 .main-post-section 或 .article-content
        content_el = soup.select_one(".main-post-section, .article-content, .entry-content, .post-content")
        if content_el:
            for tag in content_el.select("script, style, .related-posts, .post-content__tags"):
                tag.decompose()
            raw_text = content_el.get_text(separator="\n", strip=True)
        else:
            raw_text = soup.get_text(separator="\n", strip=True)

        # 日期：从 meta 或 time 标签提取
        published_date = ""
        meta_date = soup.find("meta", property="article:published_time")
        if meta_date and meta_date.get("content"):
            published_date = meta_date["content"]
        else:
            time_el = soup.select_one("time[datetime]")
            if time_el:
                published_date = time_el.get("datetime", "")
            if not published_date:
                # 尝试从文本中提取日期（格式如 "23 Oct 2024"）
                date_pattern = r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})"
                match = re.search(date_pattern, raw_text[:500])
                if match:
                    published_date = match.group(1)

        return {
            "title": title,
            "raw_text": raw_text,
            "date": published_date,
            "tags": []
        }


# ==============================================================================
# TRM Labs 爬虫 - HTTP请求
# ==============================================================================

class TRMLabsCrawler(GenericCrawler):
    """TRM Labs爬虫 - 使用HTTP请求，定制内容提取"""
    SOURCE_NAME = "TRM Labs"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://www.trmlabs.com"

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE, f"{self.BASE_URL}/search?query={{keyword}}")

    def extract_article_links(self, soup, base_url: str) -> List[Dict]:
        """提取TRM Labs文章链接（基于当前页面结构）"""
        articles = []
        seen = set()

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)

            # 仅保留博客文章链接
            if '/blog/' not in href and '/resources/blog/' not in href:
                continue
            if len(text) < 20:
                continue

            if not href.startswith('http'):
                href = urljoin(self.BASE_URL, href)

            if href in seen:
                continue

            seen.add(href)
            articles.append({"url": href, "title": text[:200], "date": ""})

        return articles

    def fetch_article(self, url: str) -> Dict:
        """通用抓取方法 - 仅提取标题和正文，日期留空（子类可覆盖）"""
        html = fetch_url(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        content_el = soup.select_one("article, .entry-content, .post-content, .blog-content, main")
        if content_el:
            for tag in content_el.select("script, style, nav, footer"):
                tag.decompose()
            raw_text = content_el.get_text(separator="\n", strip=True)
        else:
            raw_text = soup.get_text(separator="\n", strip=True)

        return {
            "title": title,
            "raw_text": raw_text,
            "date": "",  # 子类应覆盖此方法以提供日期
            "tags": []
        }


# ==============================================================================
# 数据源配置
# ==============================================================================

SOURCES = {
    "chainalysis": lambda: ChainalysisCrawler(),
    "trmlabs": lambda: TRMLabsCrawler(),
    "microsoft": lambda: MicrosoftCrawler(),
    "securelist": lambda: SecureListCrawler(),
}


def main():
    parser = argparse.ArgumentParser(description="补充数据爬虫 v1 - HTTP请求版本")
    parser.add_argument("--sources", type=int, required=True, help="Local source bitmask")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--limit", type=int, default=20, help="最大文章数")
    
    args = parser.parse_args()
    
    log.info(f"开始爬取: source={args.source}, keyword={args.keyword}, limit={args.limit}")
    
    for source_name in sources_from_mask(args.sources):
        crawler_factory = SOURCES[source_name]
        log.info(f"\n--- 运行 {source_name} 爬虫 ---")
        try:
            crawler = crawler_factory()
            crawler.run(args.keyword, args.limit)
        except Exception as e:
            log.error(f"{source_name} 爬虫失败: {e}")
    
    log.info("\n--- 爬虫完成 ---")


if __name__ == "__main__":
    main()
