"""Weekly entry: the external script's detect-then-download path.

The sanitized wrapper returns 0 when ``detect_changes`` is empty. A recorded
current version with no valid PDF must still be downloaded after the baseline.
"""

import json
from pathlib import Path

import pytest

from nccn_monitor.scraper import GuidelineInfo, PdfIndexEntry
from nccn_monitor.state import StateManager
from nccn_monitor.weekly import check_and_download

FIXTURES = Path(__file__).parent / "fixtures"


def _guidelines(version: str) -> list[GuidelineInfo]:
    return [
        GuidelineInfo(
            name="Gastric Cancer",
            version=version,
            detail_url="https://www.nccn.org/guidelines/guidelines-detail?category=1&id=1003",
            category="Cancer by Type",
        )
    ]


def _install(monkeypatch, version: str, calls: list):
    async def fake_fetch():
        return _guidelines(version)

    async def fake_index(guidelines, index_file="~/.nccn-monitor/index.yaml"):
        return [
            PdfIndexEntry(
                name="Gastric Cancer",
                slug="gastric-cancer",
                pdf_url="https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf",
                version=version,
                detail_url=_guidelines(version)[0].detail_url,
                category="Cancer by Type",
            )
        ]

    async def fake_download(self, **kwargs):
        calls.append(kwargs)
        return Path(kwargs["archive_dir"]) / "downloaded.pdf"

    monkeypatch.setattr("nccn_monitor.weekly.fetch_all_guidelines", fake_fetch)
    monkeypatch.setattr("nccn_monitor.weekly.fetch_pdf_index", fake_index)
    monkeypatch.setattr(
        "nccn_monitor.weekly.NCCNDownloader.download_and_archive",
        fake_download,
    )


async def test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state_path = tmp_path / "state.json"
    archive = tmp_path / "archive"
    state_path.write_text(json.dumps({
        "last_check": "2026-11-11T00:00:00+00:00",
        "initialized": True,
        "guidelines": {
            "Gastric Cancer": {
                "version": "2.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-11-11T00:00:00+00:00",
            }
        },
    }))
    calls: list[dict] = []
    _install(monkeypatch, "2.2026", calls)
    loaded = StateManager(state_path)
    assert loaded.detect_changes(_guidelines("2.2026"), ["Gastric Cancer"]) == []

    code = await check_and_download(
        {
            "state_file": str(state_path),
            "archive_dir": str(archive),
            "index_file": str(tmp_path / "index.yaml"),
            "watch_list": ["Gastric Cancer"],
            "nccn": {"username": "fixture-user", "password": "fixture-password"},
        },
        dry_run=False,
    )

    assert code == 1
    assert len(calls) == 1
    assert calls[0]["version"] == "2.2026"
    assert calls[0]["name"] == "Gastric Cancer"
    assert calls[0]["slug"] == "gastric-cancer"


async def test_first_baseline_returns_zero_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[dict] = []
    _install(monkeypatch, "2.2026", calls)
    code = await check_and_download(
        {
            "state_file": str(tmp_path / "state.json"),
            "archive_dir": str(tmp_path / "archive"),
            "index_file": str(tmp_path / "index.yaml"),
            "watch_list": ["Gastric Cancer"],
            "nccn": {"username": "fixture-user", "password": "fixture-password"},
        }
    )
    assert code == 0
    assert calls == []
    stored = StateManager(tmp_path / "state.json")
    assert stored.initialized is True
    assert stored.known_guidelines["Gastric Cancer"]["version"] == "2.2026"


async def test_dry_run_with_version_change_does_not_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state_path = tmp_path / "state.json"
    StateManager(state_path).detect_changes(_guidelines("1.2026"), ["Gastric Cancer"])
    calls: list[dict] = []
    _install(monkeypatch, "2.2026", calls)
    code = await check_and_download(
        {
            "state_file": str(state_path),
            "archive_dir": str(tmp_path / "archive"),
            "index_file": str(tmp_path / "index.yaml"),
            "watch_list": ["Gastric Cancer"],
            "nccn": {"username": "fixture-user", "password": "fixture-password"},
        },
        dry_run=True,
    )
    assert code == 0
    assert calls == []


async def test_blocked_existing_pdf_is_not_replaced_and_exits_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state_path = tmp_path / "state.json"
    archive = tmp_path / "archive"
    state_path.write_text(json.dumps({
        "last_check": "2026-11-11T00:00:00+00:00",
        "initialized": True,
        "guidelines": {
            "Gastric Cancer": {
                "version": "2.2026",
                "first_seen": "2026-03-01T00:00:00+00:00",
                "last_updated": "2026-11-11T00:00:00+00:00",
            }
        },
    }))
    target = archive / "gastric-cancer" / "v2.2026"
    target.mkdir(parents=True)
    occupied = target / "NCCN_GastricCancer_2026.V2_EN.pdf"
    occupied.write_bytes((FIXTURES / "pdf/professional_breast_v2_2026.pdf").read_bytes())
    original = occupied.read_bytes()
    calls: list[dict] = []
    _install(monkeypatch, "2.2026", calls)

    code = await check_and_download(
        {
            "state_file": str(state_path),
            "archive_dir": str(archive),
            "index_file": str(tmp_path / "index.yaml"),
            "watch_list": ["Gastric Cancer"],
            "nccn": {"username": "fixture-user", "password": "fixture-password"},
        }
    )

    assert code == 2
    assert calls == []
    assert occupied.read_bytes() == original


async def test_scrape_failure_returns_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def boom():
        raise RuntimeError("fixture scrape failure")

    monkeypatch.setattr("nccn_monitor.weekly.fetch_all_guidelines", boom)
    code = await check_and_download({"state_file": str(tmp_path / "state.json")})
    assert code == 2


def test_shim_preserves_redacted_paths_and_original_hash():
    shim = Path(__file__).resolve().parents[1] / "scripts" / "nccn_weekly_check.py"
    text = shim.read_text()
    assert "bd134c5fd9ba2b76a86abd7128ec83e6f4178112346d58e2e89dc737671a0801" in text
    assert "/Users/[REDACTED]/Workspace/devs/nccn_watcher/src" in text
    assert "/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml" in text
    assert "verify=False" not in text


def test_candidate_keeps_tls_verification_enabled():
    root = Path(__file__).resolve().parents[1] / "src" / "nccn_monitor"
    for name in ("downloader.py", "scraper.py", "weekly.py"):
        text = (root / name).read_text()
        assert "verify=False" not in text
        assert "verify = False" not in text
