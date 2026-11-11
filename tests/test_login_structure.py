"""Synthetic structure labels. No live login page is requested."""

import importlib.util
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest

from nccn_monitor.downloader import (
    BROWSER_HEADERS,
    NCCNDownloader,
    _challenge_class,
    _host_class,
    _media_type,
    _one_action_class,
    _path_class,
)
from nccn_monitor.login_structure import (
    OBSERVER_HEADERS,
    PUBLIC_LOGIN_URL,
    classify_login_structure,
    collect_login_structure,
    make_client,
    view_from_response,
)

SECRET_USER = "fixture-user"
SECRET_PASSWORD = "fixture-password"
LEAKS = (
    "fixture-",
    "example.test",
    "://",
    "http",
    "nccn.org",
    "/login",
    "Username",
    "Password",
    "Index",
    "sitekey",
    "src=",
)


def _page(*parts: str) -> str:
    return "<!DOCTYPE html><html><body>" + "".join(parts) + "</body></html>"


def _form(inner: str = "", action: str = "/login/Index/") -> str:
    return (
        f'<form action="{action}" method="post">'
        '<input type="hidden" name="__RequestVerificationToken" value="fixture-token" />'
        '<input type="text" name="Username" />'
        '<input type="password" name="Password" />'
        f"{inner}</form>"
    )


