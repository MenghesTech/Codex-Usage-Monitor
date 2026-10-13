from __future__ import annotations

import json

import pytest

from src.settings import load_settings, save_settings
from src.usage_alerts import Alert, UsageAlertEngine
from src.usage_model import Usage, Window


NOW = 2_000_000_000
FIVE_HOURS = NOW + 300 * 60
SEVEN_DAYS = NOW + 10080 * 60


def usage(primary=79, secondary=79, primary_reset=FIVE_HOURS,
          secondary_reset=SEVEN_DAYS, primary_duration=300):
    return Usage(
        True,
        Window(primary, primary_duration, primary_reset) if primary is not None else None,
        Window(secondary, 10080, secondary_reset) if secondary is not None else None,
        "plus", None, 0,
    )


def test_defaults_are_off_and_exact_crossings_fire_once():
    engine = UsageAlertEngine()
    engine.process(usage(), now=NOW)
    assert engine.process(usage(80), now=NOW) == []
    engine.set_enabled("primary", 80, True)
    assert engine.process(usage(80), now=NOW) == []
    engine.process(usage(79), now=NOW)
    assert engine.process(usage(80), now=NOW) == []  # enabled above threshold

    fresh = UsageAlertEngine()
    fresh.set_enabled("primary", 80, True)
    fresh.process(usage(79), now=NOW)
    assert fresh.process(usage(80), now=NOW) == [Alert("primary", 80, 80)]
    assert fresh.process(usage(80), now=NOW) == []
    fresh.process(usage(79), now=NOW)
    assert fresh.process(usage(80), now=NOW) == []


def test_jump_and_simultaneous_windows_are_one_batch():
    engine = UsageAlertEngine()
    for window in ("primary", "secondary"):
        for threshold in (80, 90, 95):
            engine.set_enabled(window, threshold, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(96, 96), now=NOW) == [
        Alert(window, threshold, 96)
        for window in ("primary", "secondary")
        for threshold in (80, 90, 95)
    ]


def test_restart_same_cycle_and_new_reset_cycle():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(80), now=NOW) == [Alert("primary", 80, 80)]
    restarted = UsageAlertEngine(engine.to_settings())
    assert restarted.process(usage(80), now=NOW + 1) == []
    assert restarted.process(usage(79), now=NOW + 2) == []
    assert restarted.process(usage(80), now=NOW + 3) == []
    next_deadline = FIVE_HOURS + 300 * 60
    assert restarted.process(usage(5, primary_reset=next_deadline), now=FIVE_HOURS + 1) == []
    assert restarted.process(usage(80, primary_reset=next_deadline), now=FIVE_HOURS + 2) == [
        Alert("primary", 80, 80)
    ]


def test_deadline_corrections_and_small_usage_corrections_keep_dedup():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(81), now=NOW) == [Alert("primary", 80, 81)]
    assert engine.process(usage(79, primary_reset=FIVE_HOURS + 300), now=NOW) == []
    assert engine.process(usage(81, primary_reset=FIVE_HOURS - 300), now=NOW) == []


def test_late_deadline_correction_after_expiry_is_not_a_new_cycle():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    old_deadline = NOW + 100
    corrected_deadline = old_deadline + 60
    engine.process(usage(79, primary_reset=old_deadline), now=NOW)
    assert engine.process(usage(80, primary_reset=old_deadline), now=NOW + 1) == [
        Alert("primary", 80, 80)
    ]
    assert engine.process(usage(79, primary_reset=corrected_deadline),
                          now=old_deadline + 1) == []
    assert engine.process(usage(80, primary_reset=corrected_deadline),
                          now=old_deadline + 2) == []
    assert engine.process(usage(80, primary_reset=corrected_deadline),
                          now=old_deadline + 3) == []


def test_real_reset_after_deadline_rearms_even_with_pending_old_cycle_alert():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(79), now=NOW)
    assert engine.process(usage(80), now=NOW + 1) == [Alert("primary", 80, 80)]
    new_deadline = FIVE_HOURS + 300 * 60
    assert engine.process(usage(5, primary_reset=new_deadline),
                          now=FIVE_HOURS + 1) == []
    assert engine.process(usage(80, primary_reset=new_deadline),
                          now=FIVE_HOURS + 2) == [Alert("primary", 80, 80)]
    assert [item.cycle for item in engine.queued_alerts()] == [
        FIVE_HOURS, new_deadline,
    ]


def test_disabling_threshold_cancels_queued_notice():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(79), now=NOW)
    engine.process(usage(80), now=NOW + 1)
    assert len(engine.queued_alerts()) == 1
    engine.set_enabled("primary", 80, False)
    assert engine.queued_alerts() == []
    assert UsageAlertEngine(engine.to_settings()).queued_alerts() == []


