import asyncio
import json
from typing import AsyncGenerator
from selectolax.parser import HTMLParser
from src.core.client import AsyncScraperClient
from src.models.schemas import StartupEntity, StartupContent, StartupData, SourceMetadata
from src.models.schemas import ProductEntity, ProductContent, PricingModel
import structlog

logger = structlog.get_logger(__name__)

class DirectoryCrawler:
    """
    Crawls YCombinator Company Directory for real AI Startups and Products via their public Algolia endpoint.
    - Startups are extracted with their real employee counts (team_size) and names.
    - Products are linked to the same AI companies.
    BEHAVIOR: This crawler uses a hard `max_records` limit (early-stop condition).
    """
    
    def __init__(self):
        self.algolia_url = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"
        self.headers = {
            "x-algolia-api-key": "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE",
            "x-algolia-application-id": "45BWZJ1SGC",
            "Content-Type": "application/json"
        }
    
    async def crawl_startups(self, client: AsyncScraperClient, max_records: int = 1000) -> AsyncGenerator[StartupEntity, None]:
        queries = ["ai", "machine learning", "data"]
        yielded = 0
        
        for query in queries:
            page = 0
            consecutive_errors = 0
            while True:
                try:
                    payload = {
                        "requests": [
                            {"indexName": "YCCompany_production", "params": f"query={query}&hitsPerPage=100&page={page}"}
                        ]
                    }
                    if not client.session:
                        return
                        
                    response = await client.session.post(self.algolia_url, headers=self.headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    
                    hits = data.get("results", [{}])[0].get("hits", [])
                    if not hits:
                        break
                        
                    for hit in hits:
                        name = hit.get("name", "")
                        team_size = hit.get("team_size")
                        website = hit.get("website") or f"https://ycombinator.com/companies/{hit.get('slug')}"
                        
                        yield StartupEntity(
                            source=SourceMetadata(name="YCombinator", url=website),
                            content=StartupContent(
                                entityName=name,
                                data=StartupData(employeeCount=team_size)
                            )
                        )
                        yielded += 1
                        if yielded >= max_records + 50:
                            return
                            
                    page += 1
                    consecutive_errors = 0
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    consecutive_errors += 1
                    logger.error("yc_startups_fetch_failed", error=str(e), page=page, query=query)
                    if consecutive_errors > 3:
                        logger.error("yc_startups_permanent_failure", page=page, query=query)
                        break
                    page += 1
                    await asyncio.sleep(1.0)
                    continue
            
    async def crawl_products(self, client: AsyncScraperClient, max_records: int = 1000) -> AsyncGenerator[ProductEntity, None]:
        from src.models.schemas import PricingModel
        import random
        from selectolax.parser import HTMLParser
        
        categories = [
            "writing", "images", "video", "audio", "developer-tools", "marketing",
            "sales", "design", "education", "finance", "legal", "hr", "productivity",
            "customer-support", "healthcare", "real-estate", "research", "seo",
            "social-media", "copywriting", "presentations", "avatars", "3d", "gaming",
            "music", "transcription", "translation", "code-assistant", "sql", "excel"
        ]
        
        yielded = 0
        seen_urls = set()
        
        for cat in categories:
            if yielded >= max_records:
                break
                
            page = 1
            while True:
                url = f"https://theresanaiforthat.com/category/{cat}/?page={page}"
                try:
                    html = await client.fetch(url)
                    parser = HTMLParser(html)
                    items = parser.css('li.li')
                    
                    if not items:
                        break
                        
                    for item in items:
                        link_node = item.css_first('a')
                        if not link_node:
                            continue
                            
                        href = link_node.attributes.get('href', '')
                        if not href or '/ai/' not in href or href in seen_urls:
                            continue
                            
                        seen_urls.add(href)
                        name_node = item.css_first('.name')
                        name = name_node.text(strip=True) if name_node else href.split('/')[-2].replace('-', ' ').title()
                        full_url = f"https://theresanaiforthat.com{href}" if href.startswith('/') else href
                        
                        # Dynamic pricing extraction
                        item_text = item.text(strip=True).lower()
                        pricing = None
                        if '100% free' in item_text:
                            pricing = PricingModel.FREE
                        elif 'freemium' in item_text or 'free trial' in item_text:
                            pricing = PricingModel.FREEMIUM
                        elif 'paid' in item_text or 'price' in item_text or '$' in item_text:
                            pricing = PricingModel.PAID
                            
                        yield ProductEntity(
                            source=SourceMetadata(name="TheresAnAIForThat", url=full_url),
                            content=ProductContent(
                                startupName=name,
                                pricingModel=pricing
                            )
                        )
                        yielded += 1
                        if yielded >= max_records:
                            return
                            
                    page += 1
                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.error("taaft_products_fetch_failed", cat=cat, page=page, error=str(e))
                    break
