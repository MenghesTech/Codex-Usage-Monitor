"""Local usage threshold detection, independent of the Qt interface."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .usage_model import Usage, Window


LEGACY_THRESHOLDS = (80, 90, 95)
WINDOWS = {"primary": (300, "5 horas"), "secondary": (10080, "7 días")}
MAX_THRESHOLDS = 3


@dataclass(frozen=True)
class Alert:
    window: str
    threshold: int
    used: int


@dataclass(frozen=True)
class QueuedAlert:
    window: str
    threshold: int
    used: int
    cycle: int


def _valid_int(value: Any, low: int, high: int | None = None) -> bool:
    return (type(value) is int and value >= low and (high is None or value <= high))


def _valid_thresholds(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) <= MAX_THRESHOLDS
            and all(_valid_int(item, 1, 100) for item in value)
            and len(set(value)) == len(value))


def normalize_alert_settings(value: Any) -> dict[str, Any]:
    """Accept only known alert options and valid deduplication state."""
    source = value if isinstance(value, Mapping) else {}
    legacy = "thresholds" not in source and "active" not in source
    thresholds_source = source.get("enabled" if legacy else "thresholds")
    state_source = source.get("state")
    pending_source = source.get("pending")
    queued_source = source.get("queued")
    if not isinstance(thresholds_source, Mapping):
        thresholds_source = {}
    if not isinstance(state_source, Mapping):
        state_source = {}
    if not isinstance(pending_source, Mapping):
        pending_source = {}

    thresholds: dict[str, list[int]] = {}
    state: dict[str, dict[str, Any]] = {}
    pending: dict[str, list[int]] = {}
    for name in WINDOWS:
        raw = thresholds_source.get(name)
        if legacy:
            thresholds[name] = (
                [threshold for threshold in LEGACY_THRESHOLDS if threshold in raw]
                if isinstance(raw, list) and all(type(item) is int for item in raw)
                else []
            )
        else:
            thresholds[name] = sorted(raw) if _valid_thresholds(raw) else []
    active = (any(thresholds.values()) if legacy
              else source.get("active") is True)

    for name in WINDOWS:
        raw_pending = pending_source.get(name)
        pending[name] = (
            [threshold for threshold in thresholds[name] if threshold in raw_pending]
            if active and isinstance(raw_pending, list)
            and all(_valid_int(item, 1, 100) for item in raw_pending)
            else []
        )
        candidate = state_source.get(name)
        if not isinstance(candidate, Mapping):
            continue
        used = candidate.get("used")
        deadline = candidate.get("resets_at")
        notified = candidate.get("notified")
        if not (_valid_int(used, 0, 100) and _valid_int(deadline, 1)):
            continue
        if not isinstance(notified, list) or not all(type(item) is int for item in notified):
            continue
        state[name] = {
            "used": used,
            "resets_at": deadline,
            # Keep deduplication for valid thresholds that were removed and
            # might be configured again within this same cycle.
            "notified": sorted({item for item in notified if _valid_int(item, 1, 100)}),
        }
    queued: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    if isinstance(queued_source, list):
        for candidate in queued_source:
            if not isinstance(candidate, Mapping):
                continue
            name = candidate.get("window")
            threshold = candidate.get("threshold")
            used = candidate.get("used")
            cycle = candidate.get("cycle")
            if (not isinstance(name, str) or name not in WINDOWS or not active
                    or type(threshold) is not int or threshold not in thresholds[name]
                    or not _valid_int(used, threshold, 100)
                    or not _valid_int(cycle, 1)):
                continue
            key = (name, threshold, cycle)
            if key not in seen:
                queued.append(dict(window=name, threshold=threshold, used=used, cycle=cycle))
                seen.add(key)
    return {"active": active, "thresholds": thresholds, "state": state,
            "pending": pending, "queued": queued}


class UsageAlertEngine:
    def __init__(self, settings: Any = None):
        self._settings = normalize_alert_settings(settings)
        self._observed: set[str] = set()

    def to_settings(self) -> dict[str, Any]:
        return normalize_alert_settings(self._settings)

    def clone(self) -> UsageAlertEngine:
        result = UsageAlertEngine(self.to_settings())
        result._observed = self._observed.copy()
        return result

    def is_active(self) -> bool:
        return self._settings["active"]

    def thresholds(self, window: str) -> list[int]:
        return list(self._settings["thresholds"][window])

    def is_enabled(self, window: str, threshold: int) -> bool:
        return self.is_active() and threshold in self._settings["thresholds"][window]

    def queued_alerts(self) -> list[QueuedAlert]:
        return [QueuedAlert(**candidate) for candidate in self._settings["queued"]]

    def acknowledge(self, alerts: list[QueuedAlert]) -> None:
        keys = {(alert.window, alert.threshold, alert.cycle) for alert in alerts}
        self._settings["queued"] = [candidate for candidate in self._settings["queued"]
                                    if (candidate["window"], candidate["threshold"],
                                        candidate["cycle"]) not in keys]

    def configure(self, active: bool, thresholds: Mapping[str, list[int]]) -> None:
        if type(active) is not bool or not isinstance(thresholds, Mapping):
            raise ValueError("Invalid alert configuration")
        selected = {}
        for name in WINDOWS:
            raw = thresholds.get(name)
            if not _valid_thresholds(raw):
                raise ValueError(f"Invalid thresholds for {name}")
            selected[name] = sorted(raw)

        previously_active = self._settings["active"]
        previous = self._settings["thresholds"]
        for name in WINDOWS:
            newly_enabled = (set(selected[name])
                             - (set(previous[name]) if previously_active else set()))
            pending = self._settings["pending"][name]
            pending[:] = [level for level in pending if active and level in selected[name]]
            if active:
                state = self._settings["state"].get(name)
                for level in sorted(newly_enabled):
                    if name not in self._observed:
                        # The saved sample may predate the user's change.
                        if level not in pending:
                            pending.append(level)
                    elif state and state["used"] >= level and level not in state["notified"]:
                        state["notified"].append(level)
                if state:
                    state["notified"].sort()
                pending.sort()

        self._settings["active"] = active
        self._settings["thresholds"] = selected
        self._settings["queued"] = [candidate for candidate in self._settings["queued"]
                                    if active and candidate["threshold"]
                                    in selected[candidate["window"]]]

    def set_enabled(self, window: str, threshold: int, enabled: bool) -> None:
        """Compatibility helper for existing callers of individual thresholds."""
        if window not in WINDOWS or not _valid_int(threshold, 1, 100):
            raise ValueError("Unknown usage alert")
        selected = {name: self.thresholds(name) for name in WINDOWS}
        if enabled and threshold not in selected[window]:
            selected[window].append(threshold)
        elif not enabled and threshold in selected[window]:
            selected[window].remove(threshold)
        self.configure(self.is_active() or bool(enabled), selected)

    def process(self, usage: Usage, now: int | None = None) -> list[Alert]:
        current_time = int(time.time()) if now is None else now
        alerts: list[Alert] = []
        for name, (duration, _) in WINDOWS.items():
            window: Window | None = getattr(usage, name)
            if (window is None or window.duration_mins != duration
                    or not _valid_int(window.used, 0, 100)
                    or not _valid_int(window.resets_at, 1)
                    or window.resets_at <= current_time):
                # Incomplete or stale reads cannot create a crossing or erase
                # the last complete sample used after reconnection.
                continue

            self._observed.add(name)
            pending = self._settings["pending"][name]
            previous = self._settings["state"].get(name)
            new_cycle = False
            if previous is not None:
                old_deadline = previous["resets_at"]
                # A passed deadline alone is insufficient: the backend may
                # extend it shortly afterward without starting a new cycle.
                # Require both a substantial advance and a drop in usage.
                new_cycle = (window.resets_at - old_deadline >= duration * 30
                             and window.used < previous["used"])
            if previous is None or new_cycle:
                # A new or newly observed cycle starts with a baseline, even
                # if its first reading is already above an enabled threshold.
                self._settings["state"][name] = {
                    "used": window.used,
                    "resets_at": window.resets_at,
                    "notified": [threshold for threshold in pending
                                 if window.used >= threshold],
                }
                pending.clear()
                continue

            notified = previous["notified"]
            for threshold in pending:
                if window.used >= threshold and threshold not in notified:
                    notified.append(threshold)
            for threshold in (self._settings["thresholds"][name]
                              if self._settings["active"] else ()):
                if (previous["used"] < threshold <= window.used
                        and threshold not in notified and threshold not in pending):
                    alerts.append(Alert(name, threshold, window.used))
                    notified.append(threshold)
                    self._settings["queued"].append(dict(
                        window=name, threshold=threshold, used=window.used,
                        cycle=window.resets_at,
                    ))
            pending.clear()
            notified.sort()
            previous["used"] = window.used
            # A corrected deadline is stored, but does not by itself create
            # another cycle or clear previously sent thresholds.
            previous["resets_at"] = window.resets_at
        return alerts
