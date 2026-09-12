import asyncio
from collections import defaultdict
from pathlib import Path
import httpx
import structlog

from src.core.client import AsyncScraperClient
from src.scrapers.jobs_crawler import (
    crawl_arbeitnow,
    crawl_himalayas,
    crawl_jobicy,
    crawl_remoteok,
    crawl_weworkremotely,
)
from src.scrapers.news_crawler import crawl_news
from src.utils.freshness_store import FreshnessStore
from src.storage.sqlite_store import SQLiteStore

logger = structlog.get_logger(__name__)


async def main():
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    freshness_store = FreshnessStore()

    news_counts = defaultdict(int)
    job_counts = defaultdict(int)

    async with AsyncScraperClient(impersonate="chrome120") as scraper_client:
        with open("data/processed/news.jsonl", "w", encoding="utf-8") as news_out:
            async for record in crawl_news(scraper_client, freshness_store):
                news_out.write(record.model_dump_json() + "\n")
                news_counts[record.source.name] += 1

    freshness_store.persist()

    job_crawlers = [
        ("RemoteOK", crawl_remoteok),
        ("Arbeitnow", crawl_arbeitnow),
        ("Jobicy", crawl_jobicy),
        ("Himalayas", crawl_himalayas),
        ("WeWorkRemotely", crawl_weworkremotely),
    ]

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as http_client:
        store = SQLiteStore(db_path="data/processed/seen_signals.db")
        await store.init_db()
        
        with open("data/processed/jobs.jsonl", "w", encoding="utf-8") as jobs_out:
            for name, crawler_fn in job_crawlers:
                try:
                    async for record in crawler_fn(http_client):
                        if await store.insert_record(record):
                            jobs_out.write(record.model_dump_json() + "\n")
                            job_counts[name] += 1
                except Exception as e:
                    logger.error("job_source_execution_error", source=name, error=str(e))
                    continue

    print("\n================== PHASE 2 INGESTION SUMMARY ==================")
    print(f"Total News Records (24h Fresh): {sum(news_counts.values())}")
    for src, cnt in news_counts.items():
        print(f"  - {src}: {cnt}")

    print(f"\nTotal Job Records (24h Fresh): {sum(job_counts.values())}")
    for src, cnt in job_counts.items():
        print(f"  - {src}: {cnt}")
    print("===============================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
