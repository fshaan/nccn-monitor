"""Version state management — detect which guidelines have been updated."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .scraper import GuidelineInfo

logger = logging.getLogger(__name__)


@dataclass
class VersionChange:
    """Represents a detected version change for a guideline."""

    name: str
    old_version: str
    new_version: str
    detail_url: str
    category: str


class StateManager:
    """Tracks known guideline versions in a JSON file.

    File format:
    {
        "last_check": "2026-03-20T08:00:00Z",
        "initialized": true,
        "guidelines": {
            "Breast Cancer": {"version": "2.2026", "first_seen": "...", "last_updated": "..."},
            ...
        }
    }
    """

    def __init__(self, state_file: str | Path):
        self.path = Path(state_file).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {"last_check": None, "initialized": False, "guidelines": {}}

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def detect_changes(
        self, current: list[GuidelineInfo], watch_list: list[str] | None = None
    ) -> list[VersionChange]:
        """Compare current scrape results against stored state.

        Args:
            current: Fresh scrape results from NCCN.
            watch_list: If set, only report changes for these guideline names.
                        Names are matched case-insensitively.

        Returns:
            List of VersionChange for guidelines whose version changed.
            Returns empty list on first run (baseline establishment).
        """
        now = datetime.now(timezone.utc).isoformat()
        stored = self._data["guidelines"]
        is_first_run = not self._data["initialized"]
        changes: list[VersionChange] = []

        # Normalize watch list for case-insensitive matching
        watch_set: set[str] | None = None
        if watch_list:
            watch_set = {name.lower() for name in watch_list}

        for info in current:
            # Filter by watch list if configured
            if watch_set and info.name.lower() not in watch_set:
                continue

            key = info.name
            if key in stored:
                old_ver = stored[key]["version"]
                if old_ver != info.version:
                    changes.append(
                        VersionChange(
                            name=info.name,
                            old_version=old_ver,
                            new_version=info.version,
                            detail_url=info.detail_url,
                            category=info.category,
                        )
                    )
                    stored[key]["version"] = info.version
                    stored[key]["last_updated"] = now
            else:
                # New guideline — record it but don't report as "changed"
                stored[key] = {
                    "version": info.version,
                    "first_seen": now,
                    "last_updated": now,
                }

        self._data["last_check"] = now
        self._data["initialized"] = True
        self._save()

        if is_first_run:
            logger.info(
                "First run: established baseline with %d guidelines. "
                "No changes reported.",
                len(stored),
            )
            return []

        if changes:
            logger.info("Detected %d guideline updates", len(changes))
        else:
            logger.info("No guideline updates detected")

        return changes

    @property
    def last_check(self) -> str | None:
        return self._data.get("last_check")

    @property
    def known_guidelines(self) -> dict:
        return self._data.get("guidelines", {})
