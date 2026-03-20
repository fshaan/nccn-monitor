"""Tests for the state management module."""

import json
from pathlib import Path

from nccn_monitor.scraper import GuidelineInfo
from nccn_monitor.state import StateManager


def make_guidelines(*items: tuple[str, str]) -> list[GuidelineInfo]:
    return [
        GuidelineInfo(name=name, version=ver, detail_url=f"https://nccn.org/detail/{name}")
        for name, ver in items
    ]


def test_first_run_returns_no_changes(tmp_path: Path):
    """First run establishes baseline — should NOT report any changes."""
    mgr = StateManager(tmp_path / "state.json")
    guidelines = make_guidelines(("Breast Cancer", "2.2026"), ("Lung Cancer", "5.2026"))

    changes = mgr.detect_changes(guidelines)

    assert changes == []
    assert mgr._data["initialized"] is True
    assert len(mgr.known_guidelines) == 2


def test_detects_version_change(tmp_path: Path):
    mgr = StateManager(tmp_path / "state.json")

    # First run: establish baseline
    v1 = make_guidelines(("Breast Cancer", "2.2026"), ("Lung Cancer", "5.2026"))
    mgr.detect_changes(v1)

    # Second run: Breast Cancer updated
    v2 = make_guidelines(("Breast Cancer", "3.2026"), ("Lung Cancer", "5.2026"))
    changes = mgr.detect_changes(v2)

    assert len(changes) == 1
    assert changes[0].name == "Breast Cancer"
    assert changes[0].old_version == "2.2026"
    assert changes[0].new_version == "3.2026"


def test_no_changes_returns_empty(tmp_path: Path):
    mgr = StateManager(tmp_path / "state.json")

    guidelines = make_guidelines(("Breast Cancer", "2.2026"))
    mgr.detect_changes(guidelines)  # baseline
    changes = mgr.detect_changes(guidelines)  # same versions

    assert changes == []


def test_watch_list_filters_results(tmp_path: Path):
    mgr = StateManager(tmp_path / "state.json")

    v1 = make_guidelines(("Breast Cancer", "2.2026"), ("Lung Cancer", "5.2026"))
    mgr.detect_changes(v1, watch_list=["Breast Cancer"])

    # Both updated, but only Breast Cancer is in watch list
    v2 = make_guidelines(("Breast Cancer", "3.2026"), ("Lung Cancer", "6.2026"))
    changes = mgr.detect_changes(v2, watch_list=["Breast Cancer"])

    assert len(changes) == 1
    assert changes[0].name == "Breast Cancer"


def test_watch_list_case_insensitive(tmp_path: Path):
    mgr = StateManager(tmp_path / "state.json")

    v1 = make_guidelines(("Breast Cancer", "2.2026"))
    mgr.detect_changes(v1, watch_list=["breast cancer"])

    v2 = make_guidelines(("Breast Cancer", "3.2026"))
    changes = mgr.detect_changes(v2, watch_list=["breast cancer"])

    assert len(changes) == 1


def test_new_guideline_added_later(tmp_path: Path):
    mgr = StateManager(tmp_path / "state.json")

    v1 = make_guidelines(("Breast Cancer", "2.2026"))
    mgr.detect_changes(v1)

    # New guideline appears — should NOT be reported as a change
    v2 = make_guidelines(("Breast Cancer", "2.2026"), ("Gastric Cancer", "1.2026"))
    changes = mgr.detect_changes(v2)

    assert changes == []
    assert "Gastric Cancer" in mgr.known_guidelines


def test_state_persists_to_disk(tmp_path: Path):
    state_file = tmp_path / "state.json"
    mgr1 = StateManager(state_file)
    mgr1.detect_changes(make_guidelines(("Breast Cancer", "2.2026")))

    # Load from disk in a new instance
    mgr2 = StateManager(state_file)
    assert mgr2._data["initialized"] is True
    assert "Breast Cancer" in mgr2.known_guidelines
