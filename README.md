# NCCN Watcher

Monitor NCCN clinical guideline updates and get notified when new versions are published.

NCCN (National Comprehensive Cancer Network) publishes clinical practice guidelines for 92 cancer types and supportive care topics. These guidelines are updated frequently, and keeping track of changes is important for oncologists, researchers, and pharmaceutical professionals.

NCCN Watcher tracks version changes across all 92 NCCN professional guidelines, downloads updated PDFs, extracts update notes, and generates AI-powered change summaries — all accessible through the MCP protocol for integration with OpenClaw or any MCP-compatible AI assistant.

## Features

- **Complete coverage** — monitors all 92 NCCN professional guidelines across 4 categories (Cancer by Type, Screening, Supportive Care, Specific Populations)
- **Version change detection** — compares current versions against stored state, detects updates
- **PDF download + analysis** — logs into NCCN (free registration), downloads updated PDFs, extracts update notes from the first few pages
- **AI-powered summaries** — generates structured prompts for LLM-based change analysis (Chinese or English)
- **Health monitoring** — detects silent scraping failures and alerts after consecutive errors
- **Chinese language support** — all 92 guidelines have Chinese names and aliases for fuzzy search
- **Watch list management** — configure which guidelines to monitor via natural language (Chinese or English)

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- NCCN account (free registration at [nccn.org](https://www.nccn.org))

### Install

```bash
git clone https://github.com/fshaan/nccn-watcher.git
cd nccn-watcher
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to set your NCCN credentials and watch list. Or use environment variables:

```bash
export NCCN_USERNAME="your_email@example.com"
export NCCN_PASSWORD="your_password"
```

### Run

```bash
# Start the MCP server (stdio transport)
python -m nccn_watcher.server

# Run unit tests
python -m pytest tests/ -v

# Run integration test (needs NCCN credentials)
python tests/integration_test.py
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_updates` | Check all guidelines for version updates, download PDFs, generate change reports |
| `get_status` | Return health status, last check time, tracked guideline count |
| `list_guidelines` | List all 92 NCCN guidelines with versions and Chinese names |
| `find_guideline` | Fuzzy search by Chinese name, English name, or abbreviation |
| `update_watch_list` | Add/remove/set monitored guidelines via natural language |
| `browse_guidelines` | Browse all guidelines organized by category |

## OpenClaw Integration

Add this MCP server to your OpenClaw configuration:

```json
{
  "mcpServers": {
    "nccn-watcher": {
      "command": "python",
      "args": ["-m", "nccn_watcher.server"],
      "cwd": "/path/to/nccn-watcher"
    }
  }
}
```

Then set up a cron job in OpenClaw to call `check_updates` daily.

## Architecture

```
OpenClaw (cron + notifications)
    │
    │ MCP Protocol (stdio)
    ▼
┌─────────────────────────────────────┐
│      NCCN Watcher MCP Server        │
│                                     │
│  scraper ──→ state ──→ notifier     │
│     │                               │
│     ▼ (on version change)           │
│  downloader ──→ analyzer            │
│  (NCCN login)   (PDF extraction)    │
└─────────────────────────────────────┘
```

## Credits

- NCCN login and PDF download logic adapted from [gscfwid/NCCN_guidelines_MCP](https://github.com/gscfwid/NCCN_guidelines_MCP)
- Built with [FastMCP](https://github.com/jlowin/fastmcp) for MCP server implementation

## License

MIT
