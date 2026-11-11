"""GET-only structure labels for one public login page.

The labels describe HTML that is already in memory. They are not proof
that a server will require a challenge, and none of them grants a POST.
Production ``login()`` does not call this module.
"""

import logging
import re
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup, Comment

# Same header set the reviewed client already sends. Accept-Encoding stays
# unset so httpx advertises only decoders this interpreter can read.
OBSERVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

PUBLIC_LOGIN_URL = "https://www.nccn.org/login/Index/"

_MEDIA_TYPES = frozenset({
    "text/html",
    "text/plain",
    "application/pdf",
    "application/xhtml+xml",
})
_NCCN_HOSTS = frozenset({"nccn.org", "www.nccn.org"})
_HOOK_RE = re.compile(
    r"recaptcha|hcaptcha|captcha|cf-challenge|challenge-platform|cdn-cgi/challenge",
    re.IGNORECASE,
)
_DYNAMIC_COMMENT_RE = re.compile(r"script|insert|dynamic", re.IGNORECASE)
_ERROR_REGION_RE = re.compile(r"error|alert|validation", re.IGNORECASE)
_CONTROL_TAGS = ("iframe", "input", "textarea", "button", "select")


def _media_type(content_type: str) -> str:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if media in _MEDIA_TYPES:
        return media
    return "other" if media else ""


def _host_class(hostname: str | None) -> str:
    if (hostname or "").lower() in _NCCN_HOSTS:
        return "nccn"
    return "other"


def _path_class(path: str) -> str:
    normalized = path or "/"
    trimmed = normalized[:-1] if len(normalized) > 1 and normalized.endswith("/") else normalized
    if trimmed.lower() == "/login/index":
        return "login"
    if trimmed == "/":
        return "known-root"
    return "other"


def _brotli_decoder_present() -> bool:
    try:
        import brotli  # noqa: F401
    except ImportError:
        try:
            import brotlicffi  # noqa: F401
        except ImportError:
            return False
    return True


def _content_encoding_class(response) -> str:
    try:
        values = response.headers.get_list("content-encoding")
    except Exception:
        raw = response.headers.get("content-encoding", "")
        values = [raw] if raw else []
    if not values or not str(values[0]).strip():
        return "absent"
    token = str(values[0]).split(",", 1)[0].strip().lower()
    if token in {"gzip", "deflate", "br"}:
        return token
    return "other"


def _body_decodable(response, encoding_class: str, brotli_present: bool) -> bool:
    if encoding_class == "br" and not brotli_present:
        return False
    if encoding_class == "other":
        return False
    try:
        response.text
    except Exception:
        return False
    return True


def _substring_marker(text: str) -> str:
    """Whole-page substring label. This is not a structural finding."""
    folded = re.sub(r"\s+", " ", text or "").casefold()
    if any(marker in folded for marker in (
        "just a moment",
        "cf-challenge",
        "challenge-platform",
        "cdn-cgi/challenge",
    )):
        return "interstitial-marker"
    if any(marker in folded for marker in ("recaptcha", "hcaptcha", "captcha")):
        return "captcha-marker"
    return "none"


def _one_action_class(action) -> str:
    if not isinstance(action, str) or not action.strip():
        return "absent"
    raw = action.strip()
    if raw == "/login/Index/":
        return "exact-relative"
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    if path.lower().rstrip("/") == "/login/index":
        return "slash-or-case-variant"
    if host in _NCCN_HOSTS:
        return "absolute-nccn"
    return "other"


def _count_class(count: int) -> str:
    if count <= 0:
        return "zero"
    if count == 1:
        return "one"
    return "several"


def _status_class(code) -> str:
    try:
        number = int(code)
    except (TypeError, ValueError):
        return "other"
    if 200 <= number <= 299:
        return "ok"
    if 300 <= number <= 399:
        return "redirect"
    if 400 <= number <= 499:
        return "client-error"
    if 500 <= number <= 599:
        return "server-error"
    return "other"


class _bounded_logs:
    """Drop every log record for one observation, then restore the manager."""

    def __enter__(self):
        self._previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        return self

    def __exit__(self, exc_type, exc, tb):
        logging.disable(self._previous)
        return False


