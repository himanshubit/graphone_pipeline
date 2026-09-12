"""
Research Papers Crawler (Arxiv)
BEHAVIOR: This crawler uses a hard `max_records` limit (early-stop condition).
It paginates the Arxiv API until it reaches `max_records` successfully parsed entities, and then forcibly halts.
"""

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import AsyncGenerator
from selectolax.parser import HTMLParser
from src.core.client import AsyncScraperClient
from src.models.schemas import ResearchPaperEntity, ResearchPaperContent, SourceMetadata
from src.scrapers.github_enricher import GitHubEnricher

class ResearchPapersCrawler:
    def __init__(self, enricher: GitHubEnricher):
        self.enricher = enricher

    async def crawl_arxiv_bulk(
        self, client: AsyncScraperClient, max_records: int = 1200
    ) -> AsyncGenerator[ResearchPaperEntity, None]:
        categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV"]
        records_per_query = 100
        total_yielded = 0
        import structlog
        logger = structlog.get_logger(__name__)

        for cat in categories:
            start_index = 0
            consecutive_errors = 0
            while total_yielded < max_records:
                query_url = (
                    f"https://export.arxiv.org/api/query?"
                    f"search_query=cat:{cat}&start={start_index}&max_results={records_per_query}"
                    f"&sortBy=submittedDate&sortOrder=descending"
                )
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=60.0) as http_client:
                        response = await http_client.get(query_url)
                        response.raise_for_status()
                        xml_raw = response.text
                    root = ET.fromstring(xml_raw)
                    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
                    entries = root.findall("atom:entry", ns)
                    if not entries:
                        break

                    for entry in entries:
                        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                        paper_url = entry.find("atom:id", ns).text.strip()
                        pub_date_str = entry.find("atom:published", ns).text.strip()
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
                        summary = entry.find("atom:summary", ns).text or ""
                        
                        github_url = None
                        github_stars = None
                        import re
                        github_match = re.search(r'https?://github\.com/[^\s\)]+', summary)
                        if github_match:
                            github_url = github_match.group(0).rstrip('.,')
                            if client.session:
                                github_stars = await self.enricher.get_stars(client.session, github_url)

                        entity = ResearchPaperEntity(
                            source=SourceMetadata(name="Arxiv", url=paper_url),
                            content=ResearchPaperContent(
                                title=title,
                                authors=authors,
                                paper_url=paper_url,
                                github_url=github_url,
                                github_stars=github_stars,
                                published_date=pub_date
                            )
                        )
                        yield entity
                        total_yielded += 1
                        if total_yielded >= max_records:
                            return
                    
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    logger.error("arxiv_batch_failed", error=str(e), start_index=start_index, cat=cat)
                    if consecutive_errors > 3:
                        logger.error("arxiv_permanent_failure", cat=cat)
                        break
                    
                    await asyncio.sleep(10.0)
                    continue
                        
                start_index += records_per_query
                await asyncio.sleep(5.0)

    async def crawl_papers_with_code(
        self, client: AsyncScraperClient, max_records: int = 500
    ) -> AsyncGenerator[ResearchPaperEntity, None]:
        page = 1
        yielded = 0
        while yielded < max_records:
            url = f"https://paperswithcode.co/papers/recent?page={page}"
            try:
                html = await client.fetch(url)
            except Exception:
                break
                
            parser = HTMLParser(html)
            cards = parser.css("div.paper-card")
            if not cards:
                break

            for card in cards:
                title_node = card.css_first("h1 a, h2 a, h3 a")
                if not title_node:
                    continue
                title = title_node.text(strip=True)
                relative_link = title_node.attributes.get("href", "")
                paper_detail_url = f"https://paperswithcode.co{relative_link}"
                
                try:
                    detail_html = await client.fetch(paper_detail_url)
                    detail_parser = HTMLParser(detail_html)
                    code_link = detail_parser.css_first("a[href*='github.com']")
                    github_url = code_link.attributes.get("href") if code_link else None
                    
                    stars = None
                    if github_url and client.session:
                        stars = await self.enricher.get_stars(client.session, github_url)

                    yield ResearchPaperEntity(
                        source=SourceMetadata(name="PapersWithCode", url=paper_detail_url),
                        content=ResearchPaperContent(
                            title=title,
                            authors=[],
                            paper_url=paper_detail_url,
                            github_url=github_url,
                            github_stars=stars,
                            published_date=datetime.utcnow()
                        )
                    )
                    yielded += 1
                    if yielded >= max_records:
                        return
                except Exception:
                    continue
            page += 1
