from datetime import datetime, timedelta, timezone
import json


def verify_freshness(path: str, date_field_path: list[str], hours: int = 24):
    violations = []
    total = 0
    now = datetime.now(timezone.utc)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            record = json.loads(line)
            node = record
            for key in date_field_path:
                node = node.get(key, {})

            try:
                published = datetime.fromisoformat(node.replace("Z", "+00:00"))
                delta = now - published
                if delta > timedelta(hours=hours) or delta < -timedelta(minutes=15):
                    violations.append(record.get("content", {}))
            except Exception:
                violations.append(record.get("content", {}))

    print(f"{path}: {total} records evaluated, {len(violations)} violations.")
    if violations:
        print("Sample violations:", violations[:3])
    return total, violations


if __name__ == "__main__":
    verify_freshness("data/processed/news.jsonl", ["content", "published_date"])
    verify_freshness("data/processed/jobs.jsonl", ["content", "date"])
