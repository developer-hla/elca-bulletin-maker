"""Tests for the core domain layer — naming and document orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bulletin_maker.core.documents import (
    DEFAULT_SELECTION,
    DOCUMENTS,
    document_label,
    generate_documents,
)
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.naming import build_date_suffix, build_filename, extract_day_name
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.sns.models import DayContent


SUNDAY_TITLE = "Sunday, July 19, 2026 Lectionary 16, Year A"


def _day() -> DayContent:
    return DayContent(
        date="2026-7-19", title=SUNDAY_TITLE, introduction="",
        confession_html="", prayer_of_the_day_html="", gospel_acclamation="",
        prayers_html="<p>x</p>",
    )


def _config(**kwargs) -> ServiceConfig:
    return ServiceConfig(date="2026-07-19", date_display="July 19, 2026", **kwargs)


class TestNaming:

    def test_extract_day_name(self):
        assert extract_day_name(SUNDAY_TITLE) == "Lectionary 16"

    def test_extract_day_name_without_date_prefix(self):
        assert extract_day_name("First Sunday in Lent, Year A") == "First Sunday in Lent"

    def test_date_suffix_for_sunday(self):
        suffix = build_date_suffix("2026-07-19", SUNDAY_TITLE)
        assert suffix == "2026.07.19 - Lectionary 16 Year A"

    def test_date_suffix_prepends_weekday_for_non_sunday(self):
        title = "Wednesday, February 18, 2026 Ash Wednesday"
        suffix = build_date_suffix("2026-02-18", title)
        assert suffix.startswith("2026.02.18 - Wednesday - ")

    def test_build_filename(self):
        name = build_filename("Leader Guide", "2026-07-19", SUNDAY_TITLE)
        assert name == "Leader Guide - 2026.07.19 - Lectionary 16 Year A.pdf"


class TestRegistry:

    def test_five_documents_registered(self):
        assert len(DOCUMENTS) == 5
        assert DEFAULT_SELECTION == (
            "bulletin", "prayers", "scripture", "large_print", "leader_guide",
        )

    def test_prayers_label_embeds_creed(self):
        assert document_label("prayers") == "Pulpit PRAYERS + APOSTLES"
        assert document_label("prayers", creed_type="nicene") == "Pulpit PRAYERS + NICENE"

    def test_other_labels_ignore_creed(self):
        assert document_label("bulletin", creed_type="nicene") == "Bulletin for Congregation"


class TestGenerateDocuments:

    def _run(self, tmp_path, selected=None):
        with patch("bulletin_maker.core.documents.generate_bulletin") as m_bull, \
             patch("bulletin_maker.core.documents.generate_pulpit_prayers") as m_pray, \
             patch("bulletin_maker.core.documents.generate_pulpit_scripture") as m_scrip, \
             patch("bulletin_maker.core.documents.generate_large_print") as m_lp, \
             patch("bulletin_maker.core.documents.generate_leader_guide") as m_lg:
            m_bull.return_value = (tmp_path / "b.pdf", 7)
            m_pray.return_value = tmp_path / "p.pdf"
            m_scrip.return_value = tmp_path / "s.pdf"
            m_lp.return_value = tmp_path / "l.pdf"
            m_lg.return_value = tmp_path / "g.pdf"
            outcome = generate_documents(
                _day(), _config(), tmp_path,
                season=LiturgicalSeason.PENTECOST.value, selected=selected,
            )
            return outcome, {
                "bulletin": m_bull, "prayers": m_pray, "scripture": m_scrip,
                "large_print": m_lp, "leader_guide": m_lg,
            }

    def test_all_five_generate_by_default(self, tmp_path):
        outcome, mocks = self._run(tmp_path)
        assert outcome.success
        assert set(outcome.results) == set(DEFAULT_SELECTION)
        for mock in mocks.values():
            assert mock.call_count == 1

    def test_creed_page_flows_from_bulletin_to_prayers(self, tmp_path):
        outcome, mocks = self._run(tmp_path)
        assert outcome.creed_page == 7
        assert mocks["prayers"].call_args.kwargs["creed_page_num"] == 7

    def test_selection_limits_generation(self, tmp_path):
        outcome, mocks = self._run(tmp_path, selected={"scripture"})
        assert set(outcome.results) == {"scripture"}
        assert mocks["bulletin"].call_count == 0

    def test_unknown_key_raises(self, tmp_path):
        with pytest.raises(ValueError):
            generate_documents(
                _day(), _config(), tmp_path,
                season=LiturgicalSeason.PENTECOST.value, selected={"newsletter"},
            )

    def test_one_failure_does_not_stop_others(self, tmp_path):
        with patch("bulletin_maker.core.documents.generate_bulletin",
                   side_effect=RuntimeError("chromium died")), \
             patch("bulletin_maker.core.documents.generate_pulpit_prayers") as m_pray, \
             patch("bulletin_maker.core.documents.generate_pulpit_scripture") as m_scrip, \
             patch("bulletin_maker.core.documents.generate_large_print") as m_lp, \
             patch("bulletin_maker.core.documents.generate_leader_guide") as m_lg:
            for m in (m_pray, m_scrip, m_lp, m_lg):
                m.return_value = tmp_path / "x.pdf"
            outcome = generate_documents(
                _day(), _config(), tmp_path, season=LiturgicalSeason.PENTECOST.value,
            )
        assert not outcome.success
        assert "chromium died" in outcome.errors["bulletin"]
        assert set(outcome.results) == {"prayers", "scripture", "large_print", "leader_guide"}

    def test_progress_reports_each_document(self, tmp_path):
        calls = []
        with patch("bulletin_maker.core.documents.generate_pulpit_scripture") as m_scrip:
            m_scrip.return_value = tmp_path / "s.pdf"
            generate_documents(
                _day(), _config(), tmp_path,
                season=LiturgicalSeason.PENTECOST.value, selected={"scripture"},
                on_progress=lambda key, detail, pct: calls.append((key, detail, pct)),
            )
        keys = [c[0] for c in calls]
        assert "scripture" in keys
        assert calls[-1] == ("done", "Generation complete!", 100)

    def test_filenames_use_registry_labels(self, tmp_path):
        outcome, mocks = self._run(tmp_path, selected={"large_print"})
        out_path = mocks["large_print"].call_args.kwargs["output_path"]
        assert Path(out_path).name == (
            "Full with Hymns LARGE PRINT - 2026.07.19 - Lectionary 16 Year A.pdf"
        )
