import json
import random
import asyncio
from curl_cffi.requests import AsyncSession
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)

async def check_url(session, record, record_type):
    url = record.get("source", {}).get("url")
    if not url:
        return {"status": "DEAD_LINK", "reason": "No URL found"}
        
    try:
        response = await session.get(url, timeout=10, impersonate="chrome120")
        if response.status_code >= 400:
            return {"status": "DEAD_LINK", "reason": f"HTTP {response.status_code}"}
            
        content = response.text.lower()
        
        search_term = ""
        if record_type == "STARTUP":
            search_term = record.get("content", {}).get("entityName", "").lower()
        elif record_type == "PRODUCT":
            search_term = record.get("content", {}).get("startupName", "").lower()
        elif record_type == "RESEARCH_PAPER":
            search_term = record.get("content", {}).get("title", "").lower()
            
        if search_term and search_term not in content:
            # Partial match on first two words handles truncated titles in HTML
            words = search_term.split()
            if len(words) > 2 and " ".join(words[:2]) in content:
                pass
            else:
                return {"status": "CONTENT_MISMATCH", "reason": f"Could not find '{search_term}' in content"}
                
        return {"status": "OK", "reason": ""}
    except Exception as e:
        return {"status": "DEAD_LINK", "reason": str(e)}

async def main():
    files_to_check = {
        "STARTUP": "data/processed/startups.jsonl",
        "PRODUCT": "data/processed/products.jsonl",
        "RESEARCH_PAPER": "data/processed/research_papers.jsonl"
    }
    
    report = {"summary": {"total_checked": 0, "passed": 0, "flagged": 0}, "records": []}
    
    async with AsyncSession() as session:
        for r_type, filepath in files_to_check.items():
            if not Path(filepath).exists():
                logger.warning("file_not_found", filepath=filepath)
                continue
                
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            if not lines:
                continue
                
            sample_size = min(20, len(lines))
            samples = random.sample(lines, sample_size)
            
            for line in samples:
                record = json.loads(line)
                url = record.get("source", {}).get("url", "")
                
                logger.info("spot_check", record_type=r_type, url=url)
                result = await check_url(session, record, r_type)
                
                report_item = {
                    "type": r_type,
                    "url": url,
                    "status": result["status"],
                    "reason": result["reason"]
                }
                report["records"].append(report_item)
                
                report["summary"]["total_checked"] += 1
                if result["status"] == "OK":
                    report["summary"]["passed"] += 1
                else:
                    report["summary"]["flagged"] += 1
                    
                await asyncio.sleep(0.5) # respect rate limits during check
                
    with open("verification_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"\nVerification Complete: {report['summary']['passed']}/{report['summary']['total_checked']} passed, {report['summary']['flagged']} flagged.")

if __name__ == "__main__":
    asyncio.run(main())
