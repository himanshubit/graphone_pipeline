import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
import feedparser
import structlog
import trafilatura

from src.core.client import AsyncScraperClient
from src.models.schemas import NewsContent, NewsEntity, SourceMetadata
from src.utils.date_parser import is_within_freshness_window, parse_to_utc
from src.utils.freshness_store import FreshnessStore

logger = structlog.get_logger(__name__)

NEWS_SOURCES = {
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "ArXiv cs.AI": "https://rss.arxiv.org/rss/cs.AI",
}


async def crawl_news(
    client: AsyncScraperClient, freshness_store: FreshnessStore
) -> AsyncGenerator[NewsEntity, None]:
    for source_name, feed_url in NEWS_SOURCES.items():
        try:
            feed_xml = await client.fetch(feed_url)
            feed = await asyncio.to_thread(feedparser.parse, feed_xml)

            if feed.bozo and not feed.entries:
                logger.error("news_feed_unreachable", source=source_name, url=feed_url)
                continue

            for entry in feed.entries:
                try:
                    link = entry.get("link")
                    if not link:
                        continue

                    published_raw = entry.get("published_parsed") or entry.get("updated_parsed")
                    published_date = parse_to_utc(published_raw)

                    if published_date is None:
                        if not freshness_store.is_new(link):
                            continue
                        published_date = datetime.now(timezone.utc)
                    elif not is_within_freshness_window(published_date, hours=24):
                        continue

                    try:
                        article_html = await client.fetch(link)
                        body = trafilatura.extract(article_html)
                    except Exception as fetch_err:
                        logger.warning("news_fetch_failed", url=link, error=str(fetch_err))
                        continue

                    if not body:
                        continue

                    record = NewsEntity(
                        source=SourceMetadata(name=source_name, url=link),
                        content=NewsContent(
                            title=entry.get("title", "").strip(),
                            body=body.strip(),
                            published_date=published_date,
                        ),
                        collectedAt=datetime.now(timezone.utc),
                    )
                    freshness_store.mark_seen(link)
                    yield record

                except Exception as entry_err:
                    logger.error("news_entry_failed", source=source_name, error=str(entry_err))
                    continue

        except Exception as src_err:
            logger.error("news_source_failed", source=source_name, error=str(src_err))
            continue
