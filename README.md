# GraphOne / FrontierAtlas

This repository contains the GraphOne / FrontierAtlas pipeline.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (The exclusive package and environment manager used in this project)

## Setup & Installation

Navigate to the main project directory and install the dependencies using `uv`:

```bash
cd graphone-pipeline
uv sync
```

## Running the Pipeline

The project is split into several execution phases. From within the `graphone_pipeline` directory, you can run the following commands:

**Phase 1: Products Ingestion**
```bash
uv run python src/main_phase1.py
```

**Phase 2: Jobs Pipeline & Data Deduplication**
```bash
uv run python src/main_phase2.py
```

**Phase 4: Final Deployment & Sheets Export**
Once all intermediate pipelines have successfully run, export the final data to Google Sheets:
```bash
uv run python src/storage/sheets_export.py
```

*(Refer to `AGENT_REMEDIATION_RUNBOOK.md` and `architecture.md` for more detailed information about troubleshooting and the architecture.)*
