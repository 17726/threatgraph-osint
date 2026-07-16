"""
补充数据爬虫 v2 - Playwright版本
处理需要JavaScript渲染的网站：CrowdStrike、Group-IB、OFAC、FBI

使用方式：
    python scripts/crawler_supplementary_v2.py --source crowdstrike --keyword APT28 --limit 10
    python scripts/crawler_supplementary_v2.py --source groupib --keyword Lazarus --limit 10
    python scripts/crawler_supplementary_v2.py --source ofac,fbi --keyword Lazarus --limit 10
    python scripts/crawler_supplementary_v2.py --source all --keyword Lazarus --limit 5
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
CRAWLER_NAME = "scripts/crawler_supplementary_v2.py"

DOCUMENT_KEYS = [
    "doc_id", "schema_version", "target_group", "target_groups",
    "source_url", "source_type", "source_name", "title",
    "language", "clean_text", "content_hash", "published_at",
    "retrieved_at", "source_reliability", "tlp", "tags", "metadata",
]

SOURCE_RELIABILITY_MAP = {
    "Microsoft": "B", "SecureList": "B", "CrowdStrike": "B",
    "Group-IB": "B", "OFAC": "A", "FBI": "A",
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


SOURCE_NAMES = ("crowdstrike", "groupib", "ofac", "fbi")


def parse_sources(value: str) -> List[str]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested:
        raise ValueError("source cannot be empty")
    if "all" in requested:
        if len(requested) != 1:
            raise ValueError("source=all cannot be combined with individual sources")
        return list(SOURCE_NAMES)
    unknown = [item for item in requested if item not in SOURCE_NAMES]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}")
    return list(dict.fromkeys(requested))

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
# Playwright 浏览器管理
# ==============================================================================

_playwright_instance = None
_browser = None

def get_playwright_browser():
    global _playwright_instance, _browser
    if _playwright_instance is None:
        from playwright.sync_api import sync_playwright
        _playwright_instance = sync_playwright().start()
        _browser = _playwright_instance.chromium.launch(headless=True)
    return _browser

def close_playwright():
    global _playwright_instance, _browser
    if _browser:
        _browser.close()
        _browser = None
    if _playwright_instance:
        _playwright_instance.stop()
        _playwright_instance = None

# ==============================================================================
# 通用爬虫基类
# ==============================================================================

class GenericCrawler:
    """通用爬虫基类"""
    
    def __init__(self, source_name: str, source_type: str):
        self.source_name = source_name
        self.source_type = source_type
    
    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索文章 - 子类必须覆盖"""
        raise NotImplementedError
    
    def fetch_article(self, url: str) -> Dict:
        """获取文章全文"""
        content = fetch_page_content(url)
        title_match = re.search(r'^(.+?)\n', content)
        title = title_match.group(1).strip() if title_match else ""
        return {"title": title, "raw_text": content, "date": "", "tags": []}
    
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

def fetch_page_content(url: str, timeout: int = 60000) -> str:
    """使用playwright获取页面内容"""
    browser = get_playwright_browser()
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(3000)
        
        content = page.evaluate("""() => {
            const noise = ['nav', 'footer', 'header', '.nav', '.footer', '.header', 
                          '.sidebar', '.menu', '.cookie', '.banner', '.ad', '.comment',
                          '.related', '.recommend', '.share', '.social'];
            noise.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            
            const article = document.querySelector('article, .article, .content, .post-content, main, .main, .entry-content');
            if (article) return article.innerText;
            return document.body.innerText;
        }""")
        return content
    finally:
        page.close()
        context.close()

# ==============================================================================
# CrowdStrike 爬虫 - 使用cloudscraper绕过Cloudflare
# ==============================================================================

