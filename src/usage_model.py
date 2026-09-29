from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass
class Window:
    used: int | None
    duration_mins: int | None
    resets_at: int | None

    @property
    def remaining(self) -> int | None:
        return None if self.used is None else max(0, 100 - self.used)

    def reset_local(self) -> datetime | None:
        if self.resets_at is None:
            return None
        return datetime.fromtimestamp(self.resets_at, tz=timezone.utc).astimezone()


@dataclass
class Usage:
    allowed: bool | None
    primary: Window | None
    secondary: Window | None
    plan: str | None
    reached_type: str | None
    reset_credits: int


@dataclass
class ResetDeadlines:
    """Ephemeral deadlines from the latest complete backend snapshot."""

    primary: datetime | None = None
    secondary: datetime | None = None

    def replace(self, usage: Usage) -> None:
        self.primary = usage.primary.reset_local() if usage.primary else None
        self.secondary = usage.secondary.reset_local() if usage.secondary else None


def seconds_until(deadline: datetime | None, now: datetime | None = None) -> int | None:
    if deadline is None:
        return None
    current = now if now is not None else datetime.now().astimezone()
    return max(0, int((deadline - current).total_seconds()))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _window(value: Any) -> Window | None:
    if not isinstance(value, Mapping):
        return None
    return Window(
        _optional_int(value.get("usedPercent")),
        _optional_int(value.get("windowDurationMins")),
        _optional_int(value.get("resetsAt")),
    )


def _select_rate_limits(result: Mapping[str, Any]) -> Mapping[str, Any]:
    # rateLimits is the aggregate snapshot historically shown by the widget.
    # A per-limit map has no general ordering or preferred id. It is safe as a
    # fallback only when exactly one mapping exists.
    aggregate = result.get("rateLimits")
    if isinstance(aggregate, Mapping):
        return aggregate

    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, Mapping):
        candidates = [value for value in by_id.values() if isinstance(value, Mapping)]
        if len(candidates) == 1:
            return candidates[0]
    return {}


def parse_usage(result: Mapping[str, Any]) -> Usage:
    rate_limits = _select_rate_limits(result)
    credits = result.get("rateLimitResetCredits")
    if not isinstance(credits, Mapping):
        credits = {}
    return Usage(
        result.get("ordinaryUsageAllowed"),
        _window(rate_limits.get("primary")),
        _window(rate_limits.get("secondary")),
        rate_limits.get("planType"),
        rate_limits.get("rateLimitReachedType"),
        int(credits.get("availableCount") or 0),
    )
