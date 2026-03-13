"""Gmail connector — uses gog CLI to pull emails into graph events."""

from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)
from percept.connectors.sdk.auth import AuthHelper


# gog gmail list --json --results-only returns:
# [{"id": "...", "date": "YYYY-MM-DD HH:MM", "from": "Name <email>",
#   "subject": "...", "labels": [...], "messageCount": N}]
#
# gog gmail read <id> --json --results-only returns:
# {"thread": {"id": "...", "messages": [{"id": "...", "payload": {"headers": [...]}}]}}


def _parse_email_address(raw: str) -> tuple[str, str]:
    """Parse 'Name <email>' or bare 'email' into (name, email)."""
    m = re.match(r'^(.+?)\s*<([^>]+)>$', raw.strip())
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip()
    # bare email
    raw = raw.strip()
    return raw.split("@")[0], raw


def _parse_date(date_str: str) -> datetime:
    """Parse gog date format 'YYYY-MM-DD HH:MM' or ISO format."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class GmailConnector(BaseConnector):
    name = "gmail"
    version = "0.2.0"
    auth_type = "oauth2"
    description = "Pull emails from Gmail via gog CLI"

    GOG_CLI = "/opt/homebrew/bin/gog"

    # Mock data for testing / fallback
    MOCK_EMAILS = [
        {
            "id": "msg-001",
            "threadId": "thread-001",
            "from": "alice@example.com",
            "fromName": "Alice Johnson",
            "to": ["user@example.com"],
            "cc": ["bob@example.com"],
            "subject": "Q1 Board Deck Review",
            "date": "2026-03-10T14:30:00Z",
            "snippet": "Hey David, attached is the Q1 board deck. Let me know your thoughts.",
        },
        {
            "id": "msg-002",
            "threadId": "thread-001",
            "from": "user@example.com",
            "fromName": "GetPercept Team",
            "to": ["alice@example.com"],
            "cc": [],
            "subject": "Re: Q1 Board Deck Review",
            "date": "2026-03-10T16:00:00Z",
            "snippet": "Looks great, just a few comments on slide 12.",
        },
        {
            "id": "msg-003",
            "threadId": "thread-002",
            "from": "carol@vectorcare.com",
            "fromName": "Carol Chen",
            "to": ["user@example.com"],
            "cc": [],
            "subject": "FHIR Integration Update",
            "date": "2026-03-11T09:00:00Z",
            "snippet": "The SMART on FHIR R4 endpoint is live in staging.",
        },
    ]

    def __init__(self, mock: bool = False, max_results: int = 20, query: str = "in:inbox"):
        super().__init__(mock=mock)
        self.max_results = max_results
        self.query = query

    def authenticate(self, credentials: dict) -> bool:
        if self._mock_mode:
            self._authenticated = True
            return True
        if AuthHelper.check_gog_auth():
            self._authenticated = True
            return True
        self._authenticated = False
        return False

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        ok, output = AuthHelper.run_cli(
            [self.GOG_CLI, "gmail", "list", "--json", "--results-only", "in:inbox"],
            timeout=15,
        )
        return ok

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.PERSON,
                name="Person",
                description="Email sender or recipient",
                properties=["email", "name"],
            ),
            EntitySchema(
                entity_type=EntityType.DOCUMENT,
                name="Email",
                description="An email message",
                properties=["subject", "snippet", "date", "message_id"],
            ),
            EntitySchema(
                entity_type=EntityType.THREAD,
                name="Thread",
                description="An email thread/conversation",
                properties=["subject", "message_count"],
            ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_emails(self.MOCK_EMAILS, since)
        try:
            return self._pull_live(since)
        except Exception as e:
            print(f"[gmail] Live pull failed ({e}), falling back to mock data")
            return self._process_emails(self.MOCK_EMAILS, since)

    def _pull_live(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        """Pull from real Gmail via gog CLI."""
        # Build query — use since date if available
        query = self.query
        if since:
            date_str = since.strftime("%Y/%m/%d")
            query = f"{query} after:{date_str}"

        cmd = [self.GOG_CLI, "gmail", "list", "--json", "--results-only", query]
        ok, output = AuthHelper.run_cli(cmd, timeout=30)
        if not ok:
            raise RuntimeError(f"gog gmail list failed: {output}")

        try:
            raw_threads = json.loads(output)
        except json.JSONDecodeError:
            raise RuntimeError(f"gog returned non-JSON: {output[:200]}")

        if not isinstance(raw_threads, list):
            raw_threads = [raw_threads]

        # Normalize gog list output into our internal email format
        emails = []
        for thread in raw_threads[:self.max_results]:
            from_name, from_email = _parse_email_address(thread.get("from", ""))
            emails.append({
                "id": thread.get("id", ""),
                "threadId": thread.get("id", ""),  # gog list id IS the thread id
                "from": from_email,
                "fromName": from_name,
                "to": [],  # Not in list output; would need per-message read
                "cc": [],
                "subject": thread.get("subject", "(no subject)"),
                "date": thread.get("date", ""),
                "snippet": thread.get("subject", ""),  # List doesn't give snippets
                "labels": thread.get("labels", []),
                "messageCount": thread.get("messageCount", 1),
            })

        return self._process_emails(emails, since)

    def _process_emails(self, emails: list[dict], since: Optional[datetime] = None) -> list[GraphEvent]:
        """Convert raw email dicts into GraphEvents."""
        events: list[GraphEvent] = []
        seen_people: set[str] = set()
        seen_threads: set[str] = set()

        for email in emails:
            email_date = email.get("date", "")
            if isinstance(email_date, str) and email_date:
                dt = _parse_date(email_date)
                if since and dt < since:
                    continue
            else:
                dt = datetime.now(timezone.utc)

            msg_id = email.get("id", hashlib.md5(email.get("subject", "").encode()).hexdigest())

            # --- Person nodes (sender) ---
            from_raw = email.get("from", "")
            from_name = email.get("fromName", "")
            if not from_name:
                from_name, from_raw = _parse_email_address(from_raw)
            from_email = from_raw
            person_id = f"person:{from_email}"
            if from_email and person_id not in seen_people:
                seen_people.add(person_id)
                events.append(self._make_node_event(
                    Node(
                        id=person_id,
                        entity_type=EntityType.PERSON,
                        name=from_name,
                        properties={"email": from_email},
                    ),
                    raw=email,
                ))

            # --- Person nodes (recipients) ---
            for recipient in email.get("to", []):
                r_name, r_email = _parse_email_address(recipient) if "@" in recipient else (recipient, recipient)
                r_id = f"person:{r_email}"
                if r_id not in seen_people:
                    seen_people.add(r_id)
                    events.append(self._make_node_event(
                        Node(
                            id=r_id,
                            entity_type=EntityType.PERSON,
                            name=r_name,
                            properties={"email": r_email},
                        ),
                    ))

            # --- CC recipients ---
            for cc in email.get("cc", []):
                cc_name, cc_email = _parse_email_address(cc) if "@" in cc else (cc, cc)
                cc_id = f"person:{cc_email}"
                if cc_id not in seen_people:
                    seen_people.add(cc_id)
                    events.append(self._make_node_event(
                        Node(
                            id=cc_id,
                            entity_type=EntityType.PERSON,
                            name=cc_name,
                            properties={"email": cc_email},
                        ),
                    ))

            # --- Email node ---
            email_node_id = f"email:{msg_id}"
            events.append(self._make_node_event(
                Node(
                    id=email_node_id,
                    entity_type=EntityType.DOCUMENT,
                    name=email.get("subject", "(no subject)"),
                    properties={
                        "message_id": msg_id,
                        "snippet": email.get("snippet", ""),
                        "date": email_date,
                        "labels": email.get("labels", []),
                        "message_count": email.get("messageCount", 1),
                        "kind": "email",
                    },
                    created_at=dt,
                ),
                raw=email,
            ))

            # --- Thread node ---
            thread_id = email.get("threadId", "")
            if thread_id and thread_id not in seen_threads:
                seen_threads.add(thread_id)
                events.append(self._make_node_event(
                    Node(
                        id=f"thread:{thread_id}",
                        entity_type=EntityType.THREAD,
                        name=email.get("subject", "(no subject)"),
                        properties={
                            "thread_id": thread_id,
                            "message_count": email.get("messageCount", 1),
                        },
                    ),
                ))

            # --- Edges: SENT_TO ---
            for recipient in email.get("to", []):
                _, r_email = _parse_email_address(recipient) if "@" in recipient else (recipient, recipient)
                events.append(self._make_edge_event(
                    Edge(
                        source_id=person_id,
                        target_id=f"person:{r_email}",
                        relation="SENT_TO",
                        properties={"via": email_node_id},
                    ),
                ))

            # --- Edges: CC_TO ---
            for cc in email.get("cc", []):
                _, cc_email = _parse_email_address(cc) if "@" in cc else (cc, cc)
                events.append(self._make_edge_event(
                    Edge(
                        source_id=person_id,
                        target_id=f"person:{cc_email}",
                        relation="CC_TO",
                        properties={"via": email_node_id},
                    ),
                ))

            # --- Edge: AUTHORED (sender → email) ---
            events.append(self._make_edge_event(
                Edge(
                    source_id=person_id,
                    target_id=email_node_id,
                    relation="AUTHORED",
                ),
            ))

            # --- Edge: email belongs to thread ---
            if thread_id:
                events.append(self._make_edge_event(
                    Edge(
                        source_id=email_node_id,
                        target_id=f"thread:{thread_id}",
                        relation="PART_OF",
                    ),
                ))

            # --- Edge: REPLIED_TO (if Re: in subject) ---
            subject = email.get("subject", "")
            if subject.lower().startswith("re:") and thread_id:
                events.append(self._make_edge_event(
                    Edge(
                        source_id=email_node_id,
                        target_id=f"thread:{thread_id}",
                        relation="REPLIED_TO",
                    ),
                ))

        return events
