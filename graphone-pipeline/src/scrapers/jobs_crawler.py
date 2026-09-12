import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
import feedparser
import httpx
import structlog

from src.models.schemas import JobContent, JobEntity, SourceMetadata
from src.utils.date_parser import is_within_freshness_window, parse_to_utc

logger = structlog.get_logger(__name__)


def classify_role_family(title: str) -> Optional[str]:
    title_lower = title.lower()
    mapping = {
        "Data/ML": ["data scientist", "machine learning", "ml", "ai", "deep learning", "nlp"],
        "Engineering": ["engineer", "developer", "swe", "backend", "frontend", "fullstack"],
        "Product": ["product manager", "product lead", "head of product"],
        "Design": ["designer", "ux", "ui"],
    }
    for family, keywords in mapping.items():
        if any(k in title_lower for k in keywords):
            return family
    return None


async def crawl_remoteok(client: httpx.AsyncClient) -> AsyncGenerator[JobEntity, None]:
    try:
        resp = await client.get("https://remoteok.com/api")
        resp.raise_for_status()
        data = resp.json()
        for item in data[1:]:
            try:
                posted = parse_to_utc(item.get("date"))
                if not is_within_freshness_window(posted, hours=24):
                    continue
                yield JobEntity(
                    source=SourceMetadata(name="RemoteOK", url=item.get("url", "https://remoteok.com")),
                    content=JobContent(
                        company=item.get("company", "Unknown"),
                        date=posted,
                        is_remote=True,
                        role_family=classify_role_family(item.get("position", "")),
                        title=item.get("position", "").strip(),
                        job_url=item.get("url", ""),
                    ),
                    collectedAt=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error("remoteok_item_failed", error=str(e))
                continue
    except Exception as e:
        logger.error("remoteok_source_failed", error=str(e))


async def crawl_arbeitnow(client: httpx.AsyncClient) -> AsyncGenerator[JobEntity, None]:
    try:
        resp = await client.get("https://www.arbeitnow.com/api/job-board-api")
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for item in data:
            try:
                posted = parse_to_utc(item.get("created_at"))
                if not is_within_freshness_window(posted, hours=24):
                    continue
                yield JobEntity(
                    source=SourceMetadata(name="Arbeitnow", url=item.get("url", "https://www.arbeitnow.com")),
                    content=JobContent(
                        company=item.get("company_name", "Unknown"),
                        date=posted,
                        is_remote=item.get("remote", False),
                        role_family=classify_role_family(item.get("title", "")),
                        title=item.get("title", "").strip(),
                        job_url=item.get("url", ""),
                    ),
                    collectedAt=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error("arbeitnow_item_failed", error=str(e))
                continue
    except Exception as e:
        logger.error("arbeitnow_source_failed", error=str(e))


async def crawl_jobicy(client: httpx.AsyncClient) -> AsyncGenerator[JobEntity, None]:
    try:
        resp = await client.get("https://jobicy.com/api/v2/remote-jobs?count=50&tag=ai")
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
        for item in data:
            try:
                posted = parse_to_utc(item.get("pubDate"))
                if not is_within_freshness_window(posted, hours=24):
                    continue
                yield JobEntity(
                    source=SourceMetadata(name="Jobicy", url=item.get("url", "https://jobicy.com")),
                    content=JobContent(
                        company=item.get("companyName", "Unknown"),
                        date=posted,
                        is_remote=True,
                        role_family=classify_role_family(item.get("jobTitle", "")),
                        title=item.get("jobTitle", "").strip(),
                        job_url=item.get("url", ""),
                    ),
                    collectedAt=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error("jobicy_item_failed", error=str(e))
                continue
    except Exception as e:
        logger.error("jobicy_source_failed", error=str(e))


async def crawl_himalayas(client: httpx.AsyncClient) -> AsyncGenerator[JobEntity, None]:
    try:
        resp = await client.get("https://himalayas.app/jobs/api?limit=50")
        resp.raise_for_status()
        data = resp.json().get("jobs", [])
        for item in data:
            try:
                posted = parse_to_utc(item.get("pubDate"))
                if not is_within_freshness_window(posted, hours=24):
                    continue
                link = item.get("applicationLink") or f"https://himalayas.app/jobs/{item.get('slug')}"
                yield JobEntity(
                    source=SourceMetadata(name="Himalayas", url=link),
                    content=JobContent(
                        company=item.get("companyName", "Unknown"),
                        date=posted,
                        is_remote=True,
                        role_family=classify_role_family(item.get("title", "")),
                        title=item.get("title", "").strip(),
                        job_url=link,
                    ),
                    collectedAt=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error("himalayas_item_failed", error=str(e))
                continue
    except Exception as e:
        logger.error("himalayas_source_failed", error=str(e))


async def crawl_weworkremotely(client: httpx.AsyncClient) -> AsyncGenerator[JobEntity, None]:
    try:
        resp = await client.get("https://weworkremotely.com/categories/remote-programming-jobs.rss")
        resp.raise_for_status()
        feed = await asyncio.to_thread(feedparser.parse, resp.text)
        for entry in feed.entries:
            try:
                posted = parse_to_utc(entry.get("published_parsed"))
                if not is_within_freshness_window(posted, hours=24):
                    continue
                title = entry.get("title", "")
                company = title.split(":")[0].strip() if ":" in title else "Unknown"
                yield JobEntity(
                    source=SourceMetadata(name="WeWorkRemotely", url=entry.get("link", "")),
                    content=JobContent(
                        company=company,
                        date=posted,
                        is_remote=True,
                        role_family=classify_role_family(title),
                        title=title.strip(),
                        job_url=entry.get("link", ""),
                    ),
                    collectedAt=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error("wwr_item_failed", error=str(e))
                continue
    except Exception as e:
        logger.error("wwr_source_failed", error=str(e))
