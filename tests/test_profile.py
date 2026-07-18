"""Tests for the congregation profile loader."""

from __future__ import annotations

import pytest

from bulletin_maker.core.profile import BUNDLED_PROFILE, load_profile
from bulletin_maker.exceptions import BulletinError


class TestBundledProfile:

    def test_bundled_profile_exists_and_loads(self):
        profile = load_profile(BUNDLED_PROFILE)
        assert profile.church_name == "Ascension Lutheran Church"
        assert profile.service_time == "10:00 AM"
        assert "601.956.4263" in profile.church_address
        assert profile.liturgical_setting == "setting_two"
        assert profile.paper_size == "legal_booklet"

    def test_address_joins_lines(self):
        profile = load_profile(BUNDLED_PROFILE)
        assert profile.church_address.count("\n") == len(profile.address_lines) - 1

    def test_copyright_paragraphs_present(self):
        profile = load_profile(BUNDLED_PROFILE)
        assert len(profile.copyright_paragraphs) == 2
        assert "Augsburg Fortress" in profile.copyright_paragraphs[0]

    def test_standing_instructions_keep_line_break(self):
        profile = load_profile(BUNDLED_PROFILE)
        assert "\n" in profile.standing_instructions


class TestLoadProfileErrors:

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(BulletinError, match="not found"):
            load_profile(tmp_path / "nope.toml")

    def test_invalid_toml_raises(self, tmp_path):
        bad = tmp_path / "bad.toml"
        bad.write_text("this is not = valid [ toml")
        with pytest.raises(BulletinError, match="Invalid congregation profile"):
            load_profile(bad)

    def test_missing_required_field_raises(self, tmp_path):
        partial = tmp_path / "partial.toml"
        partial.write_text('[church]\nname = "St. Test"\n')
        with pytest.raises(BulletinError, match="missing"):
            load_profile(partial)


class TestCustomProfile:

    def test_another_congregation_loads(self, tmp_path):
        other = tmp_path / "other.toml"
        other.write_text(
            '[church]\n'
            'name = "St. Mark Lutheran Church"\n'
            'address_lines = ["1 Main St", "555.123.4567"]\n'
            'service_time = "9:30 AM"\n'
            '[texts]\n'
            'welcome_message = "Welcome to St. Mark."\n'
            'standing_instructions = "* means stand."\n'
        )
        profile = load_profile(other)
        assert profile.church_name == "St. Mark Lutheran Church"
        assert profile.service_time == "9:30 AM"
        assert profile.copyright_paragraphs == ()
        assert profile.liturgical_setting == "setting_two"
