"""Tests for past-run storage (core.past_runs)."""

from __future__ import annotations

import pytest

from bulletin_maker.core import past_runs


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(past_runs, "_path", lambda: tmp_path / "past_runs.json")


class TestPastRunStorage:

    def test_save_and_retrieve(self):
        run_id = past_runs.save_past_run(
            {"date": "2026-03-01", "creed_type": "nicene"},
            {"season": "lent"},
        )
        runs = past_runs.list_past_runs()
        assert runs[0]["id"] == run_id
        assert past_runs.get_past_run(run_id)["form_data"]["creed_type"] == "nicene"

    def test_deduplicates_by_date(self):
        past_runs.save_past_run({"date": "2026-03-01", "v": 1}, {})
        past_runs.save_past_run({"date": "2026-03-01", "v": 2}, {})
        runs = past_runs.read_past_runs()
        assert len(runs) == 1
        assert runs[0]["form_data"]["v"] == 2

    def test_caps_at_max(self):
        for i in range(past_runs.MAX_PAST_RUNS + 5):
            past_runs.save_past_run({"date": f"2026-01-{i + 1:02d}"}, {})
        assert len(past_runs.read_past_runs()) == past_runs.MAX_PAST_RUNS

    def test_delete(self):
        run_id = past_runs.save_past_run({"date": "2026-03-01"}, {})
        assert past_runs.delete_past_run(run_id) is True
        assert past_runs.delete_past_run(run_id) is False

    def test_corrupted_file_returns_empty(self):
        past_runs._path().write_text("not json")
        assert past_runs.read_past_runs() == []

    def test_corrupted_file_recovers_on_save(self):
        past_runs._path().write_text("{}")
        past_runs.save_past_run({"date": "2026-03-01"}, {})
        assert len(past_runs.read_past_runs()) == 1