def test_corrupt_outbox_entries_cannot_enable_or_forge_alerts():
    settings = {
        "enabled": {"primary": [80]},
        "queued": [
            {"window": ["primary"], "threshold": 80, "used": 80, "cycle": FIVE_HOURS},
            {"window": "secondary", "threshold": 80, "used": 80, "cycle": SEVEN_DAYS},
            {"window": "primary", "threshold": 80, "used": 79, "cycle": FIVE_HOURS},
            {"window": "primary", "threshold": 80, "used": 80, "cycle": FIVE_HOURS},
        ],
    }
    queued = UsageAlertEngine(settings).queued_alerts()
    assert [(item.window, item.threshold, item.used, item.cycle) for item in queued] == [
        ("primary", 80, 80, FIVE_HOURS),
    ]


def test_missing_and_stale_data_preserve_last_complete_sample():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(primary=None), now=NOW) == []
    incomplete = usage()
    incomplete.primary.used = None
    assert engine.process(incomplete, now=NOW) == []
    assert engine.process(usage(primary_reset=None), now=NOW) == []
    assert engine.process(usage(primary=80, primary_duration=None), now=NOW) == []
    assert engine.process(usage(primary_reset=NOW), now=NOW) == []
    assert engine.process(usage(80), now=NOW) == [Alert("primary", 80, 80)]


def test_one_incomplete_window_does_not_block_the_other():
    engine = UsageAlertEngine()
    engine.set_enabled("secondary", 80, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(primary=None, secondary=80), now=NOW) == [
        Alert("secondary", 80, 80)
    ]


def test_activation_above_threshold_and_disable_reenable():
    engine = UsageAlertEngine()
    engine.process(usage(91), now=NOW)
    engine.set_enabled("primary", 80, True)
    engine.set_enabled("primary", 90, True)
    assert engine.process(usage(96), now=NOW) == []
    engine.set_enabled("primary", 95, True)
    engine.set_enabled("primary", 95, False)
    engine.process(usage(94), now=NOW)
    assert engine.process(usage(96), now=NOW) == []
    engine.set_enabled("primary", 95, True)
    assert engine.process(usage(96), now=NOW) == []


def test_activation_before_first_fresh_read_is_not_retroactive_after_restart():
    original = UsageAlertEngine()
    original.process(usage(79), now=NOW)
    restarted = UsageAlertEngine(original.to_settings())
    restarted.set_enabled("primary", 80, True)
    pending = UsageAlertEngine(restarted.to_settings())
    assert pending.process(usage(96), now=NOW + 1) == []
    assert pending.process(usage(97), now=NOW + 2) == []
    assert pending.to_settings()["pending"]["primary"] == []

    another = UsageAlertEngine(original.to_settings())
    another.set_enabled("primary", 80, True)
    assert another.process(usage(79), now=NOW + 1) == []
    assert another.process(usage(80), now=NOW + 2) == [Alert("primary", 80, 80)]


def test_reconnect_does_not_repeat_alert():
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(), now=NOW)
    assert engine.process(usage(80), now=NOW) == [Alert("primary", 80, 80)]
    engine.process(usage(primary=None), now=NOW)
    assert engine.process(usage(85), now=NOW) == []


def test_persistence_and_corrupt_alert_config(tmp_path):
    path = tmp_path / "settings.json"
    engine = UsageAlertEngine()
    engine.set_enabled("primary", 80, True)
    engine.process(usage(), now=NOW)
    engine.process(usage(80), now=NOW)
    save_settings({"compact": True, "usage_alerts": engine.to_settings()}, path)
    loaded = load_settings(path, tmp_path / "missing")
    assert loaded["compact"] is True
    assert UsageAlertEngine(loaded["usage_alerts"]).process(usage(81), now=NOW) == []

    path.write_text(json.dumps({"compact": True, "usage_alerts": {
        "enabled": {"primary": [80, "90", 95]},
        "state": {"primary": {"used": "80", "resets_at": FIVE_HOURS,
                              "notified": [80]}},
    }}), encoding="utf-8")
    corrupt = load_settings(path, tmp_path / "missing")
    assert corrupt["compact"] is True
    assert corrupt["usage_alerts"]["thresholds"]["primary"] == []
    assert corrupt["usage_alerts"]["active"] is False
    assert corrupt["usage_alerts"]["state"] == {}
    path.write_bytes(b"{bad json")
    assert load_settings(path, tmp_path / "missing") == {}


@pytest.mark.parametrize("threshold", [80, 90, 95])
def test_each_threshold_has_exact_boundary(threshold):
    engine = UsageAlertEngine()
    engine.set_enabled("secondary", threshold, True)
    engine.process(usage(secondary=threshold - 1), now=NOW)
    assert engine.process(usage(secondary=threshold), now=NOW) == [
        Alert("secondary", threshold, threshold)
    ]


