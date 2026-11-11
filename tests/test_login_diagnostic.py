"""Leak tests for the bounded login diagnostic. No live NCCN call."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx

from nccn_monitor.downloader import NCCNDownloader

SECRET_QUERY = "fixture-query-secret"
SECRET_PATH = "fixture-path-secret"
SECRET_COOKIE = "fixture-cookie-secret"
SECRET_USER = "fixture-user"
SECRET_PASSWORD = "fixture-password"
SECRET_EXC = "fixture-exception-secret"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def _records_text(records: list[logging.LogRecord]) -> str:
    parts = []
    for record in records:
        parts.append(record.getMessage())
        if record.exc_info and record.exc_info[1] is not None:
            parts.append(str(record.exc_info[1]))
        if record.args:
            parts.append(repr(record.args))
    return "\n".join(parts)


async def test_path_and_query_secrets_stay_out_of_diagnostic(caplog):
    login_html = """<!DOCTYPE html><html><body>
      <form action="/login/Index/" method="post">
        <input type="hidden" name="__RequestVerificationToken" value="fixture-token" />
        <input type="password" name="Password" />
      </form></body></html>"""
    done_html = "<html><body><p>Account Settings</p><p>Log Out</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        logging.getLogger("httpx").error("transport error %s", request.url)
        logging.getLogger("httpcore").warning("core warning %s", request.url)
        if request.method == "POST":
            location = (
                "https://www.nccn.org/session/"
                f"{SECRET_PATH}/continue?token={SECRET_QUERY}"
            )
            return httpx.Response(302, headers={"Location": location})
        if request.url.path.startswith("/session/"):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": f"text/html; secret={SECRET_QUERY}",
                    "Set-Cookie": f"session={SECRET_COOKIE}",
                },
                content=done_html.encode(),
            )
        return httpx.Response(200, content=login_html.encode())

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = _client(handler)
    try:
        with caplog.at_level(logging.DEBUG):
            diag = await downloader.diagnose_login(
                f"https://www.nccn.org/login/Index/?token={SECRET_QUERY}"
            )
    finally:
        await downloader.close()

    assert diag["host_class"] == "nccn"
    assert diag["path_class"] == "other"
    assert diag["content_type"] == "text/html"
    assert diag["has_account"] is True
    assert diag["has_logout"] is True
    rendered = json.dumps(diag)
    for secret in (SECRET_QUERY, SECRET_PATH, SECRET_COOKIE, SECRET_USER, SECRET_PASSWORD, "fixture-token"):
        assert secret not in rendered
        assert secret not in caplog.text
    assert set(diag) == {
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
    }
    assert diag["observed_stage"] == "post"
    assert diag["get_form_action_class"] == "exact-relative"


async def test_transport_errors_do_not_leak_and_logging_is_restored():
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    previous_disable = logging.root.manager.disable
    httpx_logger.setLevel(logging.DEBUG)
    captured: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler_obj = Capture(level=logging.DEBUG)
    logging.getLogger().addHandler(handler_obj)
    httpx_logger.addHandler(handler_obj)

    def handler(request: httpx.Request) -> httpx.Response:
        logging.getLogger("httpx").error("error url %s", request.url)
        logging.getLogger("httpcore.http11").warning("warn query %s", SECRET_QUERY)
        raise RuntimeError(f"{SECRET_EXC} {request.url}")

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = _client(handler)
    try:
        diag = await downloader.diagnose_login("https://www.nccn.org/login/Index/")
        logging.getLogger("httpx").error("after-marker-visible")
    finally:
        await downloader.close()
        logging.getLogger().removeHandler(handler_obj)
        httpx_logger.removeHandler(handler_obj)
        httpx_logger.setLevel(previous_level)

    assert diag["error"] == "request_failed"
    assert diag["host_class"] == "other"
    assert diag["path_class"] == "other"
    leaked = _records_text(captured)
    for secret in (SECRET_EXC, SECRET_QUERY, SECRET_USER, SECRET_PASSWORD, "login/Index"):
        assert secret not in leaked
        assert secret not in json.dumps(diag)
    assert "after-marker-visible" in leaked
    assert logging.root.manager.disable == previous_disable


def test_diagnostic_runner_without_config_prints_only_allowlisted_error(tmp_path: Path):
    runner = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_nccn_login.py"
    source = runner.read_text()
    assert "nccn_monitor.weekly" not in source
    assert "fetch_all_guidelines" not in source
    assert "StateManager" not in source
    assert "download_and_archive" not in source
    assert "/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml" in source
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in ("NCCN", "PASSWORD", "SECRET", "TOKEN", "COOKIE"))
    }
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["error"] == "credentials_not_configured"
    assert SECRET_PASSWORD not in completed.stdout
    assert SECRET_PASSWORD not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "http://" not in completed.stdout
    assert "https://" not in completed.stdout


def _runner_env(home: Path, pythonpath: str | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in ("NCCN", "PASSWORD", "SECRET", "TOKEN", "COOKIE"))
    }
    env["HOME"] = str(home)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    else:
        env.pop("PYTHONPATH", None)
    return env


def test_yaml_failure_stdout_is_allowlisted_and_stderr_has_no_traceback(tmp_path: Path):
    config_dir = tmp_path / ".nccn_watcher"
    config_dir.mkdir()
    secret = "fixture-yaml-secret"
    (config_dir / "config.yaml").write_text(
        "nccn:\n  username: fixture-user\n  password: "
        + secret
        + "\n  bad: [\n"
    )
    runner = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_nccn_login.py"
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(tmp_path),
        env=_runner_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["error"] == "request_failed"
    assert set(payload) <= {
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
    }
    assert secret not in completed.stdout
    assert secret not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "config.yaml" not in completed.stderr


def test_runner_loads_script_src_not_pythonpath_dirty_module(tmp_path: Path):
    dirty = tmp_path / "dirty"
    package = dirty / "nccn_monitor"
    package.mkdir(parents=True)
    marker = tmp_path / "dirty-imported"
    (package / "__init__.py").write_text("")
    (package / "downloader.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('dirty')\n"
        "class NCCNDownloader:\n"
        "    def __init__(self, username=None, password=None):\n"
        "        pass\n"
        "    async def diagnose_login(self, target_url):\n"
        "        return {'error': 'dirty-loaded'}\n"
        "    async def close(self):\n"
        "        pass\n"
    )
    isolate = tmp_path / "isolate"
    repo = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/diagnose_nccn_login.py",
        "src/nccn_monitor/__init__.py",
        "src/nccn_monitor/downloader.py",
    ):
        target = isolate / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / relative).read_bytes())
    work = tmp_path / "work"
    work.mkdir()
    completed = subprocess.run(
        [sys.executable, str(isolate / "scripts" / "diagnose_nccn_login.py")],
        cwd=str(work),
        env=_runner_env(tmp_path / "home", pythonpath=str(dirty)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert not marker.exists()
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["error"] == "credentials_not_configured"
    assert "dirty-loaded" not in completed.stdout
    assert "Traceback" not in completed.stderr


def test_runner_does_not_create_state_or_pdf(tmp_path: Path):
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    runner = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_nccn_login.py"
    before = {path.relative_to(work) for path in work.rglob("*")}
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(work),
        env=_runner_env(home),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["error"] == "credentials_not_configured"
    assert not (home / ".nccn-monitor" / "state.json").exists()
    assert list(work.rglob("*.pdf")) == []
    assert {path.relative_to(work) for path in work.rglob("*")} == before


def test_close_failure_does_not_print_traceback(monkeypatch, capsys):
    import importlib.util

    runner = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_nccn_login.py"
    spec = importlib.util.spec_from_file_location("diagnose_nccn_login_under_test", runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "fixture-close-secret"
    import nccn_monitor.downloader as downloader_module

    class Boom(downloader_module.NCCNDownloader):
        async def diagnose_login(self, target_url):
            return {
                "status_code": 200,
                "host_class": "nccn",
                "path_class": "login",
                "content_type": "text/html",
                "has_login_form": True,
                "has_account": False,
                "has_logout": False,
            }

        async def close(self):
            raise RuntimeError(secret + " password: fixture-yaml-secret")

    monkeypatch.setattr(downloader_module, "NCCNDownloader", Boom)
    monkeypatch.setattr(module, "load_config", lambda config_path="": {"nccn": {"username": "u", "password": "p"}})
    code = asyncio_run(module)
    captured = capsys.readouterr()
    assert code == 0
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err
    assert json.loads(captured.out)["path_class"] == "login"


def asyncio_run(module):
    import asyncio
    return asyncio.run(module._run())


def _form(action: str, password_type: str = "password", hidden_value: str = "fixture-hidden-secret") -> str:
    return (
        "<!DOCTYPE html><html><body>"
        f"<form action=\"{action}\" method=\"post\">"
        f"<input type=\"hidden\" name=\"__RequestVerificationToken\" value=\"{hidden_value}\" />"
        "<input type=\"text\" name=\"Username\" />"
        f"<input type=\"{password_type}\" name=\"Password\" />"
        "<input type=\"hidden\" name=\"ReturnUrl\" value=\"fixture-return-secret\" />"
        "</form></body></html>"
    )


async def _diag_for(html: str, monkeypatch=None) -> tuple[dict, int]:
    posts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts["n"] += 1
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                content=b"<html><body><p>Account Settings</p><p>Log Out</p></body></html>",
            )
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=html.encode())

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = _client(handler)
    try:
        diag = await downloader.diagnose_login("https://www.nccn.org/login/Index/")
    finally:
        await downloader.close()
    rendered = json.dumps(diag)
    for secret in (SECRET_USER, SECRET_PASSWORD, "fixture-hidden-secret", "fixture-return-secret"):
        assert secret not in rendered
    return diag, posts["n"]


async def test_observed_stage_is_post_only_after_exact_form_submit():
    posted, posts = await _diag_for(_form("/login/Index/"))
    assert posts == 1
    assert posted["observed_stage"] == "post"
    assert posted["get_form_action_class"] == "exact-relative"
    assert posted["get_password_control"] == "type-password"
    assert posted["get_username_control"] == "present"
    assert posted["get_hidden_count_class"] == "several"
    assert posted["get_challenge_class"] == "none"
    assert posted["get_body_decodable"] is True
    absent, posts = await _diag_for("<html><body><p>no form</p></body></html>")
    assert posts == 0
    assert absent["observed_stage"] == "get"
    assert absent["get_form_action_class"] == "absent"


async def test_action_classes_do_not_submit_unless_exact_relative():
    cases = {
        "/login/index": "slash-or-case-variant",
        "https://www.nccn.org/login/Index/": "slash-or-case-variant",
        "https://www.nccn.org/account/login": "absolute-nccn",
        "https://evil.example/login": "other",
    }
    for action, expected in cases.items():
        diag, posts = await _diag_for(_form(action))
        assert posts == 0
        assert diag["observed_stage"] == "get"
        assert diag["get_form_action_class"] == expected
        assert "evil.example" not in json.dumps(diag)
        assert "account/login" not in json.dumps(diag)


async def test_br_without_decoder_does_not_post(monkeypatch):
    from httpx._decoders import SUPPORTED_DECODERS

    monkeypatch.setattr("nccn_monitor.downloader._brotli_decoder_present", lambda: False)
    monkeypatch.delitem(SUPPORTED_DECODERS, "br", raising=False)
    posts = {"n": 0}
    secret = "fixture-br-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts["n"] += 1
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html", "Content-Encoding": "br"},
            content=_form("/login/Index/").encode() + secret.encode(),
        )

    downloader = NCCNDownloader(SECRET_USER, SECRET_PASSWORD)
    downloader._client = _client(handler)
    try:
        diag = await downloader.diagnose_login("https://www.nccn.org/login/Index/")
    finally:
        await downloader.close()
    assert posts["n"] == 0
    assert diag["observed_stage"] == "get"
    assert diag["get_content_encoding_class"] == "br"
    assert diag["final_content_encoding_class"] == "br"
    assert diag["get_body_decodable"] is False
    assert diag["brotli_decoder_present"] is False
    assert diag["get_form_action_class"] == "not-decoded"
    assert secret not in json.dumps(diag)


async def test_challenge_marker_does_not_post_credentials():
    html = _form("/login/Index/") + "<p>recaptcha fixture-challenge-secret</p>"
    diag, posts = await _diag_for(html)
    assert posts == 0
    assert diag["observed_stage"] == "get"
    assert diag["get_challenge_class"] == "captcha-marker"
    assert "fixture-challenge-secret" not in json.dumps(diag)
    interstitial, posts = await _diag_for("<html><body>Just a moment</body></html>")
    assert posts == 0
    assert interstitial["get_challenge_class"] == "interstitial-marker"
