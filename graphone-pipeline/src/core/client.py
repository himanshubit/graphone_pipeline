from typing import Optional
from curl_cffi.requests import AsyncSession
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import structlog

from src.core.exceptions import AntiBotChallengeError, NetworkFetchError

logger = structlog.get_logger(__name__)


class AsyncScraperClient:
    def __init__(self, impersonate: str = "chrome120", timeout: int = 20):
        self.impersonate = impersonate
        self.timeout = timeout
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self):
        self.session = AsyncSession(
            impersonate=self.impersonate,
            timeout=self.timeout,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def fetch(self, url: str) -> str:
        if not self.session:
            raise RuntimeError("AsyncScraperClient must be used as an async context manager.")
        try:
            response = await self.session.get(url)
            if response.status_code in (403, 503):
                body = response.text.lower()
                if "just a moment" in body or "cf-mitigated" in body or "turnstile" in body:
                    raise AntiBotChallengeError(f"Anti-bot challenge encountered at: {url}")

            response.raise_for_status()
            return response.text
        except AntiBotChallengeError:
            raise
        except Exception as err:
            logger.warning("fetch_failed", url=url, error=str(err))
            raise NetworkFetchError(f"Failed to fetch {url}: {err}") from err
