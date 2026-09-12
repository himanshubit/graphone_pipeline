import asyncio
from collections import defaultdict
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import structlog

load_dotenv()

from src.graph.resolver import EntityCanonicalizer
from src.llm.orchestrator import LLMOrchestrator

logger = structlog.get_logger(__name__)

async def main():
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    orchestrator = LLMOrchestrator()
    canonicalizer = EntityCanonicalizer(orchestrator)
    canonicalizer.load_canonical_entities()
    
    stats = defaultdict(int)
    seen_mappings: set[tuple[str, str]] = set()
    output_path = "data/processed/entity_mapping_log.jsonl"
    
    sem = asyncio.Semaphore(5)

    async def process_candidate(raw_str: str, source_url: str, context: str, out_file):
        async with sem:
            mapping = await canonicalizer.resolve_entity(raw_str, source_url, context)
            if mapping:
                dedup_key = (mapping.raw_name.lower(), mapping.canonical_name.lower())
                if dedup_key not in seen_mappings:
                    seen_mappings.add(dedup_key)
                    out_file.write(mapping.model_dump_json() + "\n")
                    out_file.flush()
                    stats[mapping.resolution_method.value] += 1
                    stats["total_mapped"] += 1
            else:
                stats["unresolved_or_discarded"] += 1

    with open(output_path, "w", encoding="utf-8") as out_f:
        tasks = []

        jobs_path = Path("data/processed/jobs.jsonl")
        if jobs_path.exists():
            with open(jobs_path, "r", encoding="utf-8") as jf:
                for line in jf:
                    if not line.strip():
                        continue
                    job = json.loads(line)
                    company = job["content"]["company"]
                    url = job["source"]["url"]
                    title = job["content"]["title"]
                    tasks.append(process_candidate(company, url, f"Job Posting: {title}", out_f))

        news_path = Path("data/processed/news.jsonl")
        if news_path.exists():
            with open(news_path, "r", encoding="utf-8") as nf:
                for line in nf:
                    if not line.strip():
                        continue
                    news = json.loads(line)
                    headline = news["content"]["title"]
                    body = news["content"]["body"]
                    url = news["source"]["url"]
                    candidate_token = headline.split(":")[0].split("—")[0].strip()
                    tasks.append(process_candidate(candidate_token, url, body[:400], out_f))

        logger.info("processing_candidate_entities", total_candidates=len(tasks))
        await asyncio.gather(*tasks)

    print("\n================== PHASE 4 CANONICALIZATION SUMMARY ==================")
    print(f"Total Unique Entities Mapped: {stats['total_mapped']}")
    print(f" - Exact Matches: {stats['EXACT']}")
    print(f" - Fuzzy Matches: {stats['FUZZY']}")
    print(f" - LLM Tiebreak: {stats['LLM_TIEBREAK']}")
    print(f"Unresolved/Discarded: {stats['unresolved_or_discarded']}")
    print(f"Artifact Saved: {output_path}")
    print("======================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
