"""Strict as-of and chronological split guards for Atmos V4 research.

An observed timestamp is not proof that a product was available to a forecaster.
No assumed historical latency is accepted for certified skill.
"""
from datetime import datetime, timezone


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Naive timestamp: explicit UTC offset required")
    return value.astimezone(timezone.utc)


def asof_sensor(record, issue_time, *, verified_only=True):
    issue = utc(issue_time)
    observed = utc(record["observed_at_utc"])
    available = utc(record["available_at_utc"])
    if available < observed:
        raise ValueError("Sensor availability predates observation")
    provenance = str(record.get("availability_provenance", ""))
    if verified_only and (not provenance or provenance.startswith("ASSUMED_")):
        raise ValueError("Unverified historical sensor availability")
    return observed <= issue and available <= issue


def chronological_split(train_examples, evaluation_examples, *, embargo_hours=72):
    """Examples require issue_at_utc and target_at_utc; reject future-label training."""
    from datetime import timedelta
    if not evaluation_examples:
        raise ValueError("No evaluation examples")
    first_issue = min(utc(e["issue_at_utc"]) for e in evaluation_examples)
    cutoff = first_issue - timedelta(hours=embargo_hours)
    for row in train_examples:
        issue, target = utc(row["issue_at_utc"]), utc(row["target_at_utc"])
        if target < issue:
            raise ValueError("Target predates issue")
        if target > cutoff:
            raise ValueError("Temporal leakage: training label unavailable before evaluation")
    for row in evaluation_examples:
        if utc(row["target_at_utc"]) <= utc(row["issue_at_utc"]):
            raise ValueError("Evaluation target must follow issue")
    return True


def reject_frozen_v2_for_chronological_claim(checkpoint_end, earliest_issue):
    if utc(checkpoint_end) >= utc(earliest_issue):
        raise ValueError("Frozen V2 trained through evaluation period; refit baseline as-of each cutoff")
    return True
