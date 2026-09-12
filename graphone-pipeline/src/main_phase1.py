import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
import structlog
from typing import Any
from src.core.client import AsyncScraperClient
from src.scrapers.github_enricher import GitHubEnricher
from src.scrapers.papers_crawler import ResearchPapersCrawler
from src.scrapers.directory_crawler import DirectoryCrawler
from src.storage.sqlite_store import SQLiteStore
from pydantic_settings import BaseSettings

logger = structlog.get_logger(__name__)

class PipelineConfig(BaseSettings):
    WORKER_CONCURRENCY: int = 10
    QUEUE_MAXSIZE: int = 500
    TARGET_RECORDS: int = 1050

config = PipelineConfig()

async def producer(
    crawler: ResearchPapersCrawler, 
    dir_crawler: DirectoryCrawler, 
    client: AsyncScraperClient,
    queue: asyncio.Queue
):
    logger.info("producer_started")

    async def produce_arxiv():
        async for record in crawler.crawl_arxiv_bulk(client, max_records=config.TARGET_RECORDS):
            await queue.put(record)
            
    async def produce_startups():
        dir_crawler = DirectoryCrawler()
        async for record in dir_crawler.crawl_startups(client, max_records=config.TARGET_RECORDS):
            await queue.put(record)
            
    async def produce_products():
        dir_crawler = DirectoryCrawler()
        async for record in dir_crawler.crawl_products(client, max_records=config.TARGET_RECORDS):
            await queue.put(record)

    await asyncio.gather(produce_arxiv(), produce_startups(), produce_products())

    for _ in range(config.WORKER_CONCURRENCY):
        await queue.put(None)
    logger.info("producer_finished")

async def worker(
    worker_id: int, 
    queue: asyncio.Queue, 
    store: SQLiteStore, 
    client: AsyncScraperClient,
    enricher: GitHubEnricher,
    semaphore: asyncio.Semaphore
):
    logger.info("worker_started", worker_id=worker_id)
    while True:
        record = await queue.get()
        if record is None:
            queue.task_done()
            break
            
        async with semaphore:
            if hasattr(record.content, 'github_url') and record.content.github_url and client.session:
                if record.content.github_stars is None:
                    stars = await enricher.get_stars(client.session, record.content.github_url)
                    record.content.github_stars = stars
            
            inserted = await store.insert_record(record)
            if inserted:
                logger.debug("record_inserted", type=record.recordType)
            
        queue.task_done()
    logger.info("worker_finished", worker_id=worker_id)


async def run_pipeline():
    os.makedirs("data/processed", exist_ok=True)
    
    enricher = GitHubEnricher(github_token=os.getenv("GITHUB_TOKEN"))
    crawler = ResearchPapersCrawler(enricher)
    dir_crawler = DirectoryCrawler()
    store = SQLiteStore(db_path="data/processed/staging.db")
    await store.init_db()
    
    queue = asyncio.Queue(maxsize=config.QUEUE_MAXSIZE)
    semaphore = asyncio.Semaphore(config.WORKER_CONCURRENCY)
    
    async with AsyncScraperClient(impersonate="chrome120") as client:
        workers = [
            asyncio.create_task(worker(i, queue, store, client, enricher, semaphore))
            for i in range(config.WORKER_CONCURRENCY)
        ]
        
        producer_task = asyncio.create_task(producer(crawler, dir_crawler, client, queue))
        
        await producer_task
        await queue.join()
        await asyncio.gather(*workers)
        
    logger.info("flushing_to_jsonl")
    await store.flush_to_jsonl("data/processed/research_papers.jsonl", "RESEARCH_PAPER")
    await store.flush_to_jsonl("data/processed/startups.jsonl", "STARTUP")
    await store.flush_to_jsonl("data/processed/products.jsonl", "PRODUCT")
    
    logger.info("pipeline_complete")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
