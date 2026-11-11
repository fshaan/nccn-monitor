"""NCCN Monitor MCP Server — entry point for OpenClaw integration."""

import os
import logging
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from .scraper import (
    fetch_all_guidelines, fetch_pdf_index,
    slugify, ScrapeError,
)
from .state import StateManager
from .downloader import NCCNDownloader, get_archived_versions, valid_current_archive_exists
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
    Path.home() / ".nccn-monitor" / "config.yaml",
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
        "state_file": "~/.nccn-monitor/state.json",
        "cache_dir": "~/.nccn-monitor/cache",
        "archive_dir": "~/.nccn-monitor/archive",
    }


# ── Initialize ───────────────────────────────────────────────────────

config = load_config()
mcp = FastMCP("nccn-monitor")
state_mgr = StateManager(config.get("state_file", "~/.nccn-monitor/state.json"))
health = HealthTracker("~/.nccn-monitor/health.json")

nccn_user = config.get("nccn", {}).get("username") or os.getenv("NCCN_USERNAME", "")
nccn_pass = config.get("nccn", {}).get("password") or os.getenv("NCCN_PASSWORD", "")
downloader = NCCNDownloader(nccn_user or None, nccn_pass or None)


# ── MCP Tools ────────────────────────────────────────────────────────


def _current_versions_missing_archive(
    current,
    known: dict,
    watch_list: list[str],
    archive_dir: str,
    pdf_url_map: dict,
    skip_names: set[str],
) -> list[tuple]:
    """Monitored guidelines whose recorded current version has no valid PDF.

    Unmonitored guidelines and older version directories are ignored. This is
    used by check_updates only. The external weekly wrapper does not call
    check_updates, so this retry does not by itself repair that script.
    """
    watch_set = {name.lower() for name in watch_list} if watch_list else None
    pending = []
    for info in current:
        if watch_set is not None and info.name.lower() not in watch_set:
            continue
        if info.name in skip_names:
            continue
        recorded = known.get(info.name) or {}
        version = recorded.get("version") or ""
        if not version:
            continue
        entry = pdf_url_map.get(info.name)
        slug = entry.slug if entry else slugify(info.name)
        if valid_current_archive_exists(slug, version, info.name, archive_dir):
            continue
        pending.append((info, version))
    return pending


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
    cache_dir = config.get("cache_dir", "~/.nccn-monitor/cache")
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("update_notes_pages", 5)
    language = analysis_cfg.get("language", "zh-CN")

    try:
        # Step 1: Scrape ALL category pages for complete guideline list
        current = await fetch_all_guidelines()
        health.record_success()

        # Step 2: Detect version changes. An empty list still means the
        # compared versions are unchanged. Archive retry is separate and only
        # runs after a baseline already exists, so the first run does not
        # download every watched guideline.
        already_initialized = state_mgr.initialized
        changes = state_mgr.detect_changes(current, watch_list or None)
        archive_dir = config.get("archive_dir", "~/.nccn-monitor/archive")

        if not changes and not already_initialized:
            return (
                f"No guideline updates detected. "
                f"Checked {len(current)} guidelines. "
                f"Last check: {state_mgr.last_check}"
            )

        # Step 3: Get PDF URLs from index (crawls detail pages if needed)
        index = await fetch_pdf_index(current)
        pdf_url_map = {e.name: e for e in index}
        retries = []
        if already_initialized:
            retries = _current_versions_missing_archive(
                current,
                state_mgr.known_guidelines,
                watch_list,
                archive_dir,
                pdf_url_map,
                {change.name for change in changes},
            )

        if not changes and not retries:
            return (
                f"No guideline updates detected. "
                f"Checked {len(current)} guidelines. "
                f"Last check: {state_mgr.last_check}"
            )

        # Step 4: For each version change, and for each already-recorded
        # monitored version whose valid PDF is still absent, archive once.
        report_parts: list[str] = []
        if changes:
            report_parts.append(f"# NCCN Guideline Updates Detected ({len(changes)})\n")
        else:
            report_parts.append(f"# NCCN Guideline Archives Missing ({len(retries)})\n")

        jobs = [
            {
                "name": change.name,
                "version_line": f"**Version**: {change.old_version} → {change.new_version}",
                "category": change.category,
                "detail_url": change.detail_url,
                "archive_version": change.new_version,
                "old_version": change.old_version,
                "new_version": change.new_version,
            }
            for change in changes
        ]
        jobs.extend(
            {
                "name": info.name,
                "version_line": f"**Version**: {version} (recorded, valid archive missing)",
                "category": info.category,
                "detail_url": info.detail_url,
                "archive_version": version,
                "old_version": version,
                "new_version": version,
            }
            for info, version in retries
        )

        for job in jobs:
            entry = pdf_url_map.get(job["name"])
            section = [
                f"## {job['name']} ({get_zh_name(job['name'])})",
                job["version_line"],
                f"**Category**: {job['category']}",
                f"**Detail**: {job['detail_url']}",
            ]
            if entry:
                section.append(f"**PDF**: {entry.pdf_url}")

            # Try PDF download + archive + analysis if credentials available
            if analysis_cfg.get("enabled", True) and nccn_user and entry:
                pdf_path = await downloader.download_and_archive(
                    entry.pdf_url, entry.slug, job["archive_version"],
                    name=job["name"],
                    archive_dir=archive_dir,
                )
                if pdf_path:
                    notes = extract_update_notes(pdf_path, max_pages)
                    if notes:
                        prompt = build_summary_prompt(
                            job["name"],
                            job["old_version"],
                            job["new_version"],
                            notes,
                            language,
                        )
                        section.append(f"\n### Update Notes (raw text)\n```\n{notes[:2000]}\n```")
                        section.append(f"\n### AI Summary Prompt\n{prompt}")
                    else:
                        section.append("\n*Could not extract update notes from PDF.*")
                else:
                    section.append("\n*PDF download failed. Check NCCN credentials.*")
            elif not entry:
                section.append(
                    "\n*PDF URL not found in index. "
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
    """Get the current status of the NCCN monitor.

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

    # GUIDELINE_ZH is ordered by category in the source file.
    # These indexes must match the category boundaries in guideline_names.py.
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


@mcp.tool()
async def download_guideline(query: str) -> str:
    """Download a specific NCCN guideline PDF by name.

    Searches by Chinese or English name (fuzzy matching), downloads the
    PDF via NCCN login, archives it, and extracts update notes.

    Args:
        query: Guideline name in Chinese, English, or abbreviation.
               Examples: "胃癌", "GIST", "Breast Cancer"

    Returns a summary with the PDF path and extracted update notes.
    """
    # Step 1: Resolve guideline name
    matches = search_guidelines(query)
    if not matches:
        return f"No guideline found matching '{query}'. Use find_guideline to search."

    en_name, zh_name, score = matches[0]
    if score < 0.4:
        return f"No confident match for '{query}'. Best guess: {en_name} ({zh_name}). Use find_guideline to search."

    # Step 2: Get PDF URL from index
    guidelines = await fetch_all_guidelines()
    index = await fetch_pdf_index(guidelines)
    entry = next((e for e in index if e.name == en_name), None)

    if not entry:
        return f"PDF URL not found for '{en_name}'. The index may be incomplete."

    if not nccn_user:
        return (
            f"Found: **{en_name}** ({zh_name}) — Version {entry.version}\n"
            f"PDF URL: {entry.pdf_url}\n\n"
            f"*Cannot download — NCCN credentials not configured.*"
        )

    # Step 3: Download and archive with standardized filename
    pdf_path = await downloader.download_and_archive(
        entry.pdf_url, entry.slug, entry.version,
        name=en_name,
        archive_dir=config.get("archive_dir", "~/.nccn-monitor/archive"),
    )
    if not pdf_path:
        return f"Download failed for {en_name}. Check NCCN credentials."

    # Step 4: Extract update notes
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("update_notes_pages", 5)
    notes = extract_update_notes(pdf_path, max_pages)

    lines = [
        f"# {en_name} ({zh_name})",
        f"**Version**: {entry.version}",
        f"**PDF**: {pdf_path}",
        f"**Size**: {pdf_path.stat().st_size / (1024*1024):.1f} MB",
    ]
    if notes:
        lines.append(f"\n## Update Notes (first {max_pages} pages)\n```\n{notes[:3000]}\n```")
    else:
        lines.append("\n*No update notes extracted.*")

    return "\n".join(lines)


@mcp.tool()
async def get_guideline_history(query: str) -> str:
    """View the version history and change timeline for a specific guideline.

    Shows all archived versions with download dates and file sizes.

    Args:
        query: Guideline name in Chinese, English, or abbreviation.
    """
    matches = search_guidelines(query)
    if not matches:
        return f"No guideline found matching '{query}'."

    en_name, zh_name, score = matches[0]
    slug = slugify(en_name)

    archive_dir = config.get("archive_dir", "~/.nccn-monitor/archive")
    versions = get_archived_versions(slug, archive_dir=archive_dir)
    if not versions:
        return (
            f"No archived versions for **{en_name}** ({zh_name}).\n\n"
            f"Use `download_guideline(\"{query}\")` to download the current version."
        )

    lines = [
        f"# {en_name} ({zh_name}) — Version History",
        f"**{len(versions)} archived version(s)**\n",
    ]

    for v in versions:
        version = v.get("version", "?")
        date = v.get("downloaded_at", "?")[:10]
        size_mb = v.get("size_bytes", 0) / (1024 * 1024)
        fname = v.get("filename", "guideline.pdf")
        lines.append(f"- **v{version}** — {fname} — archived {date} ({size_mb:.1f} MB)")

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
    logger.info("Starting NCCN Monitor MCP Server...")
    if nccn_user:
        logger.info("NCCN authentication configured for: %s", nccn_user)
    else:
        logger.warning("No NCCN credentials — PDF download and AI analysis disabled")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
