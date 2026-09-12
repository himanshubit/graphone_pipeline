import json
import re
from typing import Optional
from rapidfuzz import fuzz, process
import structlog
from pydantic import BaseModel, Field

from src.models.schemas import EntityMappingRecord, MatchMethod
from src.llm.orchestrator import LLMOrchestrator

logger = structlog.get_logger(__name__)

SUFFIX_REGEX = re.compile(
    r"\b(inc|incorporated|llc|corp|corporation|technologies|technology|tech|labs|lab|ai|ltd|limited|solutions|group|holdings|io)\b",
    re.IGNORECASE
)

def clean_entity_name(name: str) -> str:
    """Strips corporate suffixes and non-alphanumeric noise."""
    no_punct = re.sub(r"[^\w\s]", " ", name)
    no_suffix = SUFFIX_REGEX.sub(" ", no_punct)
    return re.sub(r"\s+", " ", no_suffix).strip().lower()

class TiebreakResult(BaseModel):
    is_match: bool = Field(...)
    matched_canonical_name: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class EntityCanonicalizer:
    def __init__(self, orchestrator: Optional[LLMOrchestrator] = None):
        self.orchestrator = orchestrator or LLMOrchestrator()
        self.exact_map: dict[str, tuple[str, str]] = {}
        self.canonical_names: list[str] = []
        self.cleaned_to_canonical: dict[str, str] = {}
        self.name_to_type: dict[str, str] = {}

    def load_canonical_entities(
        self,
        startups_path: str = "data/processed/startups.jsonl",
        products_path: str = "data/processed/products.jsonl"
    ):
        with open(startups_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                name = rec["content"]["entityName"].strip()
                cleaned = clean_entity_name(name)
                self.exact_map[cleaned] = (name, "STARTUP")
                if name not in self.name_to_type:
                    self.name_to_type[name] = "STARTUP"
                    self.canonical_names.append(name)
                    self.cleaned_to_canonical[cleaned] = name

        with open(products_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                name = rec["content"]["startupName"].strip()
                cleaned = clean_entity_name(name)
                self.exact_map[cleaned] = (name, "PRODUCT")
                if name not in self.name_to_type:
                    self.name_to_type[name] = "PRODUCT"
                    self.canonical_names.append(name)
                    self.cleaned_to_canonical[cleaned] = name

    async def resolve_entity(
        self, raw_name: str, source_url: str, context_text: str = ""
    ) -> Optional[EntityMappingRecord]:
        raw_clean = raw_name.strip()
        cleaned_raw = clean_entity_name(raw_clean)

        if not cleaned_raw or len(cleaned_raw) < 2:
            return None

        # Stage 1: Exact Normalized Match
        if cleaned_raw in self.exact_map:
            canon_name, ent_type = self.exact_map[cleaned_raw]
            return EntityMappingRecord(
                raw_name=raw_clean,
                canonical_name=canon_name,
                entity_type=ent_type,
                resolution_method=MatchMethod.EXACT,
                confidence_score=1.0,
                source_url=source_url,
            )

        # Stage 2: Token-Set Distance Matching
        best_matches = process.extract(
            cleaned_raw,
            list(self.cleaned_to_canonical.keys()),
            scorer=fuzz.token_set_ratio,
            limit=3
        )

        if not best_matches:
            return None

        top_cleaned_cand, top_score, _ = best_matches[0]
        canonical_target = self.cleaned_to_canonical[top_cleaned_cand]

        # Auto-accept high-confidence lexical matches (>= 82.0)
        if top_score >= 82.0:
            return EntityMappingRecord(
                raw_name=raw_clean,
                canonical_name=canonical_target,
                entity_type=self.name_to_type[canonical_target],
                resolution_method=MatchMethod.FUZZY,
                confidence_score=round(float(top_score) / 100.0, 2),
                source_url=source_url,
            )

        # Stage 3: LLM Tiebreak (Ambiguous Band: 70.0 <= score < 82.0)
        if 70.0 <= top_score < 82.0:
            candidates = [self.cleaned_to_canonical[m[0]] for m in best_matches]
            prompt = (
                f"Determine whether raw entity '{raw_clean}' refers to any of: {candidates}.\n"
                f"Context: \"{context_text[:300]}\"\n"
                "Return valid JSON: {\"is_match\": bool, \"matched_canonical_name\": str|null, \"confidence\": float}"
            )
            try:
                res, _ = await self.orchestrator.extract_with_fallback(prompt, TiebreakResult)
                if res.is_match and res.matched_canonical_name in self.name_to_type:
                    return EntityMappingRecord(
                        raw_name=raw_clean,
                        canonical_name=res.matched_canonical_name,
                        entity_type=self.name_to_type[res.matched_canonical_name],
                        resolution_method=MatchMethod.LLM_TIEBREAK,
                        confidence_score=round(res.confidence, 2),
                        source_url=source_url,
                    )
            except Exception:
                return None

        return None