def _attr_text(tag, keys: tuple[str, ...]) -> str:
    parts: list[str] = []
    for key in keys:
        value = tag.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _hooked(value: str) -> bool:
    return _HOOK_RE.search(value or "") is not None


def _ancestors(node):
    current = getattr(node, "parent", None)
    while current is not None:
        if getattr(current, "name", None):
            yield current
        current = getattr(current, "parent", None)


def _inside(node, names: set[str]) -> bool:
    return any(tag.name in names for tag in _ancestors(node))


def _inside_exact_form(node) -> bool:
    for tag in _ancestors(node):
        if tag.name == "form" and _one_action_class(tag.get("action")) == "exact-relative":
            return True
    return False


def _inside_hooked_container(node) -> bool:
    for tag in _ancestors(node):
        if tag.name in {"script", "style"}:
            continue
        if _hooked(_attr_text(tag, ("id", "class"))):
            return True
    return False


def _has_control_descendant(tag) -> bool:
    return tag.find(_CONTROL_TAGS) is not None


def _role(kinds: set[str]) -> str:
    if not kinds:
        return "absent"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _structure_fields(
    *,
    structure: str,
    marker: str,
    role: str,
    reason: str,
    form_controls: int,
    frames: int,
    scripts: int,
    empty: int,
    static: int,
) -> dict:
    return {
        "structure_class": structure,
        "substring_marker_class": marker,
        "static_text_role": role,
        "unknown_reason": reason,
        "form_captcha_control_count_class": _count_class(form_controls),
        "challenge_frame_count_class": _count_class(frames),
        "vendor_script_count_class": _count_class(scripts),
        "empty_container_count_class": _count_class(empty),
        "static_mention_count_class": _count_class(static),
        "post_admitted": False,
    }


def classify_login_structure(html: str) -> dict:
    """Label one HTML document. The return value never includes the document."""
    raw = html or ""
    marker = _substring_marker(raw)
    soup = BeautifulSoup(raw, "html.parser")
    form_controls = 0
    frames = 0
    scripts = 0
    empty = 0
    static = 0
    dynamic_comments = 0
    hooked_prose = False
    kinds: set[str] = set()

    for script in soup.find_all("script"):
        blob = _attr_text(script, ("src",)) + " " + script.get_text(" ", strip=True)
        if _hooked(blob):
            scripts += 1

    for form in soup.find_all("form"):
        if _one_action_class(form.get("action")) != "exact-relative":
            continue
        form_controls += len(form.find_all("iframe"))
        for tag in form.find_all(("input", "textarea", "button", "select")):
            blob = _attr_text(tag, ("id", "class", "name", "type"))
            blob += " " + tag.get_text(" ", strip=True)
            if _hooked(blob):
                form_controls += 1

    for iframe in soup.find_all("iframe"):
        if _inside_exact_form(iframe):
            continue
        own = _attr_text(iframe, ("id", "class", "name", "title", "src"))
        if _hooked(own) or _inside_hooked_container(iframe):
            frames += 1

    for tag in soup.find_all(True):
        if tag.name in {"script", "style", "iframe", "input", "textarea", "button", "select", "form"}:
            continue
        if not _hooked(_attr_text(tag, ("id", "class"))):
            continue
        if _has_control_descendant(tag):
            continue
        if tag.get_text("", strip=True):
            hooked_prose = True
        else:
            empty += 1

    for comment in soup.find_all(string=lambda item: isinstance(item, Comment)):
        if _inside(comment, {"script", "style"}):
            continue
        text = str(comment)
        if not _hooked(text):
            continue
        if _DYNAMIC_COMMENT_RE.search(text):
            dynamic_comments += 1
        else:
            static += 1
            kinds.add("comment")

    for tag in soup.find_all(("p", "small", "footer")):
        if _inside(tag, {"script", "style", "noscript"}):
            continue
        if _inside_hooked_container(tag):
            continue
        if not _hooked(tag.get_text(" ", strip=True)):
            continue
        static += 1
        kinds.add("footer" if tag.name in {"footer", "small"} else "prose")

    for tag in soup.find_all(True):
        if tag.name in {"script", "style"}:
            continue
        identity = _attr_text(tag, ("id", "class"))
        if not _ERROR_REGION_RE.search(identity):
            continue
        if _hooked(identity) or _inside_hooked_container(tag):
            continue
        if _inside(tag, {"script", "style", "noscript"}):
            continue
        if not _hooked(tag.get_text(" ", strip=True)):
            continue
        static += 1
        kinds.add("error")

    if form_controls or frames:
        structure = "challenge-structure"
        reason = "absent"
    elif scripts and empty:
        structure = "unknown"
        reason = "script-and-empty"
    elif scripts:
        structure = "unknown"
        reason = "script-only"
    elif empty:
        structure = "unknown"
        reason = "empty-container"
    elif dynamic_comments and not hooked_prose:
        structure = "unknown"
        reason = "dynamic-comment"
    elif hooked_prose or marker == "interstitial-marker" or (marker == "captcha-marker" and not static):
        structure = "unknown"
        reason = "insufficient"
    elif static:
        structure = "static-reference"
        reason = "absent"
    else:
        structure = "none-visible"
        reason = "absent"

    return _structure_fields(
        structure=structure,
        marker=marker,
        role=_role(kinds) if static else "absent",
        reason=reason,
        form_controls=form_controls,
        frames=frames,
        scripts=scripts,
        empty=empty,
        static=static,
    )


