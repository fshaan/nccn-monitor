#!/usr/bin/env python3
"""Print one allowlisted NCCN login diagnostic. Do not run until reviewed.

This process does not scan guidelines, touch state, or write archives.
It loads config by the same file order as the weekly shim and calls only
``NCCNDownloader.diagnose_login``. It does not change ``login()``.

Import ``nccn_monitor`` only from the ``src`` directory next to this script,
before any editable install or ``PYTHONPATH`` entry. Run it from an isolated
copy of the three reviewed files, not from the production checkout, and do
not replace ``~/.hermes/scripts/nccn_weekly_check.py``.

No arguments. No credential is accepted on the command line or from the
environment. The process reads the operator's existing config file itself.
The ``/Users/[REDACTED]/`` component must not be guessed.

Exact command, with no extra shell tracing:

    PYTHONPATH="$ISOLATE/src" "$PYTHON" "$ISOLATE/scripts/diagnose_nccn_login.py"

Process exit codes, distinct from the weekly function's return values:
  0  structured diagnostic was printed (not "login succeeded", and not
     "a PDF was archived")
  2  credentials were not configured, or the request or local setup failed

Weekly ``check_and_download`` returning 1 means a PDF was archived.
A pytest process exiting 0 means the test runner finished successfully.
Those are different numbers from this script's exit codes.
"""

import asyncio
import json
import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
sys.tracebacklimit = 0


def _silent_excepthook(*_args) -> None:
    return


sys.excepthook = _silent_excepthook

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
    "observed_stage",
    "get_form_action_class",
    "get_password_control",
    "get_username_control",
    "get_hidden_count_class",
    "get_challenge_class",
    "get_content_encoding_class",
    "get_body_decodable",
    "final_content_encoding_class",
    "brotli_decoder_present",
    "error",
)
_ALLOWED_ERRORS = frozenset({"credentials_not_configured", "request_failed"})
_FAILED = {
    "error": "request_failed",
    "status_code": None,
    "host_class": "other",
    "path_class": "other",
    "content_type": "",
    "has_login_form": False,
    "has_account": False,
    "has_logout": False,
    "observed_stage": "not-reached",
    "get_form_action_class": "not-decoded",
    "get_password_control": "not-decoded",
    "get_username_control": "not-decoded",
    "get_hidden_count_class": "not-decoded",
    "get_challenge_class": "not-decoded",
    "get_content_encoding_class": "absent",
    "get_body_decodable": False,
    "final_content_encoding_class": "absent",
    "brotli_decoder_present": False,
}
_MISSING = {
    "error": "credentials_not_configured",
    "status_code": None,
    "host_class": "other",
    "path_class": "other",
    "content_type": "",
    "has_login_form": False,
    "has_account": False,
    "has_logout": False,
    "observed_stage": "not-reached",
    "get_form_action_class": "not-decoded",
    "get_password_control": "not-decoded",
    "get_username_control": "not-decoded",
    "get_hidden_count_class": "not-decoded",
    "get_challenge_class": "not-decoded",
    "get_content_encoding_class": "absent",
    "get_body_decodable": False,
    "final_content_encoding_class": "absent",
    "brotli_decoder_present": False,
}
_emitted = False


def _pin_import() -> None:
    """Prefer the src tree beside this file over site-packages and PYTHONPATH."""
    src = str(Path(__file__).resolve().parent.parent / "src")
    while src in sys.path:
        sys.path.remove(src)
    sys.path.insert(0, src)


def _emit(payload: dict) -> None:
    global _emitted
    if _emitted:
        return
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
    _emitted = True


def _public_diagnostic(raw: dict) -> dict:
    published = {}
    for key in _OUTPUT_KEYS:
        if key not in raw:
            continue
        if key == "error" and raw[key] not in _ALLOWED_ERRORS:
            continue
        published[key] = raw[key]
    return published


def load_config(config_path: str = "~/.nccn_watcher/config.yaml"):
    """Load YAML config. Paths, contents, and parser errors are not logged.

    Returns a dict, or None when the file exists but cannot be read safely.
    """
    import yaml

    path = Path(config_path).expanduser()
    if not path.is_file():
        return {}
    with open(path) as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        return None
    return loaded


def _resolve_config_path() -> str:
    config_path = "~/.nccn_watcher/config.yaml"
    for candidate in (
        Path.home() / ".nccn_watcher" / "config.yaml",
        _REDACTED_PROJECT_CONFIG,
    ):
        if candidate.is_file():
            return str(candidate)
    return config_path


async def _run() -> int:
    try:
        config = load_config(_resolve_config_path())
    except Exception:
        _emit(_FAILED)
        return 2
    if config is None:
        _emit(_FAILED)
        return 2
    nccn_cfg = config.get("nccn") if isinstance(config.get("nccn"), dict) else {}
    try:
        _pin_import()
        from nccn_monitor.downloader import NCCNDownloader
    except Exception:
        _emit(_FAILED)
        return 2
    downloader = NCCNDownloader(
        username=nccn_cfg.get("username"),
        password=nccn_cfg.get("password"),
    )
    try:
        diagnostic = await downloader.diagnose_login(_DIAGNOSTIC_URL)
    except Exception:
        _emit(_FAILED)
        return 2
    finally:
        try:
            await downloader.close()
        except Exception:
            pass
    _emit(_public_diagnostic(diagnostic))
    if diagnostic.get("error"):
        return 2
    return 0


def main() -> None:
    code = 2
    try:
        code = asyncio.run(_run())
    except SystemExit as exc:
        if isinstance(exc.code, int):
            code = exc.code
        if not _emitted:
            _emit(_FAILED)
    except BaseException:
        if not _emitted:
            _emit(_FAILED)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