def _rendered(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def _assert_closed(payload: dict) -> None:
    rendered = _rendered(payload)
    for leak in LEAKS:
        assert leak not in rendered
    assert payload["post_admitted"] is False


def _response(html: str, status: int = 200, headers: dict | None = None, url: str = PUBLIC_LOGIN_URL):
    merged = {"content-type": "text/html"}
    if headers:
        merged.update(headers)
    return httpx.Response(
        status,
        headers=merged,
        content=html.encode(),
        request=httpx.Request("GET", url),
    )


@pytest.mark.parametrize(
    ("html", "role"),
    [
        (_page(_form(), "<!-- recaptcha fixture-comment-secret -->"), "comment"),
        (_page(_form(), "<footer>recaptcha fixture-footer-secret</footer>"), "footer"),
        (_page(_form(), "<small>captcha fixture-small-secret</small>"), "footer"),
        (_page(_form(), "<p>recaptcha fixture-prose-secret</p>"), "prose"),
        (
            _page('<div class="validation-summary">captcha fixture-error-secret</div>'),
            "error",
        ),
    ],
)
def test_static_regions_are_references_not_challenge_structure(html: str, role: str):
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "static-reference"
    assert label["substring_marker_class"] == "captcha-marker"
    assert label["static_text_role"] == role
    assert label["unknown_reason"] == "absent"
    assert label["form_captcha_control_count_class"] == "zero"
    assert label["challenge_frame_count_class"] == "zero"
    assert label["vendor_script_count_class"] == "zero"
    assert label["empty_container_count_class"] == "zero"
    assert label["static_mention_count_class"] == "one"


def test_comment_and_paragraph_together_are_mixed_static_reference():
    html = _page("<!-- captcha fixture-comment-secret -->", "<p>recaptcha fixture-prose-secret</p>")
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "static-reference"
    assert label["static_text_role"] == "mixed"
    assert label["static_mention_count_class"] == "several"


@pytest.mark.parametrize(
    "inner",
    [
        '<input type="hidden" name="fixture-captcha-token" value="fixture-key" />',
        '<textarea name="fixture-captcha-note">fixture-key</textarea>',
        '<button type="submit">fixture-captcha-secret</button>',
        '<select name="fixture-captcha-choice"></select>',
        '<iframe src="https://example.test/fixture-frame"></iframe>',
    ],
    ids=["hidden", "textarea", "button", "select", "iframe"],
)
def test_bound_form_control_is_challenge_structure_and_does_not_admit_post(inner: str):
    label = classify_login_structure(_page(_form(inner)))
    _assert_closed(label)
    assert label["structure_class"] == "challenge-structure"
    assert label["form_captcha_control_count_class"] == "one"
    assert label["unknown_reason"] == "absent"
    assert label["post_admitted"] is False


def test_two_form_controls_count_as_several():
    inner = (
        '<input type="hidden" name="fixture-captcha-token" value="fixture-key" />'
        '<textarea name="fixture-captcha-note">fixture-key</textarea>'
    )
    label = classify_login_structure(_page(_form(inner)))
    _assert_closed(label)
    assert label["structure_class"] == "challenge-structure"
    assert label["form_captcha_control_count_class"] == "several"


def test_form_iframe_without_marker_is_still_challenge_structure():
    html = _page(_form('<iframe src="https://example.test/fixture-frame"></iframe>'))
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["substring_marker_class"] == "none"
    assert label["structure_class"] == "challenge-structure"
    assert label["form_captcha_control_count_class"] == "one"
    assert label["challenge_frame_count_class"] == "zero"


def test_outside_frame_and_hooked_container_are_challenge_structure():
    framed = _page('<iframe src="https://example.test/fixture-captcha-frame"></iframe>')
    contained = _page(
        '<div id="fixture-captcha-slot"><iframe src="https://example.test/frame"></iframe></div>'
    )
    for html in (framed, contained):
        label = classify_login_structure(html)
        _assert_closed(label)
        assert label["structure_class"] == "challenge-structure"
        assert label["challenge_frame_count_class"] == "one"
        assert label["form_captcha_control_count_class"] == "zero"


def test_unmarked_external_iframe_is_not_a_challenge_structure():
    label = classify_login_structure(_page('<iframe src="https://example.test/video"></iframe>'))
    _assert_closed(label)
    assert label["structure_class"] == "none-visible"
    assert label["substring_marker_class"] == "none"
    assert label["challenge_frame_count_class"] == "zero"


def test_captcha_input_outside_exact_form_is_unknown():
    html = _page(_form('<input name="fixture-captcha-token" value="fixture-key" />', action="/other"))
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == "insufficient"
    assert label["form_captcha_control_count_class"] == "zero"


@pytest.mark.parametrize(
    ("html", "reason"),
    [
        (
            _page('<script src="https://example.test/fixture-captcha.js"></script>'),
            "script-only",
        ),
        (
            _page('<script>var label = "captcha";</script>'),
            "script-only",
        ),
        (
            _page('<div class="fixture-captcha" data-sitekey="fixture-key"></div>'),
            "empty-container",
        ),
        (
            _page(_form('<div class="fixture-captcha" data-sitekey="fixture-key"></div>')),
            "empty-container",
        ),
        (
            _page("<!-- captcha control is inserted by script -->"),
            "dynamic-comment",
        ),
        (
            _page("<title>captcha fixture-title-secret</title>"),
            "insufficient",
        ),
        (
            _page('<meta name="description" content="captcha fixture-meta-secret" />'),
            "insufficient",
        ),
        (
            _page("<noscript><p>captcha fixture-noscript-secret</p></noscript>"),
            "insufficient",
        ),
    ],
    ids=[
        "script-src",
        "inline-script",
        "empty",
        "empty-in-form",
        "dynamic-comment",
        "title",
        "meta",
        "noscript",
    ],
)
def test_script_empty_container_and_unclear_markup_are_unknown(html: str, reason: str):
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == reason
    assert label["post_admitted"] is False
    assert label["structure_class"] != "none-visible"
    assert label["structure_class"] != "static-reference"


def test_script_and_empty_container_report_both():
    html = _page(
        '<script src="https://example.test/fixture-captcha.js"></script>',
        '<div class="fixture-captcha"></div>',
    )
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == "script-and-empty"
    assert label["vendor_script_count_class"] == "one"
    assert label["empty_container_count_class"] == "one"


def test_script_or_empty_container_prevents_static_reference():
    script = _page(
        '<script src="https://example.test/fixture-captcha.js"></script>',
        "<footer>captcha fixture-footer-secret</footer>",
    )
    empty = _page(
        '<div class="fixture-captcha" data-sitekey="fixture-key"></div>',
        "<footer>captcha fixture-footer-secret</footer>",
    )
    for html, reason in ((script, "script-only"), (empty, "empty-container")):
        label = classify_login_structure(html)
        _assert_closed(label)
        assert label["structure_class"] == "unknown"
        assert label["unknown_reason"] == reason
        assert label["static_mention_count_class"] == "one"


def test_plain_script_plus_footer_stays_static_reference():
    html = _page(
        '<script src="https://example.test/library.js"></script>',
        "<footer>captcha fixture-footer-secret</footer>",
    )
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "static-reference"
    assert label["vendor_script_count_class"] == "zero"


def test_hooked_container_with_only_prose_is_unknown():
    html = _page('<div class="fixture-captcha"><p>complete the fixture-prose-secret</p></div>')
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == "insufficient"
    assert label["empty_container_count_class"] == "zero"
    assert label["form_captcha_control_count_class"] == "zero"


def test_real_control_wins_over_a_vendor_script():
    html = _page(
        '<script src="https://example.test/fixture-captcha.js"></script>',
        _form('<input type="hidden" name="fixture-captcha-token" value="fixture-key" />'),
    )
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["structure_class"] == "challenge-structure"
    assert label["vendor_script_count_class"] == "one"
    assert label["form_captcha_control_count_class"] == "one"
    assert label["unknown_reason"] == "absent"
    assert label["post_admitted"] is False


def test_plain_form_is_none_visible_and_does_not_admit_post():
    label = classify_login_structure(_page(_form()))
    _assert_closed(label)
    assert label["structure_class"] == "none-visible"
    assert label["substring_marker_class"] == "none"
    assert label["unknown_reason"] == "absent"
    assert label["static_text_role"] == "absent"
    for key in (
        "form_captcha_control_count_class",
        "challenge_frame_count_class",
        "vendor_script_count_class",
        "empty_container_count_class",
        "static_mention_count_class",
    ):
        assert label[key] == "zero"


def test_interstitial_text_without_structure_is_unknown():
    label = classify_login_structure(_page("Just a moment"))
    _assert_closed(label)
    assert label["substring_marker_class"] == "interstitial-marker"
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == "insufficient"
    assert label["structure_class"] != "none-visible"
    assert label["post_admitted"] is False


def test_interstitial_text_plus_captcha_prose_stays_unknown():
    label = classify_login_structure(_page("Just a moment", "<p>captcha fixture-prose-secret</p>"))
    _assert_closed(label)
    assert label["substring_marker_class"] == "interstitial-marker"
    assert label["structure_class"] == "unknown"
    assert label["static_mention_count_class"] == "one"


def test_empty_interstitial_container_is_unknown_not_a_frame():
    label = classify_login_structure(_page('<div id="cf-challenge"></div>'))
    _assert_closed(label)
    assert label["substring_marker_class"] == "interstitial-marker"
    assert label["structure_class"] == "unknown"
    assert label["unknown_reason"] == "empty-container"
    assert label["challenge_frame_count_class"] == "zero"


def test_interstitial_frame_is_challenge_structure():
    html = _page('<iframe src="https://example.test/cdn-cgi/challenge"></iframe>')
    label = classify_login_structure(html)
    _assert_closed(label)
    assert label["substring_marker_class"] == "interstitial-marker"
    assert label["structure_class"] == "challenge-structure"
    assert label["challenge_frame_count_class"] == "one"
    assert label["post_admitted"] is False


def test_view_scrubs_status_host_path_and_media_parameters():
    response = _response(
        _page(_form(), "<p>captcha fixture-prose-secret</p>"),
        headers={"content-type": "text/html; secret=fixture-type-secret"},
        url="https://evil.example/login/Index/?token=fixture-query-secret",
    )
    view = view_from_response(response)
    _assert_closed(view)
    assert view["status_class"] == "ok"
    assert view["host_class"] == "other"
    assert view["path_class"] == "login"
    assert view["content_type"] == "text/html"
    assert view["observed_stage"] == "get"
    assert view["structure_class"] == "static-reference"
    assert "200" not in _rendered(view)


def test_client_error_status_is_an_enum():
    view = view_from_response(_response("<p>no marker</p>", status=403))
    _assert_closed(view)
    assert view["status_class"] == "client-error"
    assert "403" not in _rendered(view)


def test_br_body_is_not_decoded_or_admitted(monkeypatch):
    from httpx._decoders import SUPPORTED_DECODERS

    monkeypatch.setattr("nccn_monitor.login_structure._brotli_decoder_present", lambda: False)
    monkeypatch.delitem(SUPPORTED_DECODERS, "br", raising=False)
    response = httpx.Response(
        200,
        headers={"content-type": "text/html", "content-encoding": "br"},
        content=b"captcha fixture-br-secret",
        request=httpx.Request("GET", PUBLIC_LOGIN_URL),
    )
    view = view_from_response(response)
    _assert_closed(view)
    assert view["body_decodable"] is False
    assert view["content_encoding_class"] == "br"
    assert view["structure_class"] == "not-decoded"
    assert view["substring_marker_class"] == "not-decoded"
    assert view["form_captcha_control_count_class"] == "not-decoded"
    assert view["observed_stage"] == "get"
    assert "fixture-br-secret" not in _rendered(view)


def test_gzip_body_is_classified_without_returning_text():
    import gzip

    raw = _page("<p>captcha fixture-gzip-secret</p>").encode()
    response = httpx.Response(
        200,
        headers={"content-type": "text/html", "content-encoding": "gzip"},
        content=gzip.compress(raw),
        request=httpx.Request("GET", PUBLIC_LOGIN_URL),
    )
    view = view_from_response(response)
    _assert_closed(view)
    assert view["body_decodable"] is True
    assert view["content_encoding_class"] == "gzip"
    assert view["structure_class"] == "static-reference"


def test_classifier_failure_does_not_leak_and_stays_get(monkeypatch):
    def boom(_html: str) -> dict:
        raise RuntimeError("fixture-parse-secret https://example.test/secret")

    monkeypatch.setattr("nccn_monitor.login_structure.classify_login_structure", boom)
    view = view_from_response(_response(_page(_form())))
    _assert_closed(view)
    assert view["observed_stage"] == "get"
    assert view["structure_class"] == "unknown"
    assert view["post_admitted"] is False


def test_allowlist_helpers_match_the_reviewed_downloader():
    assert OBSERVER_HEADERS == BROWSER_HEADERS
    assert "Accept-Encoding" not in OBSERVER_HEADERS
    assert "accept-encoding" not in OBSERVER_HEADERS
    samples = [
        "",
        "Just a moment",
        "  Just   a moment  ",
        "recaptcha",
        "cf-challenge and captcha",
        "nothing here",
    ]
    for sample in samples:
        assert _substring_from_module(sample) == _challenge_class(sample)
    assert _host_class("www.nccn.org") == "nccn"
    assert _path_class("/login/Index/") == "login"
    assert _one_action_class("/login/Index/") == "exact-relative"
    assert _media_type("text/html; charset=utf-8") == "text/html"
    from nccn_monitor import login_structure as module

    assert module._host_class("www.nccn.org") == _host_class("www.nccn.org")
    assert module._path_class("/login/Index/") == _path_class("/login/Index/")
    assert module._one_action_class("https://www.nccn.org/login/Index/") == _one_action_class(
        "https://www.nccn.org/login/Index/"
    )
    assert module._media_type("text/html; secret=fixture-type-secret") == _media_type(
        "text/html; secret=fixture-type-secret"
    )


def _substring_from_module(sample: str) -> str:
    from nccn_monitor.login_structure import _substring_marker

    return _substring_marker(sample)


async def test_client_uses_reviewed_headers_default_encoding_and_one_hop():
    source = Path(__file__).resolve().parents[1].joinpath("src/nccn_monitor/login_structure.py").read_text()
    assert "verify=False" not in source
    assert ".post(" not in source
    assert "NCCNDownloader" not in source
    bare = httpx.AsyncClient()
    client = make_client()
    try:
        assert client.follow_redirects is False
        assert client.headers["accept-encoding"] == bare.headers["accept-encoding"]
        assert client.timeout.connect == 60
        assert client.timeout.read == 60
    finally:
        await client.aclose()
        await bare.aclose()


async def test_collect_issues_one_get_and_does_not_follow(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        logging.getLogger("httpx").error("transport %s fixture-log-secret", request.url)
        return httpx.Response(
            302,
            headers={"Location": "https://example.test/next?token=fixture-query-secret"},
            request=request,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=OBSERVER_HEADERS,
        timeout=60,
        follow_redirects=False,
    )
    monkeypatch.setattr("nccn_monitor.login_structure.make_client", lambda: client)
    captured: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler_obj = Capture(level=logging.DEBUG)
    root = logging.getLogger()
    httpx_logger = logging.getLogger("httpx")
    previous = httpx_logger.level
    previous_disable = logging.root.manager.disable
    root.addHandler(handler_obj)
    httpx_logger.addHandler(handler_obj)
    httpx_logger.setLevel(logging.DEBUG)
    try:
        view = await collect_login_structure()
        logging.getLogger("httpx").error("after-marker-visible")
    finally:
        root.removeHandler(handler_obj)
        httpx_logger.removeHandler(handler_obj)
        httpx_logger.setLevel(previous)
    assert calls == ["GET"]
    assert view["status_class"] == "redirect"
    assert view["observed_stage"] == "get"
    assert view["post_admitted"] is False
    _assert_closed(view)
    during = [record.getMessage() for record in captured if record.getMessage() != "after-marker-visible"]
    assert during == []
    assert any(record.getMessage() == "after-marker-visible" for record in captured)
    assert logging.root.manager.disable == previous_disable


async def test_get_failure_and_close_failure_do_not_leak(monkeypatch):
    class Boom:
        async def get(self, url):
            raise RuntimeError(f"fixture-get-secret {url}")

        async def aclose(self):
            return None

    monkeypatch.setattr("nccn_monitor.login_structure.make_client", lambda: Boom())
    failed = await collect_login_structure()
    _assert_closed(failed)
    assert failed["error"] == "request_failed"
    assert failed["observed_stage"] == "not-reached"
    assert failed["post_admitted"] is False

    class ClosesBadly:
        async def get(self, url):
            return _response(_page(_form()))

        async def aclose(self):
            raise RuntimeError("fixture-close-secret https://example.test/close")

    monkeypatch.setattr("nccn_monitor.login_structure.make_client", lambda: ClosesBadly())
    kept = await collect_login_structure()
    _assert_closed(kept)
    assert kept["structure_class"] == "none-visible"
    assert "error" not in kept


def _load_runner():
    runner = Path(__file__).resolve().parents[1] / "scripts" / "observe_login_structure.py"
    spec = importlib.util.spec_from_file_location("observe_login_structure_under_test", runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_source_has_no_credential_or_post_path():
    source = Path(__file__).resolve().parents[1].joinpath("scripts/observe_login_structure.py").read_text()
    for banned in (
        "NCCNDownloader",
        "yaml",
        "config.yaml",
        ".post(",
        "verify=False",
        "Accept-Encoding",
        "argparse",
        "import os",
        "os.environ",
        "downloader",
    ):
        assert banned not in source
    assert "timeout 60 env -u PYTHONPATH" in source
    assert source.strip().endswith("main()")


def test_runner_ignores_config_env_and_argv(tmp_path: Path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    config = home / ".nccn_watcher"
    config.mkdir()
    (config / "config.yaml").write_text("nccn:\n  username: fixture-user\n  password: fixture-config-secret\n")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("NCCN_PASSWORD", "fixture-env-secret")
    monkeypatch.setenv("NCCN_USERNAME", "fixture-user")
    monkeypatch.chdir(work)
    module = _load_runner()
    secret_arg = "https://example.test/argv?token=fixture-argv-secret"
    monkeypatch.setattr(sys, "argv", [str(module.__file__), secret_arg])

    class Fake:
        def __init__(self):
            self.urls = []

        async def get(self, url):
            self.urls.append(url)
            return _response(_page(_form(), "<p>captcha fixture-prose-secret</p>"))

        async def post(self, *args, **kwargs):
            raise AssertionError("post")

        async def aclose(self):
            return None

    fake = Fake()
    monkeypatch.setattr("nccn_monitor.login_structure.make_client", lambda: fake)
    previous_hook = sys.excepthook
    previous_limit = getattr(sys, "tracebacklimit", 1000)
    try:
        code = __import__("asyncio").run(module._run())
    finally:
        sys.excepthook = previous_hook
        sys.tracebacklimit = previous_limit
    captured = capsys.readouterr()
    assert code == 0
    assert fake.urls == [PUBLIC_LOGIN_URL]
    payload = json.loads(captured.out)
    assert payload["structure_class"] == "static-reference"
    assert payload["post_admitted"] is False
    assert payload["observed_stage"] == "get"
    _assert_closed(payload)
    assert "fixture-config-secret" not in captured.out
    assert "fixture-env-secret" not in captured.out
    assert secret_arg not in captured.out
    assert "Traceback" not in captured.err
    assert list(work.rglob("*")) == []


def test_runner_forces_closed_output(monkeypatch, capsys):
    module = _load_runner()

    async def rogue():
        return {
            "post_admitted": True,
            "observed_stage": "post",
            "structure_class": "fixture-secret https://evil.example/a",
            "html": "<p>fixture-secret</p>",
            "status_class": "ok",
        }

    monkeypatch.setattr("nccn_monitor.login_structure.collect_login_structure", rogue)
    previous_hook = sys.excepthook
    previous_limit = getattr(sys, "tracebacklimit", 1000)
    try:
        code = __import__("asyncio").run(module._run())
    finally:
        sys.excepthook = previous_hook
        sys.tracebacklimit = previous_limit
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["post_admitted"] is False
    assert payload["observed_stage"] == "not-reached"
    assert payload["structure_class"] == "not-decoded"
    assert payload["status_class"] == "ok"
    assert "html" not in payload
    _assert_closed(payload)
    assert "Traceback" not in captured.err


def test_runner_request_failure_has_no_traceback(monkeypatch, capsys):
    module = _load_runner()

    async def boom():
        raise RuntimeError("fixture-runner-secret https://example.test/fail")

    monkeypatch.setattr("nccn_monitor.login_structure.collect_login_structure", boom)
    previous_hook = sys.excepthook
    previous_limit = getattr(sys, "tracebacklimit", 1000)
    try:
        code = __import__("asyncio").run(module._run())
    finally:
        sys.excepthook = previous_hook
        sys.tracebacklimit = previous_limit
    captured = capsys.readouterr()
    assert code == 2
    payload = json.loads(captured.out)
    assert payload["error"] == "request_failed"
    assert payload["post_admitted"] is False
    _assert_closed(payload)
    assert "Traceback" not in captured.err


def test_runner_pins_import_without_a_network_call(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    isolate = tmp_path / "isolate"
    for relative in (
        "scripts/observe_login_structure.py",
        "src/nccn_monitor/__init__.py",
        "src/nccn_monitor/login_structure.py",
    ):
        target = isolate / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / relative).read_bytes())
    dirty = tmp_path / "dirty"
    package = dirty / "nccn_monitor"
    package.mkdir(parents=True)
    marker = tmp_path / "dirty-imported"
    (package / "__init__.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('dirty')\n")
    (package / "login_structure.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('dirty')\n"
        "PUBLIC_LOGIN_URL = 'http://evil.example/secret'\n"
    )
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import importlib.util, sys\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('observer', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "module._pin_import()\n"
        "import nccn_monitor.login_structure as observed\n"
        "print(Path(observed.__file__).resolve())\n"
    )
    import os
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(probe), str(isolate / "scripts" / "observe_login_structure.py")],
        cwd=str(tmp_path),
        env={
            **{key: value for key, value in os.environ.items() if "PASSWORD" not in key.upper()},
            "PYTHONPATH": str(dirty),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    assert completed.stdout.strip() == str((isolate / "src" / "nccn_monitor" / "login_structure.py").resolve())
    assert "evil.example" not in completed.stdout
    assert "Traceback" not in completed.stderr


def test_production_login_does_not_call_the_observer():
    import inspect

    login_source = inspect.getsource(NCCNDownloader.login)
    diagnose_source = inspect.getsource(NCCNDownloader.diagnose_login)
    for source in (login_source, diagnose_source):
        assert "login_structure" not in source
        assert "classify_login_structure" not in source
        assert "post_admitted" not in source
    downloader_text = Path(__file__).resolve().parents[1].joinpath("src/nccn_monitor/downloader.py").read_text()
    assert "observe_login_structure" not in downloader_text
    assert "classify_login_structure" not in downloader_text


async def test_static_prose_stays_stopped_in_diagnose_login():
    html = _page(_form(), "<p>recaptcha fixture-prose-secret</p>")
    posts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/html"}, content=html.encode())

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        diag = await downloader.diagnose_login(PUBLIC_LOGIN_URL)
    finally:
        await downloader.close()
    label = classify_login_structure(html)
    assert posts["n"] == 0
    assert diag["observed_stage"] == "get"
    assert diag["get_challenge_class"] == "captcha-marker"
    assert label["structure_class"] == "static-reference"
    assert label["post_admitted"] is False
    _assert_closed(label)


async def test_observer_does_not_post_when_diagnose_login_still_would():
    html = _page(_form())
    posts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts["n"] += 1
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<html><body><p>Account Settings</p><p>Log Out</p></body></html>",
            )
        return httpx.Response(200, headers={"content-type": "text/html"}, content=html.encode())

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        diag = await downloader.diagnose_login(PUBLIC_LOGIN_URL)
    finally:
        await downloader.close()
    assert posts["n"] == 1
    assert diag["observed_stage"] == "post"
    assert classify_login_structure(html)["structure_class"] == "none-visible"
    assert classify_login_structure(html)["post_admitted"] is False
