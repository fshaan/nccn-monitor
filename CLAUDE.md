# NCCN Monitor

NCCN 指南更新监控工具 — MCP Server for OpenClaw.

## Architecture

Python MCP Server exposing 6 tools via MCP protocol (stdio transport).
OpenClaw or any MCP-compatible client can call these tools.

Core tools: `check_updates`, `get_status`, `list_guidelines`
Config tools: `find_guideline`, `update_watch_list`, `browse_guidelines`

## Key Modules

- `src/nccn_monitor/scraper.py` — Scrape all 4 NCCN category pages (92 guidelines)
- `src/nccn_monitor/state.py` — JSON-based version state tracking
- `src/nccn_monitor/downloader.py` — NCCN login + PDF download (adapted from gscfwid/NCCN_guidelines_MCP)
- `src/nccn_monitor/analyzer.py` — PDF update notes extraction + AI summary prompt
- `src/nccn_monitor/health.py` — Health check / silent failure detection
- `src/nccn_monitor/guideline_names.py` — Chinese name mapping + fuzzy search for all 92 guidelines
- `src/nccn_monitor/server.py` — MCP server entry point (6 tools)
- `openclaw-plugin/` — Native OpenClaw plugin (TypeScript wrapper for MCP bridge)

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
