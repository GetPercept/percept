"""Signal extraction from graph events — detects patterns worth acting on."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent paths for imports
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "percept-connectors"))
sys.path.insert(0, str(_root / "percept-initiative"))

from percept.connectors.sdk.base import GraphEvent, EntityType
from percept.initiatives.engine.signals import Signal


def extract_signals(
    events: list[GraphEvent],
    *,
    stale_pr_days: int = 3,
    high_activity_threshold: int = 3,
    known_contacts: set[str] | None = None,
) -> list[Signal]:
    """Extract actionable signals from a batch of graph events.

    Returns Signal objects compatible with the Initiative Engine.
    """
    signals: list[Signal] = []
    now = datetime.now(timezone.utc)

    # Collect data for pattern detection
    person_thread_count: Counter[str] = Counter()  # person_id -> thread appearances
    pr_states: dict[str, dict] = {}  # pr_id -> {state, created, has_review, title, url}
    email_senders: list[dict] = []  # [{person_id, email, name, subject}]

    for event in events:
        node = event.node
        edge = event.edge

        # Track email senders for new_contact detection
        if node and node.entity_type == EntityType.PERSON:
            email = node.properties.get("email", "")
            if email and event.source == "gmail":
                email_senders.append({
                    "person_id": node.id,
                    "email": email,
                    "name": node.name,
                })

        # Track PRs for stale_pr detection
        if node and node.entity_type == EntityType.DOCUMENT:
            props = node.properties
            if props.get("kind") == "pull_request":
                pr_states[node.id] = {
                    "state": props.get("state", ""),
                    "created": props.get("created_at", node.created_at.isoformat() if isinstance(node.created_at, datetime) else str(node.created_at)),
                    "has_review": False,
                    "title": node.name,
                    "url": props.get("url", ""),
                    "number": props.get("number", ""),
                }

        # Track reviews for stale_pr detection
        if edge and edge.relation == "REVIEWED":
            target = edge.target_id
            if target in pr_states:
                pr_states[target]["has_review"] = True

        # Track person-thread connections for high_activity
        if edge and edge.relation in ("AUTHORED", "SENT_TO", "CC_TO"):
            person_thread_count[edge.source_id] += 1

    # --- Signal: new_contact ---
    known = known_contacts or set()
    for sender in email_senders:
        if sender["email"] not in known and not sender["email"].endswith("@example.com"):
            signals.append(Signal(
                source="gmail",
                signal_type="new_contact",
                entity=sender["person_id"],
                data={
                    "email": sender["email"],
                    "name": sender["name"],
                },
                urgency=0.3,
            ))

    # --- Signal: stale_pr (open > N days, no review) ---
    for pr_id, info in pr_states.items():
        if info["state"] in ("OPEN", "open"):
            try:
                created_str = info["created"]
                if isinstance(created_str, str) and created_str:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                else:
                    continue
                age_days = (now - created).days
                if age_days >= stale_pr_days and not info["has_review"]:
                    signals.append(Signal(
                        source="github",
                        signal_type="stale_pr",
                        entity=pr_id,
                        data={
                            "title": info["title"],
                            "url": info["url"],
                            "number": info["number"],
                            "age_days": age_days,
                            "days": age_days,
                        },
                        urgency=min(0.4 + (age_days - stale_pr_days) * 0.1, 0.9),
                    ))
            except (ValueError, TypeError):
                continue

    # --- Signal: high_activity (same person in N+ threads) ---
    for person_id, count in person_thread_count.items():
        if count >= high_activity_threshold:
            signals.append(Signal(
                source="pipeline",
                signal_type="high_activity",
                entity=person_id,
                data={
                    "person": person_id,
                    "thread_count": count,
                    "count": count,
                },
                urgency=0.4,
            ))

    return signals
