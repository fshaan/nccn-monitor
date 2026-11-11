"""Stage A regressions for the weekly auth/download miss.

Synthetic fixtures only. These tests do not log in, do not read config.yaml or
environment secrets, and do not open a real archive or state file. They are
expected to fail until production download and state handling is fixed.

The locked outcomes do not assume why login returned false:

- A later check must still try to archive a version that is already recorded
  when that version's PDF is absent.
- A failed download must not make the next check report that nothing changed.
- HTML/login bytes, patient guides, and PDFs with the wrong title or version
  must not count as an archived professional guideline.
- Older archived versions stay byte-for-byte intact.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import httpx
import pytest
from pypdf import PdfReader

from nccn_monitor.downloader import (
    ARCHIVE_BLOCKED_INVALID_EXISTING,
    ARCHIVE_VALID,
    BLOCKED_EXISTING_PDF_MESSAGE,
    NCCNDownloader,
    classify_current_archive,
    get_archived_versions,
)
from nccn_monitor.scraper import (
    GuidelineInfo,
    PdfIndexEntry,
    format_pdf_filename,
    parse_detail_page_for_pdf,
    slugify,
)
from nccn_monitor.state import StateManager

FIXTURES = Path(__file__).parent / "fixtures"
PROFESSIONAL_GASTRIC_URL = "https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf"
PATIENT_STOMACH_URL = "https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf"
OLD_GASTRIC_BYTES = b"%PDF-1.4\n%fixture-old-gastric-professional\n"
OLD_COLON_BYTES = b"%PDF-1.4\n%fixture-old-colon-professional\n"


def _read_fixture(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def _pdf_text(path: Path) -> str:
    """Text extraction only. No page size, rotation, or coordinate checks."""
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _write_archived_version(
    archive: Path,
    slug: str,
    version: str,
    name: str,
    pdf_url: str,
    payload: bytes,
) -> Path:
    directory = archive / slug / f"v{version}"
    directory.mkdir(parents=True, exist_ok=True)
    filename = format_pdf_filename(name, version)
    pdf_path = directory / filename
    pdf_path.write_bytes(payload)
    meta = {
        "version": version,
        "slug": slug,
        "name": name,
        "filename": filename,
        "pdf_url": pdf_url,
        "downloaded_at": "2026-03-20T00:00:00+00:00",
        "size_bytes": len(payload),
    }
    (directory / "meta.json").write_text(json.dumps(meta, indent=2))
    return pdf_path


def _bind_client(downloader: NCCNDownloader, responses: list[tuple[str, bytes]]) -> None:
    """Serve fixture bodies for www.nccn.org without opening a socket."""
    pending = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host not in {"www.nccn.org", "nccn.org"}:
            raise AssertionError(f"unexpected host {host}")
        if not pending:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        content_type, body = pending.pop(0)
        return httpx.Response(200, headers={"Content-Type": content_type}, content=body)

    downloader._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def _install_fastmcp_stub() -> None:
    """Let check_updates be imported when the installed mcp package has no FastMCP.

    A fresh resolve of mcp[cli]>=1.11.0 on 2026-11-11 installed mcp 2.3.0, and
    importing mcp.server.fastmcp raises. The weekly failure reached
    downloader.login, so this stub is only an import shim for the coroutine.
    """
    stub = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            def deco(fn):
                return fn
            return deco

        def run(self, *args, **kwargs):
            return None

    stub.FastMCP = FastMCP
    sys.modules["mcp.server.fastmcp"] = stub


def _load_isolated_server(monkeypatch: pytest.MonkeyPatch, home: Path):
    home.mkdir(parents=True, exist_ok=True)
    work = home / "work"
    work.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("NCCN_USERNAME", "fixture-user")
    monkeypatch.setenv("NCCN_PASSWORD", "fixture-password")
    monkeypatch.chdir(work)
    assert Path.home() == home
    _install_fastmcp_stub()

    import importlib
    import nccn_monitor.server as server

    return importlib.reload(server)


def _catalog(versions: dict[str, str]) -> list[GuidelineInfo]:
    ids = {"Gastric Cancer": "1003", "Colon Cancer": "1004", "Breast Cancer": "1005"}
    return [
        GuidelineInfo(
            name=name,
            version=version,
            detail_url=f"https://www.nccn.org/guidelines/guidelines-detail?category=1&id={ids[name]}",
            category="Cancer by Type",
        )
        for name, version in versions.items()
    ]


def _index_for(guidelines: list[GuidelineInfo]) -> list[PdfIndexEntry]:
    stems = {
        "Gastric Cancer": "gastric",
        "Colon Cancer": "colon",
        "Breast Cancer": "breast",
    }
    return [
        PdfIndexEntry(
            name=item.name,
            slug=slugify(item.name),
            pdf_url=f"https://www.nccn.org/professionals/physician_gls/pdf/{stems[item.name]}.pdf",
            version=item.version,
            detail_url=item.detail_url,
            category=item.category,
        )
        for item in guidelines
    ]


# ── Detail-page audience selection ───────────────────────────────────


def test_detail_page_skips_patient_link_listed_before_professional():
    html = _read_fixture("auth/detail_patient_before_professional.html").decode()
    pdf_url = parse_detail_page_for_pdf(html)
    assert pdf_url == PROFESSIONAL_GASTRIC_URL


def test_detail_page_returns_none_when_only_patient_guide_is_listed():
    html = _read_fixture("auth/detail_patient_only.html").decode()
    assert parse_detail_page_for_pdf(html) is None


def test_detail_page_fallback_skips_patient_and_blocks_filenames():
    html = _read_fixture("auth/detail_patient_filename_without_gl_header.html").decode()
    assert parse_detail_page_for_pdf(html) == PROFESSIONAL_GASTRIC_URL


# ── Archive acceptance ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture_rel", "pdf_url"),
    [
        ("auth/login_wall.html", PROFESSIONAL_GASTRIC_URL),
        ("pdf/patient_stomach.pdf", PATIENT_STOMACH_URL),
        ("pdf/professional_breast_v2_2026.pdf", PROFESSIONAL_GASTRIC_URL),
        ("pdf/professional_gastric_v1_2025.pdf", PROFESSIONAL_GASTRIC_URL),
    ],
)
async def test_download_and_archive_rejects_html_patient_wrong_title_or_version(
    tmp_path: Path, fixture_rel: str, pdf_url: str
):
    """A mismatched body must not become the Gastric Cancer 2.2026 archive.

    Fixture bodies are, in order: a login HTML page, a patient-guide PDF,
    a Breast Cancer professional PDF at the requested version, and a Gastric
    Cancer professional PDF at a different version. All are served as
    application/pdf, which is the branch that currently stores the bytes.
    """
    archive = tmp_path / "archive"
    old_pdf = _write_archived_version(
        archive,
        "gastric-cancer",
        "1.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        OLD_GASTRIC_BYTES,
    )
    old_pdf_bytes = old_pdf.read_bytes()
    old_meta_bytes = (old_pdf.parent / "meta.json").read_bytes()
    body = _read_fixture(fixture_rel)

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    _bind_client(downloader, [("application/pdf", body)])
    try:
        result = await downloader.download_and_archive(
            pdf_url,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    new_dir = archive / "gastric-cancer" / "v2.2026"
    archived_pdfs = list(new_dir.glob("*.pdf")) if new_dir.exists() else []
    archived_meta = new_dir / "meta.json"
    assert result is None
    assert archived_pdfs == []
    assert not archived_meta.exists()
    assert old_pdf.read_bytes() == old_pdf_bytes
    assert (old_pdf.parent / "meta.json").read_bytes() == old_meta_bytes


async def test_existing_login_html_named_as_pdf_is_not_archived_completion(tmp_path: Path):
    """An HTML file already stored under the professional filename is not done."""
    archive = tmp_path / "archive"
    old_pdf = _write_archived_version(
        archive,
        "gastric-cancer",
        "1.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        _read_fixture("pdf/professional_gastric_v1_2026.pdf"),
    )
    old_pdf_bytes = old_pdf.read_bytes()
    old_meta_bytes = (old_pdf.parent / "meta.json").read_bytes()
    html = _read_fixture("auth/login_wall.html")
    new_pdf = _write_archived_version(
        archive,
        "gastric-cancer",
        "2.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        html,
    )
    assert new_pdf.read_bytes() == html

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    _bind_client(
        downloader,
        [("application/pdf", html), ("application/pdf", html)],
    )
    try:
        first = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
        second = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    listed = [
        item["version"]
        for item in get_archived_versions("gastric-cancer", archive_dir=archive)
    ]
    assert first is None
    assert second is None
    assert "2.2026" not in listed
    assert listed == ["1.2026"]
    assert old_pdf.read_bytes() == old_pdf_bytes
    assert (old_pdf.parent / "meta.json").read_bytes() == old_meta_bytes


async def test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf(tmp_path: Path):
    """Retry must be able to store a matching PDF over a login page at that path.

    The previous version's %PDF bytes stay in place. Only the non-PDF occupant
    of the requested version may be replaced. Name and version are read from
    extracted text, not from uncompressed file bytes.
    """
    archive = tmp_path / "archive"
    old_pdf = _write_archived_version(
        archive,
        "gastric-cancer",
        "1.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        _read_fixture("pdf/professional_gastric_v1_2026.pdf"),
    )
    old_pdf_bytes = old_pdf.read_bytes()
    old_meta_bytes = (old_pdf.parent / "meta.json").read_bytes()
    html = _read_fixture("auth/login_wall.html")
    _write_archived_version(
        archive,
        "gastric-cancer",
        "2.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        html,
    )
    good_pdf = _read_fixture("pdf/professional_gastric_v2_2026.pdf")

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    _bind_client(downloader, [("application/pdf", good_pdf)])
    try:
        result = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    assert result is not None
    assert result.read_bytes().startswith(b"%PDF")
    text = _pdf_text(result)
    assert "Gastric Cancer" in text
    assert "2.2026" in text
    assert old_pdf.read_bytes() == old_pdf_bytes
    assert (old_pdf.parent / "meta.json").read_bytes() == old_meta_bytes
    listed = [
        item["version"]
        for item in get_archived_versions("gastric-cancer", archive_dir=archive)
    ]
    assert listed == ["2.2026", "1.2026"]


async def test_compressed_professional_cover_with_patient_crosslink_is_archived(tmp_path: Path):
    """A professional cover may mention the patient series, including in a compressed stream.

    Acceptance uses extracted text. The raw file is FlateDecode and does not
    contain those phrases as plaintext, and no page geometry is asserted.
    """
    archive = tmp_path / "archive"
    old_pdf = _write_archived_version(
        archive,
        "gastric-cancer",
        "1.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        OLD_GASTRIC_BYTES,
    )
    old_pdf_bytes = old_pdf.read_bytes()
    old_meta_bytes = (old_pdf.parent / "meta.json").read_bytes()
    body = _read_fixture("pdf/professional_gastric_v2_2026_compressed.pdf")
    assert b"Gastric Cancer" not in body
    assert b"Guidelines for Patients" not in body
    assert b"Clinical Practice Guidelines" not in body

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    _bind_client(downloader, [("application/pdf", body)])
    try:
        result = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    assert result is not None
    assert result.read_bytes().startswith(b"%PDF")
    text = _pdf_text(result)
    assert "Clinical Practice Guidelines in Oncology" in text
    assert "Gastric Cancer" in text
    assert "2.2026" in text
    assert "Guidelines for Patients" in text
    assert old_pdf.read_bytes() == old_pdf_bytes
    assert (old_pdf.parent / "meta.json").read_bytes() == old_meta_bytes


def _occupied_version(archive: Path, payload: bytes) -> Path:
    return _write_archived_version(
        archive,
        "gastric-cancer",
        "2.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        payload,
    )


@pytest.mark.parametrize(
    ("fixture_rel", "payload"),
    [
        ("pdf/professional_breast_v2_2026.pdf", None),
        ("pdf/professional_gastric_v1_2025.pdf", None),
        ("", b"%PDF-1.4\n%truncated\n"),
    ],
)
async def test_existing_invalid_pdf_is_blocked_and_not_replaced(
    tmp_path: Path, fixture_rel: str, payload: bytes | None
):
    """A %PDF at the target path that is corrupt or the wrong guideline stays put.

    A matching professional response is available and must not be written over it.
    """
    archive = tmp_path / "archive"
    body = payload if payload is not None else _read_fixture(fixture_rel)
    occupied = _occupied_version(archive, body)
    original = occupied.read_bytes()
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=_read_fixture("pdf/professional_gastric_v2_2026.pdf"),
        )

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    downloader._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    try:
        result = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    assert result is None
    assert requests == []
    assert occupied.read_bytes() == original
    assert classify_current_archive(
        "gastric-cancer", "2.2026", "Gastric Cancer", archive,
    ) == ARCHIVE_BLOCKED_INVALID_EXISTING
    listed = [
        item["version"]
        for item in get_archived_versions("gastric-cancer", archive_dir=archive)
    ]
    assert "2.2026" not in listed


async def test_legacy_valid_professional_pdf_stays_completed_and_unchanged(tmp_path: Path):
    """An existing PDF that already matches name and version is left byte-for-byte."""
    archive = tmp_path / "archive"
    payload = _read_fixture("pdf/professional_gastric_v2_2026.pdf")
    occupied = _occupied_version(archive, payload)
    original = occupied.read_bytes()

    def handler(request):
        raise AssertionError(f"valid archive was downloaded again: {request.url}")

    downloader = NCCNDownloader("fixture-user", "fixture-password")
    downloader._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    try:
        result = await downloader.download_and_archive(
            PROFESSIONAL_GASTRIC_URL,
            "gastric-cancer",
            "2.2026",
            name="Gastric Cancer",
            archive_dir=archive,
        )
    finally:
        await downloader.close()

    assert result == occupied
    assert occupied.read_bytes() == original
    assert classify_current_archive(
        "gastric-cancer", "2.2026", "Gastric Cancer", archive,
    ) == ARCHIVE_VALID
    text = _pdf_text(occupied)
    assert "Gastric Cancer" in text
    assert "2.2026" in text
    assert "Clinical Practice Guidelines in Oncology" in text
    listed = [
        item["version"]
        for item in get_archived_versions("gastric-cancer", archive_dir=archive)
    ]
    assert listed == ["2.2026"]


async def test_check_updates_reports_blocked_existing_pdf_without_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    home = tmp_path / "home"
    server = _load_isolated_server(monkeypatch, home)
    archive = home / "archive"
    server.config["archive_dir"] = str(archive)
    server.config["watch_list"] = ["Gastric Cancer"]
    server.config["analysis"] = {"enabled": True, "update_notes_pages": 5, "language": "zh-CN"}
    occupied = _occupied_version(archive, _read_fixture("pdf/professional_breast_v2_2026.pdf"))
    original = occupied.read_bytes()
    state_path = server.state_mgr.path
    state_path.write_text(json.dumps({
        "last_check": "2026-11-11T00:00:00+00:00",
        "initialized": True,
        "guidelines": {
            "Gastric Cancer": {
                "version": "2.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-11-11T00:00:00+00:00",
            },
        },
    }))
    server.state_mgr = StateManager(state_path)
    calls: list[dict] = []
    _install_catalog(
        monkeypatch,
        server,
        {"Gastric Cancer": "2.2026"},
        calls,
    )

    report = await server.check_updates()

    assert BLOCKED_EXISTING_PDF_MESSAGE in report
    assert "No guideline updates detected" not in report
    assert calls == []
    assert occupied.read_bytes() == original


async def test_login_diagnostic_returns_only_safe_fields(caplog):
    """The diagnostic observes a mocked exchange and does not echo secrets."""
    secret_query = "fixture-query-secret"
    cookie_secret = "fixture-cookie-secret"
    username = "fixture-user"
    password = "fixture-password"
    login_html = """<!DOCTYPE html><html><body>
      <form action="/login/Index/" method="post">
        <input type="hidden" name="__RequestVerificationToken" value="fixture-token" />
        <input type="password" name="Password" />
        <p>Log in</p>
      </form></body></html>"""
    done_html = "<html><body><p>Account Settings</p><p>Log Out</p></body></html>"
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path != "/home":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": f"session={cookie_secret}",
                },
                content=login_html.encode(),
            )
        if request.method == "POST":
            return httpx.Response(
                302,
                headers={"Location": f"https://www.nccn.org/home?token={secret_query}"},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=done_html.encode(),
        )

    downloader = NCCNDownloader(username, password)
    downloader._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    try:
        with caplog.at_level("DEBUG"):
            diag = await downloader.diagnose_login(
                f"https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf?token={secret_query}"
            )
    finally:
        await downloader.close()

    assert diag == {
        "status_code": 200,
        "host_class": "nccn",
        "path_class": "other",
        "content_type": "text/html",
        "has_login_form": False,
        "has_account": True,
        "has_logout": True,
    }
    rendered = json.dumps(diag)
    log_text = caplog.text
    for secret in (secret_query, cookie_secret, username, password, "fixture-token"):
        assert secret not in rendered
        assert secret not in log_text
    assert seen[0][0] == "GET"
    assert seen[1][0] == "POST"


# ── Weekly check retry ───────────────────────────────────────────────


def _install_catalog(monkeypatch: pytest.MonkeyPatch, server, versions: dict[str, str], calls: list[dict]):
    async def fake_guidelines():
        return _catalog(versions)

    async def fake_index(guidelines, index_file="~/.nccn-monitor/index.yaml"):
        return _index_for(list(guidelines))

    async def fake_download(
        pdf_url,
        slug,
        version,
        name="",
        archive_dir="~/.nccn-monitor/archive",
        filename="",
    ):
        calls.append(
            {
                "pdf_url": pdf_url,
                "slug": slug,
                "version": version,
                "name": name,
                "archive_dir": archive_dir,
                "filename": filename,
            }
        )
        return None

    async def forbid_real_client(self):
        raise AssertionError("NCCNDownloader opened a real HTTP client")

    monkeypatch.setattr(server, "fetch_all_guidelines", fake_guidelines)
    monkeypatch.setattr(server, "fetch_pdf_index", fake_index)
    monkeypatch.setattr(server.NCCNDownloader, "_get_client", forbid_real_client)
    server.downloader.download_and_archive = fake_download


def _seed_prior_archives(archive: Path) -> dict[Path, bytes]:
    gastric = _write_archived_version(
        archive,
        "gastric-cancer",
        "1.2026",
        "Gastric Cancer",
        PROFESSIONAL_GASTRIC_URL,
        OLD_GASTRIC_BYTES,
    )
    colon = _write_archived_version(
        archive,
        "colon-cancer",
        "4.2026",
        "Colon Cancer",
        "https://www.nccn.org/professionals/physician_gls/pdf/colon.pdf",
        OLD_COLON_BYTES,
    )
    return {gastric: gastric.read_bytes(), colon: colon.read_bytes(),
            gastric.parent / "meta.json": (gastric.parent / "meta.json").read_bytes(),
            colon.parent / "meta.json": (colon.parent / "meta.json").read_bytes()}


def _assert_prior_archives_unchanged(snapshots: dict[Path, bytes]) -> None:
    for path, payload in snapshots.items():
        assert path.read_bytes() == payload


async def test_check_updates_retries_when_recorded_version_has_no_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """MBP16 shape: the new version is already in state and its PDF is absent."""
    home = tmp_path / "home"
    server = _load_isolated_server(monkeypatch, home)
    archive = home / "archive"
    server.config["archive_dir"] = str(archive)
    server.config["watch_list"] = ["Gastric Cancer", "Colon Cancer"]
    server.config["analysis"] = {"enabled": True, "update_notes_pages": 5, "language": "zh-CN"}

    state_path = server.state_mgr.path
    state_path.write_text(json.dumps({
        "last_check": "2026-11-11T00:00:00+00:00",
        "initialized": True,
        "guidelines": {
            "Gastric Cancer": {
                "version": "2.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-11-11T00:00:00+00:00",
            },
            "Colon Cancer": {
                "version": "4.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-03-20T00:00:00+00:00",
            },
            "Breast Cancer": {
                "version": "1.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-03-01T00:00:00+00:00",
            },
        },
    }))
    server.state_mgr = StateManager(state_path)
    snapshots = _seed_prior_archives(archive)
    versions = {
        "Gastric Cancer": "2.2026",
        "Colon Cancer": "4.2026",
        "Breast Cancer": "2.2026",
    }
    calls: list[dict] = []
    _install_catalog(monkeypatch, server, versions, calls)

    report = await server.check_updates()

    stored = json.loads(state_path.read_text())
    assert stored["guidelines"]["Colon Cancer"]["version"] == "4.2026"
    assert stored["guidelines"]["Breast Cancer"]["version"] == "1.2026"
    assert "fixture-password" not in state_path.read_text()
    _assert_prior_archives_unchanged(snapshots)
    assert "No guideline updates detected" not in report
    assert [call["name"] for call in calls] == ["Gastric Cancer"]
    call = calls[0]
    assert call["pdf_url"] == PROFESSIONAL_GASTRIC_URL
    assert call["slug"] == "gastric-cancer"
    assert call["version"] == "2.2026"
    assert call["archive_dir"] == str(archive)


async def test_check_updates_retries_after_download_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A failed archive attempt must leave the same version retryable."""
    home = tmp_path / "home"
    server = _load_isolated_server(monkeypatch, home)
    archive = home / "archive"
    server.config["archive_dir"] = str(archive)
    server.config["watch_list"] = ["Gastric Cancer", "Colon Cancer"]
    server.config["analysis"] = {"enabled": True, "update_notes_pages": 5, "language": "zh-CN"}
    snapshots = _seed_prior_archives(archive)
    versions = {
        "Gastric Cancer": "1.2026",
        "Colon Cancer": "4.2026",
        "Breast Cancer": "1.2026",
    }
    calls: list[dict] = []
    _install_catalog(monkeypatch, server, versions, calls)

    baseline = await server.check_updates()
    assert "No guideline updates detected" in baseline
    assert calls == []

    versions["Gastric Cancer"] = "2.2026"
    versions["Breast Cancer"] = "2.2026"
    failed = await server.check_updates()
    assert "PDF download failed" in failed
    assert [call["name"] for call in calls] == ["Gastric Cancer"]
    assert calls[0]["version"] == "2.2026"
    assert calls[0]["archive_dir"] == str(archive)

    retried = await server.check_updates()

    stored = json.loads(server.state_mgr.path.read_text())
    assert stored["guidelines"]["Colon Cancer"]["version"] == "4.2026"
    assert "Breast Cancer" not in stored["guidelines"]
    assert "fixture-password" not in server.state_mgr.path.read_text()
    _assert_prior_archives_unchanged(snapshots)
    assert "No guideline updates detected" not in retried
    gastric_versions = [call["version"] for call in calls if call["name"] == "Gastric Cancer"]
    assert gastric_versions == ["2.2026", "2.2026"]
    assert all(call["name"] != "Colon Cancer" for call in calls)
    assert all(call["name"] != "Breast Cancer" for call in calls)