def test_custom_levels_minimum_maximum_empty_and_sorted():
    engine = UsageAlertEngine()
    engine.configure(True, {"primary": [100, 1, 47], "secondary": []})
    assert engine.thresholds("primary") == [1, 47, 100]
    assert engine.thresholds("secondary") == []
    engine.process(usage(0, 0), now=NOW)
    assert engine.process(usage(1, 0), now=NOW) == [Alert("primary", 1, 1)]
    assert engine.process(usage(100, 0), now=NOW) == [
        Alert("primary", 47, 100), Alert("primary", 100, 100),
    ]


@pytest.mark.parametrize("levels", [[0], [101], [1, 1], [1, 2, 3, 4],
                                    [True], ["50"], [-1]])
def test_invalid_custom_levels_are_rejected_without_mutation(levels):
    engine = UsageAlertEngine()
    before = engine.to_settings()
    with pytest.raises(ValueError):
        engine.configure(True, {"primary": levels, "secondary": []})
    assert engine.to_settings() == before


def test_global_disable_preserves_levels_and_reenable_is_not_retroactive():
    engine = UsageAlertEngine()
    levels = {"primary": [23, 61], "secondary": []}
    engine.configure(True, levels)
    engine.process(usage(20), now=NOW)
    assert engine.process(usage(23), now=NOW) == [Alert("primary", 23, 23)]
    engine.configure(False, levels)
    assert engine.thresholds("primary") == [23, 61]
    assert engine.process(usage(70), now=NOW) == []
    engine.configure(True, levels)
    assert engine.process(usage(71), now=NOW) == []
    assert engine.to_settings()["state"]["primary"]["notified"] == [23, 61]


def test_change_levels_mid_cycle_keeps_dedup_and_no_retroactive_alert():
    engine = UsageAlertEngine()
    engine.configure(True, {"primary": [37], "secondary": []})
    engine.process(usage(30), now=NOW)
    assert engine.process(usage(40), now=NOW) == [Alert("primary", 37, 40)]
    engine.configure(True, {"primary": [37, 39, 55], "secondary": []})
    assert engine.process(usage(56), now=NOW) == [Alert("primary", 55, 56)]
    restarted = UsageAlertEngine(engine.to_settings())
    assert restarted.process(usage(56), now=NOW) == []
    restarted.configure(True, {"primary": [37, 55], "secondary": []})
    restarted.configure(True, {"primary": [37, 39, 55], "secondary": []})
    assert restarted.process(usage(60), now=NOW) == []


def test_custom_levels_group_two_windows_and_rearm_on_real_reset():
    engine = UsageAlertEngine()
    engine.configure(True, {"primary": [22, 44, 66], "secondary": [15, 45]})
    engine.process(usage(10, 10), now=NOW)
    assert engine.process(usage(70, 50), now=NOW) == [
        Alert("primary", 22, 70), Alert("primary", 44, 70),
        Alert("primary", 66, 70), Alert("secondary", 15, 50),
        Alert("secondary", 45, 50),
    ]
    next_primary = FIVE_HOURS + 300 * 60
    next_secondary = SEVEN_DAYS + 10080 * 60
    engine.process(usage(5, 5, primary_reset=next_primary,
                         secondary_reset=next_secondary), now=FIVE_HOURS + 1)
    assert engine.process(usage(22, 15, primary_reset=next_primary,
                                secondary_reset=next_secondary), now=FIVE_HOURS + 2) == [
        Alert("primary", 22, 22), Alert("secondary", 15, 15),
    ]


def test_migrate_legacy_fixed_levels_without_losing_notified_or_preferences(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"compact": True, "anchor": "tl", "usage_alerts": {
        "enabled": {"primary": [95, 80], "secondary": [90]},
        "state": {"primary": {"used": 81, "resets_at": FIVE_HOURS,
                              "notified": [80]}},
    }}), encoding="utf-8")
    loaded = load_settings(path, tmp_path / "missing")
    assert loaded["compact"] is True
    assert loaded["anchor"] == "tl"
    migrated = loaded["usage_alerts"]
    assert migrated["active"] is True
    assert migrated["thresholds"] == {"primary": [80, 95], "secondary": [90]}
    engine = UsageAlertEngine(migrated)
    assert engine.process(usage(81), now=NOW) == []
    assert engine.process(usage(96), now=NOW) == [Alert("primary", 95, 96)]


def test_corrupt_custom_configuration_falls_back_without_losing_other_preferences(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"compact": True, "topmost": False,
                                "usage_alerts": {"active": True,
                                                 "thresholds": {
                                                     "primary": [20, 20],
                                                     "secondary": [42, "50"]}}}),
                    encoding="utf-8")
    loaded = load_settings(path, tmp_path / "missing")
    assert loaded["compact"] is True
    assert loaded["topmost"] is False
    assert loaded["usage_alerts"]["thresholds"] == {
        "primary": [], "secondary": [],
    }
    assert UsageAlertEngine(loaded["usage_alerts"]).process(usage(100, 100),
                                                              now=NOW) == []
