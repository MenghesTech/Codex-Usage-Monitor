from src.usage_model import parse_usage


def snapshot():
    return {
        "ordinaryUsageAllowed": False,
        "rateLimits": {
            "primary": {
                "usedPercent": 73,
                "windowDurationMins": 300,
                "resetsAt": 2_000_000_000,
            },
            "secondary": {
                "usedPercent": 41,
                "windowDurationMins": 10080,
                "resetsAt": 2_000_500_000,
            },
            "planType": "plus",
            "rateLimitReachedType": "primary",
        },
    }


def test_primary_secondary_used_percent_and_allowed_are_preserved():
    usage = parse_usage(snapshot())

    assert usage.allowed is False
    assert usage.primary.used == 73
    assert usage.primary.duration_mins == 300
    assert usage.primary.resets_at == 2_000_000_000
    assert usage.secondary.used == 41
    assert usage.secondary.duration_mins == 10080
    assert usage.plan == "plus"
    assert usage.reached_type == "primary"


def test_null_values_are_allowed():
    usage = parse_usage(
        {
            "ordinaryUsageAllowed": None,
            "rateLimits": {
                "primary": {
                    "usedPercent": None,
                    "windowDurationMins": None,
                    "resetsAt": None,
                },
                "secondary": None,
            },
            "rateLimitResetCredits": None,
        }
    )

    assert usage.allowed is None
    assert usage.primary.used is None
    assert usage.primary.remaining is None
    assert usage.primary.reset_local() is None
    assert usage.secondary is None
    assert usage.reset_credits == 0


def test_rate_limits_remains_primary_when_by_id_is_also_present():
    data = snapshot()
    data["rateLimitsByLimitId"] = {
        "some-other-limit": {"primary": {"usedPercent": 99}}
    }

    assert parse_usage(data).primary.used == 73


def test_single_rate_limits_by_id_bucket_is_unambiguous_fallback():
    usage = parse_usage(
        {
            "ordinaryUsageAllowed": True,
            "rateLimitsByLimitId": {
                "only-limit": {
                    "primary": {
                        "usedPercent": 12,
                        "windowDurationMins": 300,
                        "resetsAt": 2_000_000_000,
                    },
                    "secondary": {
                        "usedPercent": 34,
                        "windowDurationMins": 10080,
                        "resetsAt": 2_000_500_000,
                    },
                }
            },
        }
    )

    assert usage.primary.used == 12
    assert usage.secondary.used == 34


def test_multiple_by_id_buckets_are_not_selected_arbitrarily():
    usage = parse_usage(
        {
            "ordinaryUsageAllowed": True,
            "rateLimitsByLimitId": {
                "a": {"primary": {"usedPercent": 1}},
                "b": {"primary": {"usedPercent": 2}},
            },
        }
    )

    assert usage.primary is None
    assert usage.secondary is None
