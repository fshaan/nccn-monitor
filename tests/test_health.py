"""Tests for the health check module."""

from pathlib import Path

from nccn_watcher.health import HealthTracker


def test_starts_healthy(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json")
    assert ht.is_healthy


def test_stays_healthy_on_success(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json")
    ht.record_success()
    assert ht.is_healthy


def test_single_failure_no_alert(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json", failure_threshold=3)
    should_alert = ht.record_failure("Connection timeout")
    assert not should_alert
    assert not ht.is_healthy


def test_threshold_triggers_alert(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json", failure_threshold=3)
    ht.record_failure("Error 1")
    ht.record_failure("Error 2")
    should_alert = ht.record_failure("Error 3")
    assert should_alert


def test_alert_only_fires_once(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json", failure_threshold=2)
    ht.record_failure("Error 1")
    assert ht.record_failure("Error 2") is True  # First alert
    assert ht.record_failure("Error 3") is False  # No re-alert


def test_success_resets_failure_counter(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json", failure_threshold=3)
    ht.record_failure("Error 1")
    ht.record_failure("Error 2")
    ht.record_success()
    assert ht.is_healthy
    # After reset, need 3 more failures to alert
    assert not ht.record_failure("Error A")
    assert not ht.record_failure("Error B")
    assert ht.record_failure("Error C")


def test_status_summary_healthy(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json")
    ht.record_success()
    assert "Healthy" in ht.status_summary


def test_status_summary_unhealthy(tmp_path: Path):
    ht = HealthTracker(tmp_path / "health.json")
    ht.record_failure("Bad HTML")
    assert "UNHEALTHY" in ht.status_summary
    assert "Bad HTML" in ht.status_summary
