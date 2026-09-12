"""
TAAFT Products Scraper via /s/ Search Endpoint

The /category/ pages only SSR ~35 products and aggressively rate-limit.
The /s/{query}/ search pages SSR up to ~200 products per request and are
more tolerant to sequential requests. This scraper uses broad search terms
to maximize unique product coverage with deduplication by data-id.
"""

import asyncio
import json
import os
import random
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser
import structlog

logger = structlog.get_logger(__name__)

SEARCH_QUERIES = [
    "writing", "image", "video", "audio", "developer", "marketing",
    "sales", "design", "education", "finance", "legal", "hr",
    "productivity", "customer support", "healthcare", "real estate",
    "research", "seo", "social media", "copywriting", "presentation",
    "avatar", "3d", "gaming", "music", "transcription", "translation",
    "code", "sql", "excel", "automation", "chatbot", "email",
    "data analysis", "project management", "recruitment", "content",
    "voice", "photo editing", "summarizer", "spreadsheet",
    "text to speech", "speech to text", "logo", "art",
    "writing assistant", "story", "resume", "essay", "paraphrasing",
    "grammar", "meeting", "scheduling", "note", "pdf", "document",
    "search engine", "recommendation", "travel", "fitness",
    "startup", "saas", "api", "llm", "gpt", "machine learning",
    "deep learning", "neural network", "nlp", "computer vision",
    "robotics", "analytics", "business intelligence", "crm",
    "accounting", "invoicing", "ecommerce", "marketplace",
    "cybersecurity", "devops", "testing", "database",
    "workflow", "collaboration", "communication", "calendar",
    "task management", "file management", "backup", "cloud",
    "customer service", "help desk", "feedback", "survey",
    "advertising", "branding", "pr", "influencer",
    "video editing", "animation", "podcast", "streaming",
    "language learning", "tutoring", "quiz", "flashcard",
    "diet", "meditation", "sleep", "therapy",
    "investing", "crypto", "insurance", "tax",
    "architecture", "interior design", "fashion",
    "agriculture", "energy", "sustainability", "logistics",
]

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def strip_tracking_params(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items()
                    if not k.startswith(("utm_", "ref"))}
    clean_query = urlencode(clean_params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))


def map_pricing(item_text: str) -> Optional[str]:
    text = item_text.lower()
    if "100% free" in text:
        return "FREE"
    elif "freemium" in text or "free trial" in text:
        return "FREEMIUM"
    elif "paid" in text or "$" in text:
        return "PAID"
    return None


def extract_products_from_html(html: str, seen_ids: set) -> list[dict]:
    parser = HTMLParser(html)
    items = parser.css("li.li")
    products = []

    for item in items:
        attrs = item.attributes
        data_id = attrs.get("data-id")
        if not data_id or data_id in seen_ids:
            continue

        seen_ids.add(data_id)
        name = attrs.get("data-name", "")
        task = attrs.get("data-task", "")
        raw_url = attrs.get("data-url", "")

        if not name:
            continue

        product_url = strip_tracking_params(raw_url) if raw_url else ""
        taaft_url = f"https://theresanaiforthat.com/ai/{name.lower().replace(' ', '-')}/"

        inner_text = item.text(strip=True)
        pricing = map_pricing(inner_text)

        products.append({
            "recordType": "PRODUCT",
            "source": {"name": "TheresAnAIForThat", "url": taaft_url},
            "content": {
                "startupName": name,
                "productUrl": product_url,
                "category": task,
                "pricingModel": pricing,
            },
        })
    return products


async def fetch_with_retry(session: AsyncSession, url: str, max_retries: int = 3) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            response = await session.get(url, headers={
                **BROWSER_HEADERS,
                "Referer": "https://theresanaiforthat.com/",
            })
            if response.status_code in (403, 503):
                body = response.text.lower()
                if "just a moment" in body or "turnstile" in body:
                    backoff = (2 ** attempt) + random.uniform(2.0, 5.0)
                    logger.warning("anti_bot_retry", url=url, attempt=attempt + 1, backoff=round(backoff, 1))
                    await asyncio.sleep(backoff)
                    continue
            response.raise_for_status()
            return response.text
        except Exception as e:
            backoff = (2 ** attempt) + random.uniform(1.0, 3.0)
            logger.warning("fetch_retry", url=url, attempt=attempt + 1, error=str(e))
            await asyncio.sleep(backoff)
    return None


async def scrape_taaft():
    os.makedirs("data/processed", exist_ok=True)
    out_file = "data/processed/products.jsonl"

    with open(out_file, "w", encoding="utf-8") as f:
        pass

    seen_ids: set[str] = set()
    total_yielded = 0
    target = 1200

    async with AsyncSession(impersonate="chrome120", timeout=30) as session:
        warmup = await fetch_with_retry(session, "https://theresanaiforthat.com/")
        if warmup:
            logger.info("session_warmed_up")
        await asyncio.sleep(random.uniform(2.0, 4.0))

        shuffled = SEARCH_QUERIES.copy()
        random.shuffle(shuffled)

        for query in shuffled:
            if total_yielded >= target:
                break

            slug = query.replace(" ", "+")
            url = f"https://theresanaiforthat.com/s/{slug}/"
            html = await fetch_with_retry(session, url)

            if html is None:
                continue

            products = extract_products_from_html(html, seen_ids)

            if products:
                with open(out_file, "a", encoding="utf-8") as f:
                    for p in products:
                        f.write(json.dumps(p) + "\n")
                total_yielded += len(products)
                logger.info("query_scraped", query=query, new=len(products), total=total_yielded)
            else:
                logger.warning("query_empty", query=query)

            await asyncio.sleep(random.uniform(2.0, 5.0))

    logger.info("taaft_scrape_complete", total_records=total_yielded)


if __name__ == "__main__":
    asyncio.run(scrape_taaft())