import json
from src.models.schemas import EntityMappingRecord

def verify_mapping_log(path: str = "data/processed/entity_mapping_log.jsonl"):
    total = 0
    passed = 0
    failures = []

    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            total += 1
            try:
                record = EntityMappingRecord.model_validate_json(line.strip())
                assert record.confidence_score >= 0.0 and record.confidence_score <= 1.0
                assert len(record.canonical_name) > 0
                assert record.source_url.startswith("http")
                passed += 1
            except Exception as e:
                failures.append((idx, str(e)))

    print(f"Audit Summary for {path}:")
    print(f"  Total Evaluated: {total}")
    print(f"  Schema Compliant: {passed}")
    print(f"  Validation Violations: {len(failures)}")

    if failures:
        print("Sample Violations:")
        for line_num, err in failures[:3]:
            print(f"  Line {line_num}: {err}")

if __name__ == "__main__":
    verify_mapping_log()
