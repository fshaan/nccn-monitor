#!/usr/bin/env python3
"""NCCN weekly update check — repository shim for the external cron script.

Original wrapper SHA-256:
bd134c5fd9ba2b76a86abd7128ec83e6f4178112346d58e2e89dc737671a0801

Usage: python nccn_weekly_check.py [--dry-run]
Exit codes: 0 = no download performed, 1 = updates downloaded, 2 = error

The two absolute paths below keep the sanitized ``/Users/[REDACTED]/``
component from the review copy. Do not replace ``[REDACTED]`` with a guessed
username. Restore those two components only from the operator's original
file. This shim is not written to that machine.
"""

import asyncio
import logging
import sys
from pathlib import Path

import yaml

# Add project src to path. The first entry is preserved, not guessed.
PROJECT_PATHS = [
    Path("/Users/[REDACTED]/Workspace/devs/nccn_watcher/src"),
    Path(__file__).parent.parent / "src",
]
for p in PROJECT_PATHS:
    if p.exists():
        sys.path.insert(0, str(p))
        break

from nccn_monitor.weekly import check_and_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("nccn_weekly_check")


def load_config(config_path: str = "~/.nccn_watcher/config.yaml") -> dict:
    """Load config from YAML file."""
    path = Path(config_path).expanduser()
    if not path.exists():
        logger.error("Config not found: %s", path)
        return {}
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    dry_run = "--dry-run" in sys.argv
    config_path = "~/.nccn_watcher/config.yaml"

    # Try alternative paths. The workspace path keeps its redacted user component.
    alt_paths = [
        Path.home() / ".nccn_watcher" / "config.yaml",
        Path("/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml"),
    ]
    for p in alt_paths:
        if p.exists():
            config_path = str(p)
            break

    config = load_config(config_path)
    if not config:
        logger.error("Failed to load config. Check path: %s", config_path)
        sys.exit(2)

    exit_code = asyncio.run(check_and_download(config, dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
