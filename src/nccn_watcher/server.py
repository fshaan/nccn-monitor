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
from .guideline_names import search_guidelines, get_zh_name, GUIDELINE_ZH

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
            zh = get_zh_name(g.name)
            lines.append(f"- **{g.name}** ({zh}) — Version {g.version}")
        return "\n".join(lines)
    except ScrapeError as e:
        return f"Failed to fetch guidelines: {e}"


@mcp.tool()
async def find_guideline(query: str) -> str:
    """Search NCCN guidelines by name in Chinese or English.

    Supports fuzzy matching. Examples:
    - "肺癌" → Non-Small Cell Lung Cancer, Small Cell Lung Cancer
    - "GIST" → Gastrointestinal Stromal Tumors
    - "lymphoma" → B-Cell Lymphomas, T-Cell Lymphomas, Hodgkin Lymphoma, ...

    Args:
        query: Search term in Chinese, English, or abbreviation.

    Returns matching guidelines with Chinese names and whether they
    are currently in the watch list.
    """
    results = search_guidelines(query)
    watch_list = config.get("watch_list", [])
    watch_set = {name.lower() for name in watch_list} if watch_list else set()

    if not results:
        return f"No guidelines found matching '{query}'. Try a different term."

    lines = [f"# Search results for '{query}' ({len(results)} matches)\n"]
    for en_name, zh_name, score in results[:15]:
        watched = "✅ 已监控" if en_name.lower() in watch_set else ""
        lines.append(f"- **{en_name}** ({zh_name}) {watched}")
    return "\n".join(lines)


@mcp.tool()
async def update_watch_list(action: str, guidelines: str) -> str:
    """Add or remove guidelines from the watch list.

    Args:
        action: "add", "remove", or "set" (replace entire list).
        guidelines: Comma-separated guideline names (English or Chinese).
                    Fuzzy matching is applied — exact names not required.

    Examples:
        action="add", guidelines="肺癌, 胃癌, GIST"
        action="remove", guidelines="Breast Cancer"
        action="set", guidelines="结肠癌, 直肠癌, 胃癌"
    """
    watch_list: list[str] = list(config.get("watch_list", []))

    # Parse input and resolve names
    queries = [q.strip() for q in guidelines.split(",") if q.strip()]
    resolved: list[str] = []
    not_found: list[str] = []

    for query in queries:
        matches = search_guidelines(query)
        if matches and matches[0][2] >= 0.4:
            resolved.append(matches[0][0])  # Best match English name
        else:
            not_found.append(query)

    if action == "add":
        for name in resolved:
            if name not in watch_list:
                watch_list.append(name)
    elif action == "remove":
        watch_list = [n for n in watch_list if n not in resolved]
    elif action == "set":
        watch_list = resolved
    else:
        return f"Unknown action '{action}'. Use 'add', 'remove', or 'set'."

    # Save to config
    config["watch_list"] = watch_list
    _save_config(config)

    # Build response
    lines = [f"Watch list updated ({action}). Now monitoring {len(watch_list)} guidelines:\n"]
    for name in watch_list:
        zh = get_zh_name(name)
        lines.append(f"- {name} ({zh})")

    if not_found:
        lines.append(f"\n⚠️ Could not resolve: {', '.join(not_found)}")
        lines.append("Use find_guideline to search for the correct name.")

    return "\n".join(lines)


@mcp.tool()
async def browse_guidelines() -> str:
    """Browse all NCCN guidelines organized by category with Chinese names.

    Returns a categorized list of all 92 guidelines with:
    - English name + Chinese name
    - Whether currently in the watch list (✅)

    Useful for discovering what guidelines are available before
    using update_watch_list to configure monitoring.
    """
    watch_list = config.get("watch_list", [])
    watch_set = {name.lower() for name in watch_list} if watch_list else set()

    categories = {
        "Cancer by Type": "肿瘤治疗（按类型）",
        "Detection, Prevention & Risk Reduction": "筛查与预防",
        "Supportive Care": "支持治疗",
        "Specific Populations": "特殊人群",
    }

    lines = ["# NCCN 指南浏览\n"]

    for cat_en, cat_zh in categories.items():
        lines.append(f"\n## {cat_zh} ({cat_en})")
        cat_guidelines = [
            (en, info) for en, info in GUIDELINE_ZH.items()
            # Match category by checking which guidelines belong to it
        ]
        # We need the actual category mapping, use scraper data
        for en_name, info in GUIDELINE_ZH.items():
            # Rough category mapping based on position in the dict
            # (the dict is ordered by category in the source)
            pass

    # Simpler approach: just list all by category from the dict ordering
    lines = ["# NCCN 指南浏览"]
    lines.append(f"当前监控列表：{len(watch_list)} 条\n")

    current_section = ""
    sections = {
        0: ("肿瘤治疗（按类型）", 69),
        69: ("筛查与预防", 7),
        76: ("支持治疗", 13),
        89: ("特殊人群", 3),
    }

    all_items = list(GUIDELINE_ZH.items())
    for start, (section_name, count) in sections.items():
        lines.append(f"\n## {section_name}")
        for i in range(start, min(start + count, len(all_items))):
            en_name, info = all_items[i]
            zh_name = info["zh"]
            watched = " ✅" if en_name.lower() in watch_set else ""
            lines.append(f"- {en_name} ({zh_name}){watched}")

    return "\n".join(lines)


def _save_config(cfg: dict) -> None:
    """Save config back to config.yaml."""
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            with open(path, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
            logger.info("Config saved to %s", path)
            return
    # Create default location
    default_path = DEFAULT_CONFIG_PATHS[0]
    with open(default_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    logger.info("Config created at %s", default_path)


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
