"""NCCN Watcher MCP Server — entry point for OpenClaw integration."""

import os
import logging
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from .scraper import fetch_all_guidelines, fetch_recently_published, ScrapeError
from .state import StateManager
from .downloader import NCCNDownloader
from .analyzer import extract_update_notes, build_summary_prompt
from .health import HealthTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path.home() / ".nccn-watcher" / "config.yaml",
]


def load_config() -> dict:
    """Load config from file or environment variables."""
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            with open(path) as f:
                logger.info("Loaded config from %s", path)
                return yaml.safe_load(f)

    # Fallback: build config from environment variables
    return {
        "nccn": {
            "username": os.getenv("NCCN_USERNAME", ""),
            "password": os.getenv("NCCN_PASSWORD", ""),
        },
        "watch_list": [],
        "analysis": {
            "enabled": True,
            "update_notes_pages": 5,
            "language": "zh-CN",
        },
        "state_file": "~/.nccn-watcher/state.json",
        "cache_dir": "~/.nccn-watcher/cache",
    }


# ── Initialize ───────────────────────────────────────────────────────

config = load_config()
mcp = FastMCP("nccn-watcher")
state_mgr = StateManager(config.get("state_file", "~/.nccn-watcher/state.json"))
health = HealthTracker("~/.nccn-watcher/health.json")

nccn_user = config.get("nccn", {}).get("username") or os.getenv("NCCN_USERNAME", "")
nccn_pass = config.get("nccn", {}).get("password") or os.getenv("NCCN_PASSWORD", "")
downloader = NCCNDownloader(nccn_user or None, nccn_pass or None)


# ── MCP Tools ────────────────────────────────────────────────────────


@mcp.tool()
async def check_updates() -> str:
    """Check NCCN guidelines for updates and return a change report.

    This is the main tool — designed to be called on a cron schedule.
    It scrapes ALL 4 NCCN category pages (92 guidelines total),
    compares versions against stored state, and for each update:
    1. Downloads the new PDF (if NCCN credentials are configured)
    2. Extracts update notes from the first few pages
    3. Returns structured change data for AI summary generation

    Returns a human-readable report of changes found, or a status
    message if no changes detected.
    """
    watch_list = config.get("watch_list", [])
    cache_dir = config.get("cache_dir", "~/.nccn-watcher/cache")
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("update_notes_pages", 5)
    language = analysis_cfg.get("language", "zh-CN")

    try:
        # Step 1: Scrape ALL category pages for complete guideline list
        current = await fetch_all_guidelines()
        health.record_success()

        # Step 2: Detect version changes
        changes = state_mgr.detect_changes(current, watch_list or None)

        if not changes:
            return (
                f"No guideline updates detected. "
                f"Checked {len(current)} guidelines. "
                f"Last check: {state_mgr.last_check}"
            )

        # Step 3: Get PDF URLs from Recently Published page
        # Category pages only have detail URLs, not PDF URLs.
        # Recently Published page has PDF links for recently updated guidelines.
        pdf_url_map: dict[str, str] = {}
        try:
            recent = await fetch_recently_published()
            pdf_url_map = {g.name: g.detail_url for g in recent}
        except ScrapeError:
            logger.warning("Could not fetch Recently Published page for PDF URLs")

        # Step 4: For each change, try to download PDF and extract notes
        report_parts: list[str] = []
        report_parts.append(f"# NCCN Guideline Updates Detected ({len(changes)})\n")

        for change in changes:
            pdf_url = pdf_url_map.get(change.name, "")
            section = [
                f"## {change.name}",
                f"**Version**: {change.old_version} → {change.new_version}",
                f"**Category**: {change.category}",
                f"**Detail**: {change.detail_url}",
            ]
            if pdf_url:
                section.append(f"**PDF**: {pdf_url}")

            # Try PDF download + analysis if credentials available
            if analysis_cfg.get("enabled", True) and nccn_user and pdf_url:
                pdf_path = await downloader.download_pdf(pdf_url, cache_dir)
                if pdf_path:
                    notes = extract_update_notes(pdf_path, max_pages)
                    if notes:
                        prompt = build_summary_prompt(
                            change.name,
                            change.old_version,
                            change.new_version,
                            notes,
                            language,
                        )
                        section.append(f"\n### Update Notes (raw text)\n```\n{notes[:2000]}\n```")
                        section.append(f"\n### AI Summary Prompt\n{prompt}")
                    else:
                        section.append("\n*Could not extract update notes from PDF.*")
                else:
                    section.append("\n*PDF download failed. Check NCCN credentials.*")
            elif not pdf_url:
                section.append(
                    "\n*PDF URL not found on Recently Published page. "
                    "Visit the detail page to download manually.*"
                )
            else:
                section.append(
                    "\n*AI analysis skipped — configure NCCN credentials for full analysis.*"
                )

            report_parts.append("\n".join(section))

        return "\n\n---\n\n".join(report_parts)

    except ScrapeError as e:
        should_alert = health.record_failure(str(e))
        msg = f"Scrape failed: {e}"
        if should_alert:
            msg = f"⚠️ ALERT: {health.threshold}+ consecutive scrape failures! {msg}"
        return msg

    except Exception as e:
        should_alert = health.record_failure(str(e))
        msg = f"Unexpected error: {e}"
        if should_alert:
            msg = f"⚠️ ALERT: {health.threshold}+ consecutive failures! {msg}"
        return msg


@mcp.tool()
async def get_status() -> str:
    """Get the current status of the NCCN watcher.

    Returns health status, last check time, and number of tracked guidelines.
    """
    known = state_mgr.known_guidelines
    return (
        f"Health: {health.status_summary}\n"
        f"Last check: {state_mgr.last_check or 'never'}\n"
        f"Tracking: {len(known)} guidelines\n"
        f"Watch list: {config.get('watch_list', ['(all)'])}"
    )


@mcp.tool()
async def list_guidelines() -> str:
    """Fetch and list ALL NCCN professional guidelines (92+) with versions.

    Scrapes all 4 category pages. Useful for discovering available
    guideline names to add to the watch list.
    """
    try:
        guidelines = await fetch_all_guidelines()
        lines = [f"# NCCN Professional Guidelines ({len(guidelines)})\n"]
        current_cat = ""
        for g in guidelines:
            if g.category != current_cat:
                current_cat = g.category
                lines.append(f"\n## {current_cat}")
            lines.append(f"- **{g.name}** — Version {g.version}")
        return "\n".join(lines)
    except ScrapeError as e:
        return f"Failed to fetch guidelines: {e}"


# ── Entry point ──────────────────────────────────────────────────────

def main():
    logger.info("Starting NCCN Watcher MCP Server...")
    if nccn_user:
        logger.info("NCCN authentication configured for: %s", nccn_user)
    else:
        logger.warning("No NCCN credentials — PDF download and AI analysis disabled")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
