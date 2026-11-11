"""Weekly check used by the external cron script.

Exit codes match the sanitized wrapper
``bd134c5fd9ba2b76a86abd7128ec83e6f4178112346d58e2e89dc737671a0801``:
0 = nothing downloaded (no work, or ``--dry-run``), 1 = at least one PDF
archived, 2 = scrape error, every required download failed, or only an
invalid existing PDF remains. The first baseline still returns 0 and does
not download. ``detect_changes`` returning an empty list still means the
compared versions are unchanged.
"""

import logging
from pathlib import Path

from .downloader import (
    ARCHIVE_BLOCKED_INVALID_EXISTING,
    BLOCKED_EXISTING_PDF_MESSAGE,
    NCCNDownloader,
    archive_followups_for_recorded_versions,
)
from .scraper import fetch_all_guidelines, fetch_pdf_index, slugify
from .state import StateManager

logger = logging.getLogger("nccn_weekly_check")


async def check_and_download(config: dict, dry_run: bool = False) -> int:
    """Check for updates and download missing current professional PDFs.

    A version change and a recorded version whose valid PDF is absent are
    both download work after the baseline exists. An existing ``%PDF`` that
    fails the professional check is reported and not replaced.
    """
    state_file = Path(config.get("state_file", "~/.nccn-monitor/state.json")).expanduser()
    state = StateManager(state_file)

    logger.info("Scraping NCCN guidelines...")
    try:
        current_guidelines = await fetch_all_guidelines()
    except Exception as e:
        logger.error("Scrape failed: %s", e)
        return 2

    watch_list = config.get("watch_list")
    already_initialized = state.initialized
    changes = state.detect_changes(current_guidelines, watch_list)
    archive_dir = config.get("archive_dir", "~/.nccn-monitor/archive")
    followups = []
    if already_initialized:
        followups = archive_followups_for_recorded_versions(
            current_guidelines,
            state.known_guidelines,
            watch_list,
            archive_dir,
            skip_names={change.name for change in changes},
        )
    blocked = [
        item for item in followups
        if item["status"] == ARCHIVE_BLOCKED_INVALID_EXISTING
    ]
    pending = [
        item for item in followups
        if item["status"] != ARCHIVE_BLOCKED_INVALID_EXISTING
    ]

    if changes:
        logger.info("Detected %d update(s):", len(changes))
        for change in changes:
            logger.info("  %s: %s → %s", change.name, change.old_version, change.new_version)
    elif not pending and not blocked:
        logger.info("No guideline updates detected.")
        return 0

    for item in pending:
        logger.info("Valid archive missing: %s v%s", item["name"], item["version"])
    for item in blocked:
        logger.error(
            "%s: %s v%s", BLOCKED_EXISTING_PDF_MESSAGE, item["name"], item["version"],
        )

    download_count = len(changes) + len(pending)
    if dry_run:
        if download_count:
            logger.info("[DRY RUN] Would download %d guideline(s).", download_count)
        return 0
    if download_count == 0:
        return 2

    nccn_cfg = config.get("nccn", {})
    downloader = NCCNDownloader(
        username=nccn_cfg.get("username"),
        password=nccn_cfg.get("password"),
    )
    index_file = Path(config.get("index_file", "~/.nccn-monitor/index.yaml")).expanduser()
    pdf_index = await fetch_pdf_index(current_guidelines, index_file)
    pdf_url_map = {entry.name: entry.pdf_url for entry in pdf_index}

    downloaded = 0
    failed = 0
    jobs = [
        (change.name, change.new_version, slugify(change.name))
        for change in changes
    ]
    jobs.extend(
        (item["name"], item["version"], item["slug"])
        for item in pending
    )
    for name, version, slug in jobs:
        pdf_url = pdf_url_map.get(name)
        if not pdf_url:
            logger.error("No PDF URL found for %s", name)
            failed += 1
            continue
        try:
            result = await downloader.download_and_archive(
                pdf_url=pdf_url,
                slug=slug,
                version=version,
                name=name,
                archive_dir=archive_dir,
            )
            if result:
                downloaded += 1
                logger.info("Downloaded: %s v%s → %s", name, version, result)
            else:
                failed += 1
                logger.error("Failed to download: %s v%s", name, version)
        except Exception as e:
            failed += 1
            logger.error("Error downloading %s: %s", name, e)

    await downloader.close()

    if failed > 0:
        logger.warning("%d/%d downloads failed.", failed, download_count)

    if downloaded > 0:
        return 1
    return 2
