import json
import os
from pathlib import Path

from dotenv import load_dotenv
import gspread
import structlog

load_dotenv()
logger = structlog.get_logger(__name__)

SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = "credentials.json"

TAB_SCHEMAS = {
    "Startups": {
        "file": "data/processed/startups.jsonl",
        "headers": ["Entity Name", "Source URL", "Employee Count", "Collected At"],
        "extractor": lambda d: [
            d.get("content", {}).get("entityName", ""),
            d.get("source", {}).get("url", ""),
            str(d.get("content", {}).get("data", {}).get("employeeCount") or ""),
            d.get("collectedAt", ""),
        ],
    },
    "Products": {
        "file": "data/processed/products.jsonl",
        "headers": ["Product / Startup Name", "Pricing Model", "Source URL", "Collected At"],
        "extractor": lambda d: [
            d.get("content", {}).get("startupName", ""),
            str(d.get("content", {}).get("pricingModel") or "UNSPECIFIED"),
            d.get("source", {}).get("url", ""),
            d.get("collectedAt", ""),
        ],
    },
    "Research Papers": {
        "file": "data/processed/research_papers.jsonl",
        "headers": ["Title", "Paper URL", "GitHub URL", "GitHub Stars", "Published Date"],
        "extractor": lambda d: [
            d.get("content", {}).get("title", ""),
            d.get("content", {}).get("paper_url", ""),
            d.get("content", {}).get("github_url") or "",
            str(d.get("content", {}).get("github_stars") or ""),
            d.get("content", {}).get("published_date", ""),
        ],
    },
    "Jobs": {
        "file": "data/processed/jobs.jsonl",
        "headers": ["Job Title", "Company", "Role Family", "Is Remote", "Posting URL", "Posted Date"],
        "extractor": lambda d: [
            d.get("content", {}).get("title", ""),
            d.get("content", {}).get("company", ""),
            d.get("content", {}).get("role_family") or "Unclassified",
            str(d.get("content", {}).get("is_remote", "")),
            d.get("content", {}).get("job_url", ""),
            d.get("content", {}).get("date", ""),
        ],
    },
    "News": {
        "file": "data/processed/news.jsonl",
        "headers": ["Headline", "Source Outlet", "Article URL", "Published Date"],
        "extractor": lambda d: [
            d.get("content", {}).get("title", ""),
            d.get("source", {}).get("name", ""),
            d.get("source", {}).get("url", ""),
            d.get("content", {}).get("published_date", ""),
        ],
    },
    "Entity Mapping Log": {
        "file": "data/processed/entity_mapping_log.jsonl",
        "headers": ["Raw Name", "Canonical Name", "Entity Type", "Resolution Method", "Confidence Score", "Source URL"],
        "extractor": lambda d: [
            d.get("raw_name", ""),
            d.get("canonical_name", ""),
            d.get("entity_type", ""),
            d.get("resolution_method", ""),
            str(d.get("confidence_score", "")),
            d.get("source_url", ""),
        ],
    },
}

def export_to_google_sheets():
    if not SPREADSHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID not set in .env file.")
        
    if not Path(CREDENTIALS_FILE).exists():
        raise FileNotFoundError(f"{CREDENTIALS_FILE} not found in root directory.")

    print(f"Authenticating with Service Account: sheets-exporter@gen-lang-client-0987342723...")
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    print(f"Connected to Spreadsheet: '{sh.title}'\n")

    for tab_name, cfg in TAB_SCHEMAS.items():
        file_path = Path(cfg["file"])
        if not file_path.exists():
            print(f"⚠️ Warning: Dataset file not found: {file_path}. Skipping tab '{tab_name}'.")
            continue
            
        rows = [cfg["headers"]]
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        record = json.loads(line_str)
                        rows.append(cfg["extractor"](record))
                    except Exception as err:
                        logger.warning("row_extraction_failed", tab=tab_name, error=str(err))
                        continue

        try:
            ws = sh.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab_name, rows=len(rows) + 50, cols=len(cfg["headers"]) + 2)

        ws.clear()
        ws.update(values=rows, range_name="A1")
        print(f"Successfully uploaded {len(rows) - 1} records to tab: '{tab_name}'")

    try:
        default_sheet = sh.worksheet("Sheet1")
        if len(sh.worksheets()) > 1:
            sh.del_worksheet(default_sheet)
    except gspread.WorksheetNotFound:
        pass

    print("\n Export complete. Verify your public link in an incognito window.")

if __name__ == "__main__":
    export_to_google_sheets()
