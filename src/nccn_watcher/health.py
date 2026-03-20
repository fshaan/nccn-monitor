"""Health check — detect silent failures and alert when scraping breaks."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FAILURE_THRESHOLD = 3  # Consecutive failures before alerting


class HealthTracker:
    """Track scraper health and detect silent failures.

    Stores run history in a JSON file:
    {
        "consecutive_failures": 0,
        "last_success": "2026-03-20T08:00:00Z",
        "last_failure": null,
        "last_error": null,
        "alerted": false
    }
    """

    def __init__(
        self,
        health_file: str | Path,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
    ):
        self.path = Path(health_file).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = failure_threshold
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {
            "consecutive_failures": 0,
            "last_success": None,
            "last_failure": None,
            "last_error": None,
            "alerted": False,
        }

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def record_success(self) -> None:
        was_failing = self._data["consecutive_failures"] > 0
        self._data["consecutive_failures"] = 0
        self._data["last_success"] = datetime.now(timezone.utc).isoformat()
        self._data["alerted"] = False
        self._save()
        if was_failing:
            logger.info("Health recovered after previous failures")

    def record_failure(self, error: str) -> bool:
        """Record a failure. Returns True if an alert should be sent."""
        self._data["consecutive_failures"] += 1
        self._data["last_failure"] = datetime.now(timezone.utc).isoformat()
        self._data["last_error"] = error
        self._save()

        count = self._data["consecutive_failures"]
        logger.warning("Consecutive failure #%d: %s", count, error)

        if count >= self.threshold and not self._data["alerted"]:
            self._data["alerted"] = True
            self._save()
            return True  # Caller should send alert

        return False

    @property
    def is_healthy(self) -> bool:
        return self._data["consecutive_failures"] == 0

    @property
    def status_summary(self) -> str:
        d = self._data
        if self.is_healthy:
            return f"Healthy. Last success: {d['last_success'] or 'never'}"
        return (
            f"UNHEALTHY — {d['consecutive_failures']} consecutive failures. "
            f"Last error: {d['last_error']}"
        )
