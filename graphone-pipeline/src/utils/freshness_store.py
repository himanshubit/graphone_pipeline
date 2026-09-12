import json
from pathlib import Path


class FreshnessStore:
    def __init__(self, path: str = "data/processed/last_seen_urls.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if self.path.exists():
            try:
                self._seen = set(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                self._seen = set()

    def is_new(self, url: str) -> bool:
        return url not in self._seen

    def mark_seen(self, url: str):
        self._seen.add(url)

    def persist(self):
        self.path.write_text(json.dumps(sorted(self._seen), indent=2), encoding="utf-8")
