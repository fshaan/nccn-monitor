# NCCN Watcher

NCCN 指南更新监控工具 — MCP Server for OpenClaw.

## Architecture

Python MCP Server exposing 3 tools: `check_updates`, `get_status`, `list_guidelines`.
OpenClaw calls these via MCP protocol (stdio transport).

## Key Modules

- `src/nccn_watcher/scraper.py` — Scrape all 4 NCCN category pages (92 guidelines)
- `src/nccn_watcher/state.py` — JSON-based version state tracking
- `src/nccn_watcher/downloader.py` — NCCN login + PDF download (adapted from gscfwid/NCCN_guidelines_MCP)
- `src/nccn_watcher/analyzer.py` — PDF update notes extraction + AI summary prompt
- `src/nccn_watcher/health.py` — Health check / silent failure detection
- `src/nccn_watcher/guideline_names.py` — Chinese name mapping + fuzzy search for all 92 guidelines
- `src/nccn_watcher/server.py` — MCP server entry point (6 tools)

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Test directory: `tests/`
Fixtures: `tests/fixtures/`

## Configuration

Copy `config.example.yaml` to `config.yaml` and set NCCN credentials.
Or use env vars: `NCCN_USERNAME`, `NCCN_PASSWORD`.