class CrowdStrikeCrawler(GenericCrawler):
    """CrowdStrike爬虫 - 使用cloudscraper绕过Cloudflare保护"""
    SOURCE_NAME = "CrowdStrike"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://www.crowdstrike.com"
    
    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE)
    
    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        aliases = get_keyword_aliases(keyword)
        log.info(f"CrowdStrike: 搜索关键词 {aliases}")
        
        all_articles = []
        seen_urls = set()
        
        for alias in aliases:
            search_url = f"{self.BASE_URL}/en-us/blog/?search={quote(alias)}"
            log.info(f"  搜索 '{alias}' at {search_url}")
            
            try:
                articles = self._search_with_cloudscraper(search_url)
                for art in articles:
                    if art['url'] not in seen_urls:
                        seen_urls.add(art['url'])
                        all_articles.append(art)
                time.sleep(1)
            except Exception as e:
                log.warning(f"  搜索 '{alias}' 失败: {e}")
        
        log.info(f"CrowdStrike: 找到 {len(all_articles)} 篇文章")
        return all_articles[:limit]
    
    def _search_with_cloudscraper(self, url: str) -> List[Dict]:
        """使用cloudscraper绕过Cloudflare保护"""
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
                interpreter='native'
            )
            scraper.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            response = scraper.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = []
            seen = set()
            
            # CrowdStrike文章链接在 a.search-results__link[href] 中
            for link in soup.select('a.search-results__link[href]'):
                href = link.get('href', '')
                title_el = link.select_one('.search-results__title')
                text = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                
                # 构建完整URL
                if href and not href.startswith('http'):
                    href = self.BASE_URL + href
                
                if href and text and '/blog/' in href:
                    if href not in seen:
                        seen.add(href)
                        articles.append({"url": href, "title": text[:200], "date": ""})
            
            # 如果精确选择器没找到，回退到通用选择器
            if not articles:
                for link in soup.select('a[href*="/blog/"]'):
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # 构建完整URL
                    if href and not href.startswith('http'):
                        href = self.BASE_URL + href
                    
                    if href and text and len(text) > 20 and not href.endswith('/blog/') and '/category/' not in href:
                        if href not in seen:
                            seen.add(href)
                            articles.append({"url": href, "title": text[:200], "date": ""})
            
            return articles
            
        except ImportError:
            log.error("cloudscraper未安装，请运行: pip install cloudscraper")
            return []
        except Exception as e:
            log.error(f"Cloudflare绕过失败: {e}")
            return []

# ==============================================================================
# Group-IB 爬虫 - Playwright
# ==============================================================================

class GroupIBCrawler(GenericCrawler):
    """Group-IB爬虫 - 纯Playwright搜索，无硬编码后备"""
    SOURCE_NAME = "Group-IB"
    SOURCE_TYPE = "vendor_report"
    BASE_URL = "https://www.group-ib.com"

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE)

    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """使用别名搜索，返回文章链接列表"""
        aliases = get_keyword_aliases(keyword)
        log.info(f"Group-IB: 使用别名搜索 {aliases}")

        all_articles = []
        seen_urls = set()

        for alias in aliases:
            search_url = f"{self.BASE_URL}/?s={quote(alias)}"
            try:
                articles = self._search_with_playwright(search_url, limit)
                for art in articles:
                    if art['url'] not in seen_urls:
                        seen_urls.add(art['url'])
                        all_articles.append(art)
                if len(all_articles) >= limit:
                    break
            except Exception as e:
                log.warning(f"Group-IB: 搜索 '{alias}' 失败: {e}")
                continue

        log.info(f"Group-IB: 去重后共找到 {len(all_articles)} 篇文章")
        return all_articles[:limit]

    def _search_with_playwright(self, url: str, limit: int) -> List[Dict]:
        """执行Playwright搜索并提取卡片信息"""
        browser = get_playwright_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        articles = []

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等待搜索结果卡片出现
            try:
                page.wait_for_selector('.sr-card', timeout=10000)
            except Exception:
                log.warning("Group-IB: 搜索结果页无卡片，可能被拦截或无结果")
                return []

            # 提取卡片数据（只保留博客文章）
            cards = page.evaluate("""() => {
                const cards = document.querySelectorAll('.sr-card');
                return Array.from(cards).map(card => {
                    const link = card.querySelector('a.sr-card__title');
                    if (!link) return null;
                    // 只保留博客链接
                    if (link.href.indexOf('/blog/') === -1) return null;
                    return {
                        url: link.href,
                        title: link.innerText.trim(),
                    };
                }).filter(item => item !== null);
            }""")

            for item in cards[:limit]:
                articles.append({
                    'url': item['url'],
                    'title': item['title'][:200],
                    'date': ''
                })

        except Exception as e:
            log.error(f"Playwright搜索失败: {e}")
        finally:
            page.close()
            context.close()

        return articles

    def fetch_article(self, url: str) -> Dict:
        """获取文章标题、正文和发布日期"""
        log.info(f"Group-IB: 获取文章 {url}")
        browser = get_playwright_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('.blog-post-content', timeout=10000)

            # 标题
            title_el = page.query_selector('h1.header__title')
            title = title_el.inner_text().strip() if title_el else ""

            # 正文
            content_el = page.query_selector('.blog-post-content')
            raw_text = content_el.inner_text().strip() if content_el else ""

            # 发布日期（格式如 "November 5, 2019 · 5 min to read · Threat Intelligence"）
            date_el = page.query_selector('.post-info__date .body2')
            published_date = ""
            if date_el:
                date_text = date_el.inner_text().strip()
                import re
                match = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', date_text)
                if match:
                    published_date = match.group(1)

            page.close()
            context.close()

            return {
                "title": title,
                "raw_text": raw_text,
                "date": published_date,
                "tags": []
            }

        except Exception as e:
            log.error(f"Group-IB: 获取文章失败: {e}")
            page.close()
            context.close()
            return {"title": "", "raw_text": "", "date": "", "tags": []}

