"""Loud rebaseline summary for the parity harness.

When ``BULLETIN_PARITY_REBASELINE=1`` is set, ``test_parity.py`` records
one line per (variant, document) it rewrites into
``config.stash[REBASELINE_CHANGES_KEY]``; this conftest prints all of
them in a hard-to-miss block at the end of the run regardless of
``-s``/``-r`` flags.
"""

from __future__ import annotations

import pytest

REBASELINE_CHANGES_KEY = pytest.StashKey[list]()


def pytest_configure(config: pytest.Config) -> None:
    config.stash[REBASELINE_CHANGES_KEY] = []


def pytest_terminal_summary(
    terminalreporter: object, exitstatus: int, config: pytest.Config,
) -> None:
    changes = config.stash.get(REBASELINE_CHANGES_KEY, [])
    if not changes:
        return
    terminalreporter.write_sep("=", "PARITY REBASELINE SUMMARY", red=True, bold=True)
    for line in changes:
        terminalreporter.write_line(line)
    terminalreporter.write_line("")
    terminalreporter.write_line(
        "Golden files were regenerated. This requires OWNER APPROVAL "
        "before merging — see tests/parity/README.md."
    )
    terminalreporter.write_sep("=", red=True, bold=True)