def _not_decoded_fields() -> dict:
    return _structure_fields(
        structure="not-decoded",
        marker="not-decoded",
        role="absent",
        reason="absent",
        form_controls=0,
        frames=0,
        scripts=0,
        empty=0,
        static=0,
    ) | {
        "form_captcha_control_count_class": "not-decoded",
        "challenge_frame_count_class": "not-decoded",
        "vendor_script_count_class": "not-decoded",
        "empty_container_count_class": "not-decoded",
        "static_mention_count_class": "not-decoded",
        "post_admitted": False,
    }


def _unparsed_fields() -> dict:
    fields = _not_decoded_fields()
    fields["structure_class"] = "unknown"
    fields["unknown_reason"] = "insufficient"
    return fields


def view_from_response(response) -> dict:
    """Allowlisted view of one response. Body text is not returned."""
    encoding = _content_encoding_class(response)
    brotli_present = _brotli_decoder_present()
    decodable = _body_decodable(response, encoding, brotli_present)
    parts = urlsplit(str(response.url))
    view = {
        "status_class": _status_class(response.status_code),
        "host_class": _host_class(parts.hostname),
        "path_class": _path_class(parts.path),
        "content_type": _media_type(response.headers.get("content-type", "")),
        "content_encoding_class": encoding,
        "body_decodable": decodable,
        "brotli_decoder_present": brotli_present,
        "observed_stage": "get",
    }
    if not decodable:
        view.update(_not_decoded_fields())
        return view
    try:
        view.update(classify_login_structure(response.text))
    except Exception:
        view.update(_unparsed_fields())
    view["post_admitted"] = False
    view["observed_stage"] = "get"
    return view


def failed_view() -> dict:
    view = {
        "error": "request_failed",
        "status_class": "not-reached",
        "host_class": "other",
        "path_class": "other",
        "content_type": "",
        "content_encoding_class": "absent",
        "body_decodable": False,
        "brotli_decoder_present": _brotli_decoder_present(),
        "observed_stage": "not-reached",
    }
    view.update(_not_decoded_fields())
    view["post_admitted"] = False
    return view


def make_client() -> httpx.AsyncClient:
    """One normal client: reviewed headers, default encoding, TLS on, no hop."""
    return httpx.AsyncClient(
        headers=OBSERVER_HEADERS,
        timeout=60,
        follow_redirects=False,
    )


async def collect_login_structure() -> dict:
    """GET the fixed public login page once. Never submits a form."""
    client = None
    try:
        with _bounded_logs():
            client = make_client()
            response = await client.get(PUBLIC_LOGIN_URL)
            return view_from_response(response)
    except Exception:
        return failed_view()
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass
