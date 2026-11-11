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
    }


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
    assert "http://" not in completed.stdout
    assert "https://" not in completed.stdout
