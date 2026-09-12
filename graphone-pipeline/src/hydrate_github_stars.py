import asyncio
import os
import json
import re
import structlog
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import httpx

logger = structlog.get_logger(__name__)

GITHUB_PAT = os.getenv("GITHUB_TOKEN")
REPO_REGEX = re.compile(r"https?://github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)")


async def hydrate_stars():
    jsonl_path = Path("data/processed/research_papers.jsonl")
    if not jsonl_path.exists():
        logger.error("research_papers_jsonl_not_found")
        return

    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    total = len(records)
    with_github = 0
    stars_populated = 0
    logger.info("hydration_started", total_papers=total)

    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_PAT:
        headers["Authorization"] = f"Bearer {GITHUB_PAT}"
        logger.info("github_pat_injected")
    else:
        logger.warning("github_pat_missing_using_unauthenticated")

    sem = asyncio.Semaphore(10)

    async def fetch_stars(session: httpx.AsyncClient, record: dict) -> dict:
        nonlocal with_github, stars_populated
        content = record.get("content", {})
        github_url = content.get("github_url")

        if github_url:
            match = REPO_REGEX.search(github_url)
            if match:
                owner, repo = match.group(1), match.group(2)
                repo = repo.rstrip(".,/>)").removesuffix(".git")
                content["github_url"] = f"https://github.com/{owner}/{repo}"
                with_github += 1

                async with sem:
                    try:
                        resp = await session.get(
                            f"https://api.github.com/repos/{owner}/{repo}",
                            headers=headers,
                        )
                        if resp.status_code == 200:
                            stars = resp.json().get("stargazers_count", 0)
                            content["github_stars"] = stars
                            if stars > 0:
                                stars_populated += 1
                        elif resp.status_code in (404, 451):
                            content["github_stars"] = 0
                        elif resp.status_code in (403, 429):
                            logger.warning("github_rate_limit", owner=owner, repo=repo)
                            content["github_stars"] = content.get("github_stars") or 0
                        else:
                            content["github_stars"] = 0
                    except Exception as e:
                        logger.error("github_api_error", owner=owner, repo=repo, error=str(e))
                        content["github_stars"] = content.get("github_stars") or 0
            else:
                content["github_stars"] = 0
        else:
            content["github_stars"] = 0

        record["content"] = content
        return record

    async with httpx.AsyncClient(timeout=30.0) as session:
        tasks = [fetch_stars(session, rec) for rec in records]
        hydrated = await asyncio.gather(*tasks)

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in hydrated:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        "hydration_completed",
        total=total,
        with_github=with_github,
        stars_populated=stars_populated,
    )


if __name__ == "__main__":
    asyncio.run(hydrate_stars())
