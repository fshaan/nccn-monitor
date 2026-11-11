#!/usr/bin/env python3
"""Observe one public login page and print allowlisted structure labels.

Do not run until the three isolated blobs have been reviewed. This process
does not read configuration, does not load credentials, does not construct a
credentialed session, and does not submit a form. A printed label does not admit a POST.

Import ``nccn_monitor`` only from the ``src`` directory next to this script.
Run it from an isolated copy of the three reviewed files, not from a
production checkout.

No arguments. The process timeout is the external ``timeout`` wrapper, not an
argument to this script.

Exact command, with no extra shell tracing:

    timeout 60 env -u PYTHONPATH PYTHONPATH="$ISOLATE/src" "$PYTHON" "$ISOLATE/scripts/observe_login_structure.py"

Process exit codes, distinct from weekly archive results and from pytest:
  0  one allowlisted observation was printed (not "login succeeded",
     not "a POST is allowed", and not "a PDF was archived")
  2  the single GET or local setup failed
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

_OUTPUT_KEYS = (
    "status_class",
    "host_class",
    "path_class",
    "content_type",
    "content_encoding_class",
    "body_decodable",
    "brotli_decoder_present",
    "observed_stage",
    "structure_class",
    "substring_marker_class",
    "static_text_role",
    "unknown_reason",
    "form_captcha_control_count_class",
    "challenge_frame_count_class",
    "vendor_script_count_class",
    "empty_container_count_class",
    "static_mention_count_class",
    "post_admitted",
    "error",
)
_ENUMS = {
    "status_class": {"ok", "redirect", "client-error", "server-error", "other", "not-reached"},
    "host_class": {"nccn", "other"},
    "path_class": {"login", "known-root", "other"},
    "content_encoding_class": {"absent", "gzip", "deflate", "br", "other"},
    "observed_stage": {"get", "not-reached"},
    "structure_class": {
        "not-decoded",
        "none-visible",
        "static-reference",
        "challenge-structure",
        "unknown",
    },
    "substring_marker_class": {"not-decoded", "none", "captcha-marker", "interstitial-marker"},
    "static_text_role": {"absent", "comment", "footer", "prose", "error", "mixed"},
    "unknown_reason": {
        "absent",
        "script-only",
        "empty-container",
        "script-and-empty",
        "dynamic-comment",
        "insufficient",
    },
    "form_captcha_control_count_class": {"not-decoded", "zero", "one", "several"},
    "challenge_frame_count_class": {"not-decoded", "zero", "one", "several"},
    "vendor_script_count_class": {"not-decoded", "zero", "one", "several"},
    "empty_container_count_class": {"not-decoded", "zero", "one", "several"},
    "static_mention_count_class": {"not-decoded", "zero", "one", "several"},
    "content_type": {"", "text/html", "text/plain", "application/pdf", "application/xhtml+xml", "other"},
}
_BOOLS = {"body_decodable", "brotli_decoder_present"}
_FAILED = {
    "error": "request_failed",
    "status_class": "not-reached",
    "host_class": "other",
    "path_class": "other",
    "content_type": "",
    "content_encoding_class": "absent",
    "body_decodable": False,
    "brotli_decoder_present": False,
    "observed_stage": "not-reached",
    "structure_class": "not-decoded",
    "substring_marker_class": "not-decoded",
    "static_text_role": "absent",
    "unknown_reason": "absent",
    "form_captcha_control_count_class": "not-decoded",
    "challenge_frame_count_class": "not-decoded",
    "vendor_script_count_class": "not-decoded",
    "empty_container_count_class": "not-decoded",
    "static_mention_count_class": "not-decoded",
    "post_admitted": False,
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


def _public(raw: dict) -> dict:
    published = dict(_FAILED)
    published.pop("error", None)
    if not isinstance(raw, dict):
        return dict(_FAILED)
    for key in _OUTPUT_KEYS:
        if key == "error":
            continue
        if key == "post_admitted":
            published[key] = False
            continue
        if key not in raw:
            continue
        value = raw[key]
        if key in _ENUMS and value not in _ENUMS[key]:
            continue
        if key in _BOOLS and not isinstance(value, bool):
            continue
        published[key] = value
    if raw.get("error") == "request_failed":
        published["error"] = "request_failed"
    published["post_admitted"] = False
    if published.get("observed_stage") not in _ENUMS["observed_stage"]:
        published["observed_stage"] = "not-reached"
    return published


async def _run() -> int:
    try:
        _pin_import()
        from nccn_monitor.login_structure import collect_login_structure
    except Exception:
        _emit(dict(_FAILED))
        return 2
    try:
        payload = await collect_login_structure()
    except Exception:
        _emit(dict(_FAILED))
        return 2
    published = _public(payload)
    _emit(published)
    if published.get("error"):
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
            _emit(dict(_FAILED))
    except BaseException:
        if not _emitted:
            _emit(dict(_FAILED))
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
