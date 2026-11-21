"""Fail-closed temporal provenance checks for historical forecast training.

Observations are targets, never predictors, unless publication time is proven
to precede the forecast issue time. This module does not modify NOAA archives.
"""
from datetime import datetime, timezone


def utc(value):
    if not value or not isinstance(value, str):
        raise ValueError("Missing timestamp with explicit UTC offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-naive timestamp is prohibited")
    return parsed.astimezone(timezone.utc)


def validate_forecast(record):
    """Require genuine issued forecast provenance and future valid interval."""
    if record.get("source_kind") != "issued_forecast":
        raise ValueError("Not a genuine issued forecast")
    if not record.get("source_id") or not record.get("model"):
        raise ValueError("Missing forecast source identity")
    issued = utc(record.get("issue_time_utc"))
    start = utc(record.get("valid_start_utc"))
    end = utc(record.get("valid_end_utc"))
    if not issued < start < end:
        raise ValueError("Forecast issue/valid interval order invalid")
    return issued


def validate_observation(record):
    """Require independently observed truth and a known publication time."""
    if record.get("independent") is not True:
        raise ValueError("Observation independence unverified")
    if record.get("quality_flag") != "verified":
        raise ValueError("Observation quality unverified")
    if not record.get("source_id"):
        raise ValueError("Missing observation source identity")
    start = utc(record.get("valid_start_utc"))
    end = utc(record.get("valid_end_utc"))
    published = utc(record.get("published_at_utc"))
    if not start < end <= published:
        raise ValueError("Observation interval/publication order invalid")
    return published


def predictor_allowed(forecast, predictor):
    """Fail closed: unknown availability must never become a training feature."""
    issued = validate_forecast(forecast)
    available = utc(predictor.get("available_at_utc"))
    if not predictor.get("source_id"):
        raise ValueError("Missing predictor provenance")
    if available > issued:
        raise ValueError("Future information leakage")
    return True


def match_truth(forecast, observation):
    """Match verification truth without allowing it into predictor features."""
    validate_forecast(forecast)
    validate_observation(observation)
    fields = ("location_id", "metric", "unit", "valid_start_utc", "valid_end_utc")
    if any(forecast.get(k) != observation.get(k) for k in fields):
        raise ValueError("Forecast/observation interval or identity mismatch")
    return True
