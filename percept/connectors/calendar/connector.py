"""Calendar connector — uses gog CLI to pull Google Calendar events into graph events.

Falls back to mock data when the Google Calendar API is disabled.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)
from percept.connectors.sdk.auth import AuthHelper


# Mock data for when the Calendar API is disabled
MOCK_EVENTS = [
    {
        "id": "evt-001",
        "summary": "Weekly Team Standup",
        "start": "2026-03-12T10:00:00-07:00",
        "end": "2026-03-12T10:30:00-07:00",
        "organizer": {"name": "GetPercept Team", "email": "user@example.com"},
        "attendees": [
            {"name": "Alice Johnson", "email": "alice@vectorcare.com", "status": "accepted"},
            {"name": "Bob Smith", "email": "bob@vectorcare.com", "status": "tentative"},
        ],
        "location": "Zoom",
        "status": "confirmed",
    },
    {
        "id": "evt-002",
        "summary": "Investor Call — Series A Update",
        "start": "2026-03-13T14:00:00-07:00",
        "end": "2026-03-13T15:00:00-07:00",
        "organizer": {"name": "GetPercept Team", "email": "user@example.com"},
        "attendees": [
            {"name": "Carol Chen", "email": "carol@vc-firm.com", "status": "accepted"},
        ],
        "location": "Google Meet",
        "status": "confirmed",
    },
    {
        "id": "evt-003",
        "summary": "FHIR Integration Review",
        "start": "2026-03-14T11:00:00-07:00",
        "end": "2026-03-14T12:00:00-07:00",
        "organizer": {"name": "Carol Chen", "email": "carol@vectorcare.com"},
        "attendees": [
            {"name": "GetPercept Team", "email": "user@example.com", "status": "accepted"},
            {"name": "Eve Park", "email": "eve@vectorcare.com", "status": "needsAction"},
        ],
        "location": "",
        "status": "confirmed",
    },
]


def _parse_dt(s: str) -> datetime:
    """Parse ISO datetime string."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class CalendarConnector(BaseConnector):
    name = "calendar"
    version = "0.1.0"
    auth_type = "oauth2"
    description = "Pull calendar events from Google Calendar via gog CLI"

    GOG_CLI = "/opt/homebrew/bin/gog"

    def __init__(self, mock: bool = False, max_events: int = 20):
        super().__init__(mock=mock)
        self.max_events = max_events

    def authenticate(self, credentials: dict) -> bool:
        if self._mock_mode:
            self._authenticated = True
            return True

        # Check if gog CLI has calendar access
        ok, output = AuthHelper.run_cli(
            [self.GOG_CLI, "calendar", "list", "--max", "1"],
            timeout=15,
        )
        if ok:
            self._authenticated = True
            return True

        # API likely disabled — fall back to mock
        print("[calendar] Google Calendar API not available, using mock mode")
        self._mock_mode = True
        self._authenticated = True
        return True

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        ok, _ = AuthHelper.run_cli(
            [self.GOG_CLI, "calendar", "list", "--max", "1"],
            timeout=15,
        )
        return ok

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.EVENT,
                name="CalendarEvent",
                description="A Google Calendar event",
                properties=["start", "end", "location", "status"],
            ),
            EntitySchema(
                entity_type=EntityType.PERSON,
                name="Person",
                description="An event organizer or attendee",
                properties=["email", "name"],
            ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_events(MOCK_EVENTS, since)

        try:
            return self._pull_live(since)
        except Exception as e:
            print(f"[calendar] Live pull failed ({e}), falling back to mock data")
            return self._process_events(MOCK_EVENTS, since)

    def _pull_live(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        """Pull from real Google Calendar via gog CLI."""
        cmd = [self.GOG_CLI, "calendar", "list", "--max", str(self.max_events)]

        ok, output = AuthHelper.run_cli(cmd, timeout=30)
        if not ok:
            raise RuntimeError(f"gog calendar list failed: {output}")

        events = self._parse_gog_output(output)
        return self._process_events(events, since)

    def _parse_gog_output(self, output: str) -> list[dict]:
        """Parse gog calendar list text output into event dicts.

        gog calendar list outputs lines like:
            📅 2026-03-12 10:00  Weekly Team Standup (30m)
            📅 2026-03-13 14:00  Investor Call (1h)

        We extract what we can and fill in the rest.
        """
        events = []
        lines = output.strip().split("\n")

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Try to parse "📅 YYYY-MM-DD HH:MM  Title (duration)" or similar
            m = re.match(
                r'[📅🗓️]*\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(.*)',
                line,
            )
            if m:
                date_str, time_str, rest = m.groups()
                # Extract duration if present
                dur_match = re.search(r'\((\d+)([mh])\)\s*$', rest)
                title = re.sub(r'\s*\(\d+[mh]\)\s*$', '', rest).strip()

                start = f"{date_str}T{time_str}:00"
                events.append({
                    "id": f"cal-{i}",
                    "summary": title,
                    "start": start,
                    "end": "",
                    "organizer": {},
                    "attendees": [],
                    "location": "",
                    "status": "confirmed",
                })
            else:
                # Fallback: just use the line as the event title
                if line and not line.startswith("#") and not line.startswith("─"):
                    events.append({
                        "id": f"cal-{i}",
                        "summary": line,
                        "start": datetime.now(timezone.utc).isoformat(),
                        "end": "",
                        "organizer": {},
                        "attendees": [],
                        "location": "",
                        "status": "confirmed",
                    })

        return events

    def _process_events(
        self, events: list[dict], since: Optional[datetime] = None
    ) -> list[GraphEvent]:
        """Convert raw event dicts into GraphEvents."""
        graph_events: list[GraphEvent] = []
        seen_people: set[str] = set()

        for event in events:
            start_str = event.get("start", "")
            if start_str:
                start_dt = _parse_dt(start_str)
                if since and start_dt < since:
                    continue
            else:
                start_dt = datetime.now(timezone.utc)

            event_id = f"cal-event:{event['id']}"

            # --- Event node ---
            graph_events.append(self._make_node_event(
                Node(
                    id=event_id,
                    entity_type=EntityType.EVENT,
                    name=event.get("summary", "(no title)"),
                    properties={
                        "start": event.get("start", ""),
                        "end": event.get("end", ""),
                        "location": event.get("location", ""),
                        "status": event.get("status", ""),
                        "kind": "calendar_event",
                    },
                    created_at=start_dt,
                ),
                raw=event,
            ))

            # --- Organizer ---
            organizer = event.get("organizer", {})
            if organizer and organizer.get("email"):
                org_id = f"person:{organizer['email']}"
                if org_id not in seen_people:
                    seen_people.add(org_id)
                    graph_events.append(self._make_node_event(
                        Node(
                            id=org_id,
                            entity_type=EntityType.PERSON,
                            name=organizer.get("name", organizer["email"]),
                            properties={"email": organizer["email"]},
                        ),
                    ))

                graph_events.append(self._make_edge_event(
                    Edge(
                        source_id=org_id,
                        target_id=event_id,
                        relation="ORGANIZED_BY",
                    ),
                ))

            # --- Attendees ---
            for attendee in event.get("attendees", []):
                email = attendee.get("email", "")
                if not email:
                    continue

                att_id = f"person:{email}"
                if att_id not in seen_people:
                    seen_people.add(att_id)
                    graph_events.append(self._make_node_event(
                        Node(
                            id=att_id,
                            entity_type=EntityType.PERSON,
                            name=attendee.get("name", email),
                            properties={"email": email},
                        ),
                    ))

                graph_events.append(self._make_edge_event(
                    Edge(
                        source_id=att_id,
                        target_id=event_id,
                        relation="ATTENDING",
                        properties={
                            "rsvp_status": attendee.get("status", ""),
                        },
                    ),
                ))

        return graph_events
