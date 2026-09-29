from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.usage_model import ResetDeadlines, Usage, Window, seconds_until
from src.widget import Monitor


def usage(primary_reset, secondary_reset=None):
    return Usage(
        allowed=True,
        primary=Window(10, 300, primary_reset),
        secondary=Window(20, 10080, secondary_reset) if secondary_reset else None,
        plan="plus",
        reached_type=None,
        reset_credits=0,
    )


def test_fixed_resets_at_makes_countdown_decrease_with_controlled_clock():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    deadline = now + timedelta(hours=5)

    assert seconds_until(deadline, now) == 18_000
    assert seconds_until(deadline, now + timedelta(seconds=61)) == 17_939


def test_newer_and_earlier_snapshots_replace_deadline_without_minimum():
    base = 2_000_000_000
    deadlines = ResetDeadlines()
    deadlines.replace(usage(base))
    assert int(deadlines.primary.timestamp()) == base

    deadlines.replace(usage(base + 900))
    assert int(deadlines.primary.timestamp()) == base + 900

    deadlines.replace(usage(base - 1200))
    assert int(deadlines.primary.timestamp()) == base - 1200


def test_primary_and_secondary_deadlines_are_independent():
    deadlines = ResetDeadlines()
    deadlines.replace(usage(2_000_000_000, 2_000_500_000))

    assert int(deadlines.primary.timestamp()) == 2_000_000_000
    assert int(deadlines.secondary.timestamp()) == 2_000_500_000

    deadlines.replace(usage(2_000_000_100, 2_000_400_000))
    assert int(deadlines.primary.timestamp()) == 2_000_000_100
    assert int(deadlines.secondary.timestamp()) == 2_000_400_000


def test_deadlines_are_not_persisted_and_obsolete_config_keys_are_removed(tmp_path):
    class Dummy:
        anchor = "free"
        compact = True
        topmost = False
        cfg = {
            "stable_reset_primary": 123,
            "stable_reset_secondary": 456,
            "unrelated_preference": "kept",
        }
        cfg_path = tmp_path / "settings.json"

        @staticmethod
        def x():
            return 10

        @staticmethod
        def y():
            return 20

    Monitor.save_cfg(Dummy())
    saved = json.loads(Dummy.cfg_path.read_text(encoding="utf-8"))

    assert "stable_reset_primary" not in saved
    assert "stable_reset_secondary" not in saved
    assert saved["unrelated_preference"] == "kept"
    assert ResetDeadlines() == ResetDeadlines(primary=None, secondary=None)
