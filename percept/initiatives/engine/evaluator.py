"""Condition matching logic — evaluates rules against signal buffer."""
from __future__ import annotations

from typing import Any

from percept.initiatives.engine.rules import Condition, Rule
from percept.initiatives.engine.signals import Signal, SignalBuffer


def evaluate_condition(condition: Condition, buffer: SignalBuffer) -> tuple[bool, list[Signal]]:
    """
    Check if a condition is met against the signal buffer.
    Returns (matched: bool, matching_signals: list).
    """
    signals = buffer.query(
        source=condition.source,
        signal_type=condition.signal_type,
        since_minutes=condition.time_window_minutes,
    )

    if not signals:
        return False, []

    if condition.operator == "exists":
        return True, signals

    # For comparison operators, check the data field
    matching = []
    for sig in signals:
        field_value = _extract_field(sig, condition.field)
        if field_value is None:
            continue
        if _compare(field_value, condition.operator, condition.value):
            matching.append(sig)

    return len(matching) > 0, matching


def _extract_field(signal: Signal, field_name: str) -> Any:
    """Extract a field value from signal data."""
    if field_name == "value" and "value" not in signal.data:
        # Try common field names
        for key in ("count", "score", "amount", "percent", "hours", "days"):
            if key in signal.data:
                return signal.data[key]
        return None
    return signal.data.get(field_name)


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """Compare a value using the given operator."""
    try:
        if operator == "gt":
            return float(actual) > float(expected)
        elif operator == "lt":
            return float(actual) < float(expected)
        elif operator == "eq":
            return str(actual) == str(expected)
        elif operator == "gte":
            return float(actual) >= float(expected)
        elif operator == "lte":
            return float(actual) <= float(expected)
        elif operator == "contains":
            return str(expected).lower() in str(actual).lower()
        elif operator == "not_eq":
            return str(actual) != str(expected)
        elif operator == "exists":
            return actual is not None
    except (ValueError, TypeError):
        return False
    return False


def evaluate_rule(rule: Rule, buffer: SignalBuffer) -> tuple[bool, dict]:
    """
    Evaluate all conditions for a rule (AND logic).
    Returns (all_met: bool, context: dict with matched signal data).
    """
    if not rule.enabled:
        return False, {}

    if not rule.conditions:
        return False, {}

    context = {}
    all_signals = []

    for condition in rule.conditions:
        met, signals = evaluate_condition(condition, buffer)
        if not met:
            return False, {}
        all_signals.extend(signals)
        # Merge signal data into context for template rendering
        for sig in signals:
            context.update(sig.data)
            context[f"{sig.source}_{sig.signal_type}"] = True

    # Add metadata
    context["_matched_signals"] = len(all_signals)
    context["_rule_name"] = rule.name

    return True, context
