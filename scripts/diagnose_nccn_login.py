#!/usr/bin/env python3
"""Print one allowlisted NCCN login diagnostic. Do not run until reviewed.

This process does not scan guidelines, touch state, or write archives.
It loads config by the same file order as the weekly shim and calls only
``NCCNDownloader.diagnose_login``. It does not change ``login()``.

Cloud agents must not execute this against NCCN. A parent specialist
reviews it before one authorized local test, from an isolated copy of
the candidate, not from the production checkout and not by replacing
``~/.hermes/scripts/nccn_weekly_check.py``.

No arguments. No credential is accepted on the command line or from the
environment. The process reads the operator's existing config file itself.

Exact command, with no extra shell tracing:

    python scripts/diagnose_nccn_login.py

Process exit codes, distinct from the weekly function's return values:
  0  structured diagnostic was printed (not "login succeeded", and not
     "a PDF was archived")
  2  credentials were not configured, or the request failed

Weekly ``check_and_download`` returning 1 means a PDF was archived.
A pytest process exiting 0 means the test runner finished successfully.
Those are different numbers from this script's exit codes.
"""

import asyncio
import json
import sys
from pathlib import Path

import yaml

from nccn_monitor.downloader import NCCNDownloader

# Same search order as the sanitized weekly shim. The user component stays
# redacted and must not be guessed or replaced.
_REDACTED_PROJECT_CONFIG = Path(
    "/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml"
)
_DIAGNOSTIC_URL = "https://www.nccn.org/login/Index/"
_OUTPUT_KEYS = (
    "status_code",
    "host_class",
    "path_class",
    "content_type",
    "has_login_form",
    "has_account",
    "has_logout",
    "error",
)


def load_config(config_path: str = "~/.nccn_watcher/config.yaml") -> dict:
    """Load YAML config. The path and file contents are not logged."""
    path = Path(config_path).expanduser()
    if not path.exists():
        return {}
    with open(path) as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _resolve_config_path() -> str:
    config_path = "~/.nccn_watcher/config.yaml"
    for candidate in (
        Path.home() / ".nccn_watcher" / "config.yaml",
        _REDACTED_PROJECT_CONFIG,
    ):
        if candidate.exists():
            return str(candidate)
    return config_path


def _public_diagnostic(raw: dict) -> dict:
    published = {}
    for key in _OUTPUT_KEYS:
        if key not in raw:
            continue
        if key == "error" and raw[key] not in {
            "credentials_not_configured",
            "request_failed",
        }:
            continue
        published[key] = raw[key]
    return published


async def _run() -> int:
    config = load_config(_resolve_config_path())
    nccn_cfg = config.get("nccn") if isinstance(config.get("nccn"), dict) else {}
    downloader = NCCNDownloader(
        username=nccn_cfg.get("username"),
        password=nccn_cfg.get("password"),
    )
    try:
        diagnostic = await downloader.diagnose_login(_DIAGNOSTIC_URL)
    finally:
        await downloader.close()
    json.dump(_public_diagnostic(diagnostic), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    if diagnostic.get("error"):
        return 2
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
