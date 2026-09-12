import asyncio
import json
import aiosqlite
import structlog

from src.models.schemas import ResearchPaperEntity, StartupEntity, ProductEntity, JobEntity

logger = structlog.get_logger(__name__)


class SQLiteStore:
    def __init__(self, db_path: str = "data/processed/staging.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def insert_record(self, record: ResearchPaperEntity | StartupEntity | ProductEntity | JobEntity) -> bool:
        if isinstance(record, ResearchPaperEntity):
            record_id = f"paper_{record.source.url}"
        elif isinstance(record, StartupEntity):
            record_id = f"startup_{record.content.entityName.lower().replace(' ', '_')}"
        elif isinstance(record, ProductEntity):
            record_id = f"product_{record.content.startupName.lower().replace(' ', '_')}"
        elif isinstance(record, JobEntity):
            import hashlib
            composite_key = f"{record.content.title}|{record.content.company}".lower().strip()
            record_id = "job_" + hashlib.sha256(composite_key.encode('utf-8')).hexdigest()
        else:
            record_id = str(id(record))

        payload_json = record.model_dump_json()

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                try:
                    await db.execute(
                        "INSERT INTO records (record_id, record_type, payload) VALUES (?, ?, ?)",
                        (record_id, record.recordType, payload_json)
                    )
                    await db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False

    async def flush_to_jsonl(self, output_path: str, record_type: str):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT payload FROM records WHERE record_type = ?", (record_type,)
                ) as cursor:
                    with open(output_path, "w", encoding="utf-8") as f:
                        async for row in cursor:
                            f.write(row[0] + "\n")