# ==============================================================================
# OFAC 爬虫 - 已知URL
# ==============================================================================

class OFACCrawler(GenericCrawler):
    """OFAC制裁公告爬虫 - 动态搜索 + 硬编码后备"""
    SOURCE_NAME = "OFAC"
    SOURCE_TYPE = "government_notice"
    BASE_URL = "https://home.treasury.gov"
    SEARCH_URL = f"{BASE_URL}/news/press-releases"

    # 硬编码后备（可手动扩展）
    KNOWN_ADVISORIES = [
        {
            "url": "https://home.treasury.gov/news/press-releases/sm924",
            "title": "Treasury Sanctions Individuals Laundering Cryptocurrency for Lazarus Group",
            "target_group": "Lazarus",
            "date": "2020-03-02",
        },
    ]

    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE)

    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索OFAC新闻公告，先尝试动态搜索，失败则用硬编码"""
        aliases = get_keyword_aliases(keyword)
        log.info(f"OFAC: 使用关键词 '{keyword}' 搜索新闻列表")

        # 1. 尝试动态搜索
        try:
            articles = self._fetch_search_results(aliases, limit)
            if articles:
                log.info(f"OFAC: 从搜索结果找到 {len(articles)} 篇匹配文章")
                return articles
        except Exception as e:
            log.warning(f"OFAC: 搜索失败: {e}")

        # 2. 后备：硬编码已知公告
        log.info("OFAC: 使用硬编码后备公告")
        return self._fallback_articles(keyword, limit)

    def _fetch_search_results(self, aliases: List[str], limit: int) -> List[Dict]:
        """使用Playwright获取搜索结果页，提取匹配的文章"""
        browser = get_playwright_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        articles = []

        try:
            # 使用搜索参数 title=keyword（可换成第一个别名）
            search_keyword = aliases[0] if aliases else "Lazarus"
            url = f"{self.SEARCH_URL}?title={quote(search_keyword)}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等待搜索结果容器出现
            page.wait_for_selector('.featured-stories .content--2col__body > div', timeout=15000)

            # 提取所有结果条目
            items = page.evaluate("""() => {
                const results = [];
                const rows = document.querySelectorAll('.featured-stories .content--2col__body > div');
                rows.forEach(row => {
                    const dateEl = row.querySelector('.date-format time');
                    const linkEl = row.querySelector('h3.featured-stories__headline a');
                    if (!linkEl) return;
                    const date = dateEl ? dateEl.getAttribute('datetime') || dateEl.innerText.trim() : '';
                    results.push({
                        url: linkEl.href,
                        title: linkEl.innerText.trim(),
                        date: date
                    });
                });
                return results;
            }""")

            # 根据别名过滤标题（不区分大小写）
            aliases_lower = [a.lower() for a in aliases]
            for item in items:
                title_lower = item['title'].lower()
                if any(alias in title_lower for alias in aliases_lower):
                    articles.append({
                        'url': item['url'],
                        'title': item['title'][:200],
                        'date': item['date']
                    })
                    if len(articles) >= limit:
                        break

            page.close()
            context.close()
            return articles

        except Exception as e:
            log.error(f"搜索结果提取失败: {e}")
            page.close()
            context.close()
            return []

    def _fallback_articles(self, keyword: str, limit: int) -> List[Dict]:
        """使用硬编码列表，并根据关键词过滤"""
        target_group = normalize_target_group(keyword)
        matched = []
        for adv in self.KNOWN_ADVISORIES:
            # 根据目标组匹配（简单匹配）
            if target_group.lower() in adv['target_group'].lower():
                matched.append(adv)
            # 或者关键词在标题中
            elif keyword.lower() in adv['title'].lower():
                matched.append(adv)
        return matched[:limit]

    def fetch_article(self, url: str) -> Dict:
        """获取OFAC新闻稿详情：标题、日期、正文"""
        log.info(f"OFAC: 获取文章 {url}")
        browser = get_playwright_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待正文区域
            page.wait_for_selector('.field--name-field-news-body', timeout=15000)

            # 标题 (h2.uswds-page-title)
            title_el = page.query_selector('h2.uswds-page-title')
            title = title_el.inner_text().strip() if title_el else ""

            # 发布日期 (time.datetime)
            date_el = page.query_selector('time.datetime')
            published_date = ""
            if date_el:
                date_text = date_el.get_attribute('datetime') or date_el.inner_text().strip()
                if date_text and 'T' in date_text:
                    published_date = date_text.split('T')[0]
                else:
                    published_date = date_text

            # 正文 (.field--name-field-news-body)
            content_el = page.query_selector('.field--name-field-news-body')
            raw_text = content_el.inner_text().strip() if content_el else ""

            # 备用选择器
            if not raw_text:
                content_el = page.query_selector('.clearfix.text-formatted')
                if content_el:
                    raw_text = content_el.inner_text().strip()

            page.close()
            context.close()

            return {
                "title": title,
                "raw_text": raw_text,
                "date": published_date,
                "tags": []
            }

        except Exception as e:
            log.error(f"OFAC: 获取文章失败: {e}")
            page.close()
            context.close()
            return {"title": "", "raw_text": "", "date": "", "tags": []}

# ==============================================================================
# FBI 爬虫 - Playwright
# ==============================================================================

class FBICrawler(GenericCrawler):
    """FBI爬虫 - 使用Playwright"""
    SOURCE_NAME = "FBI"
    SOURCE_TYPE = "government_notice"
    BASE_URL = "https://www.fbi.gov"
    
    def __init__(self):
        super().__init__(self.SOURCE_NAME, self.SOURCE_TYPE)
    
    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        search_url = f"{self.BASE_URL}/@@search?SearchableText={quote(keyword)}"
        log.info(f"FBI: 搜索 '{keyword}' at {search_url}")
        
        try:
            articles = self._search_with_playwright(search_url)
            log.info(f"FBI: 找到 {len(articles)} 篇文章")
            return articles[:limit]
        except Exception as e:
            log.error(f"FBI: 搜索失败: {e}")
            return []
    
    def _search_with_playwright(self, url: str) -> List[Dict]:
        browser = get_playwright_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        articles = []
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(10000)
            
            js_code = """() => {
                const results = [];
                const anchors = document.querySelectorAll('a[href]');
                for (const a of anchors) {
                    const href = a.href;
                    const text = a.innerText.trim();
                    if (href && text && text.length > 20 && href.includes('fbi.gov')) {
                        results.push({url: href, title: text.substring(0, 200)});
                    }
                }
                return results;
            }"""
            
            links = page.evaluate(js_code)
            
            seen = set()
            for link in links:
                if link['url'] not in seen:
                    seen.add(link['url'])
                    articles.append(link)
            
        except Exception as e:
            log.error(f"Playwright获取失败: {e}")
        finally:
            page.close()
            context.close()
        
        return articles

# ==============================================================================
# 数据源配置
# ==============================================================================

SOURCES = {
    "crowdstrike": CrowdStrikeCrawler,
    "groupib": GroupIBCrawler,
    "ofac": OFACCrawler,
    "fbi": FBICrawler,
}


def main():
    parser = argparse.ArgumentParser(description="补充数据爬虫 v2 - Playwright版本")
    parser.add_argument("--source", required=True, help="Comma-separated sources or all")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--limit", type=int, default=20, help="最大文章数")
    
    args = parser.parse_args()
    
    log.info(f"开始爬取: source={args.source}, keyword={args.keyword}, limit={args.limit}")
    
    try:
        for source_name in parse_sources(args.source):
            crawler_class = SOURCES[source_name]
            log.info(f"\n--- 运行 {source_name} 爬虫 ---")
            try:
                crawler = crawler_class()
                crawler.run(args.keyword, args.limit)
            except Exception as e:
                log.error(f"{source_name} 爬虫失败: {e}")
    finally:
        close_playwright()
    
    log.info("\n--- 爬虫完成 ---")


if __name__ == "__main__":
    main()
