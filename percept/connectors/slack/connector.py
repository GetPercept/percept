"""Slack connector — mock mode for now, real API when token available."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)


class SlackConnector(BaseConnector):
    name = "slack"
    version = "0.1.0"
    auth_type = "token"
    description = "Pull messages, threads, and reactions from Slack"

    MOCK_USERS = {
        "U001": {"name": "Alice Johnson", "real_name": "Alice Johnson", "email": "alice@example.com"},
        "U002": {"name": "Bob Smith", "real_name": "Bob Smith", "email": "bob@example.com"},
        "U003": {"name": "Carol Chen", "real_name": "Carol Chen", "email": "carol@vectorcare.com"},
    }

    MOCK_CHANNELS = {
        "C001": {"name": "general", "topic": "Company-wide announcements"},
        "C002": {"name": "engineering", "topic": "Engineering discussion"},
        "C003": {"name": "product", "topic": "Product updates and feedback"},
    }

    MOCK_MESSAGES = [
        {
            "ts": "1710165600.000100",
            "channel": "C002",
            "user": "U001",
            "text": "Just deployed the new FHIR endpoint to staging 🚀",
            "thread_ts": None,
            "reactions": [{"name": "rocket", "users": ["U002", "U003"]}],
        },
        {
            "ts": "1710165900.000200",
            "channel": "C002",
            "user": "U003",
            "text": "Nice! I'll run the integration tests now.",
            "thread_ts": "1710165600.000100",
            "reactions": [{"name": "+1", "users": ["U001"]}],
        },
        {
            "ts": "1710169200.000300",
            "channel": "C003",
            "user": "U002",
            "text": "Customer feedback on the transport dashboard: they want real-time GPS tracking.",
            "thread_ts": None,
            "reactions": [],
        },
        {
            "ts": "1710172800.000400",
            "channel": "C001",
            "user": "U003",
            "text": "@alice Can you review the Q1 metrics before the board meeting?",
            "thread_ts": None,
            "reactions": [],
            "mentions": ["U001"],
        },
    ]

    def __init__(self, token: str = "", mock: bool = False):
        super().__init__(mock=mock)
        self._token = token
        # Always mock if no token
        if not token:
            self._mock_mode = True

    def authenticate(self, credentials: dict) -> bool:
        token = credentials.get("token", "") or self._token
        if token:
            self._token = token
            # Would call Slack auth.test here
            self._authenticated = True
            return True
        if self._mock_mode:
            self._authenticated = True
            return True
        return False

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        # Would call Slack auth.test
        return bool(self._token)

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.PERSON,
                name="User",
                description="Slack workspace member",
                properties=["slack_id", "name", "email"],
            ),
            EntitySchema(
                entity_type=EntityType.CHANNEL,
                name="Channel",
                description="Slack channel",
                properties=["slack_id", "name", "topic"],
            ),
            EntitySchema(
                entity_type=EntityType.DOCUMENT,
                name="Message",
                description="A Slack message",
                properties=["ts", "text", "channel", "thread_ts"],
            ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_mock(since)
        return self._pull_live(since)

    def _pull_live(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        """Pull from real Slack API — requires requests."""
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests library required for live Slack API calls")

        headers = {"Authorization": f"Bearer {self._token}"}
        events: list[GraphEvent] = []

        # Get channels
        resp = requests.get(
            "https://slack.com/api/conversations.list",
            headers=headers,
            params={"types": "public_channel", "limit": 50},
        )
        channels = resp.json().get("channels", []) if resp.ok else []

        for ch in channels:
            events.append(self._make_node_event(
                Node(
                    id=f"slack:channel:{ch['id']}",
                    entity_type=EntityType.CHANNEL,
                    name=ch.get("name", ""),
                    properties={
                        "slack_id": ch["id"],
                        "topic": ch.get("topic", {}).get("value", ""),
                    },
                ),
            ))

            # Get messages
            params = {"channel": ch["id"], "limit": 20}
            if since:
                params["oldest"] = str(since.timestamp())

            resp = requests.get(
                "https://slack.com/api/conversations.history",
                headers=headers,
                params=params,
            )
            messages = resp.json().get("messages", []) if resp.ok else []
            events.extend(self._process_messages(messages, ch["id"]))

        return events

    def _process_mock(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        events: list[GraphEvent] = []

        # User nodes
        for uid, info in self.MOCK_USERS.items():
            events.append(self._make_node_event(
                Node(
                    id=f"slack:user:{uid}",
                    entity_type=EntityType.PERSON,
                    name=info["real_name"],
                    properties={"slack_id": uid, "email": info.get("email", "")},
                ),
            ))

        # Channel nodes
        for cid, info in self.MOCK_CHANNELS.items():
            events.append(self._make_node_event(
                Node(
                    id=f"slack:channel:{cid}",
                    entity_type=EntityType.CHANNEL,
                    name=info["name"],
                    properties={"slack_id": cid, "topic": info.get("topic", "")},
                ),
            ))

        # Messages
        events.extend(self._process_messages(self.MOCK_MESSAGES, None))

        return events

    def _process_messages(self, messages: list[dict], channel_id: Optional[str]) -> list[GraphEvent]:
        events: list[GraphEvent] = []

        for msg in messages:
            ch = msg.get("channel", channel_id or "unknown")
            ts = msg.get("ts", "")
            user = msg.get("user", "unknown")
            msg_id = f"slack:msg:{ch}:{ts}"
            user_id = f"slack:user:{user}"

            # Message node
            events.append(self._make_node_event(
                Node(
                    id=msg_id,
                    entity_type=EntityType.DOCUMENT,
                    name=msg.get("text", "")[:80],
                    properties={
                        "text": msg.get("text", ""),
                        "ts": ts,
                        "channel": ch,
                        "thread_ts": msg.get("thread_ts"),
                        "kind": "slack_message",
                    },
                ),
                raw=msg,
            ))

            # Edge: POSTED_IN
            events.append(self._make_edge_event(
                Edge(
                    source_id=user_id,
                    target_id=f"slack:channel:{ch}",
                    relation="POSTED_IN",
                    properties={"message": msg_id},
                ),
            ))

            # Edge: REPLIED_TO (thread)
            thread_ts = msg.get("thread_ts")
            if thread_ts and thread_ts != ts:
                parent_id = f"slack:msg:{ch}:{thread_ts}"
                events.append(self._make_edge_event(
                    Edge(source_id=msg_id, target_id=parent_id, relation="REPLIED_TO"),
                ))

            # Edges: REACTED_TO
            for reaction in msg.get("reactions", []):
                for reactor in reaction.get("users", []):
                    events.append(self._make_edge_event(
                        Edge(
                            source_id=f"slack:user:{reactor}",
                            target_id=msg_id,
                            relation="REACTED_TO",
                            properties={"emoji": reaction["name"]},
                        ),
                    ))

            # Edges: MENTIONED
            for mentioned in msg.get("mentions", []):
                events.append(self._make_edge_event(
                    Edge(
                        source_id=msg_id,
                        target_id=f"slack:user:{mentioned}",
                        relation="MENTIONED",
                    ),
                ))

        return events
