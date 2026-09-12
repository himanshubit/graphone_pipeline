import re
from typing import Optional
from curl_cffi.requests import AsyncSession
import structlog

logger = structlog.get_logger(__name__)

class GitHubEnricher:
    def __init__(self, github_token: Optional[str] = None):
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"

    @staticmethod
    def extract_repo_path(github_url: str) -> Optional[tuple[str, str]]:
        match = re.search(r"github\.com/([^/]+)/([^/#?]+)", github_url)
        if match:
            owner, repo = match.group(1), match.group(2)
            return owner, repo.removesuffix(".git")
        return None

    async def get_stars(self, session: AsyncSession, github_url: str) -> Optional[int]:
        parsed = self.extract_repo_path(github_url)
        if not parsed:
            return None
        owner, repo = parsed
        endpoint = f"https://api.github.com/repos/{owner}/{repo}"
        
        try:
            response = await session.get(endpoint, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("stargazers_count")
            elif response.status_code == 404:
                return None
            elif response.status_code in (403, 429):
                logger.warn("github_rate_limit_reached", owner=owner, repo=repo)
                return None
        except Exception as e:
            logger.error("github_enrichment_error", url=github_url, error=str(e))
            return None
        return None
