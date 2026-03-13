"""Linear connector — uses GraphQL API to pull issues, projects, and people into graph events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)
from percept.connectors.sdk.auth import AuthHelper


API_URL = "https://api.linear.app/graphql"

ISSUES_QUERY = """
{
  issues(first: 50, orderBy: updatedAt) {
    nodes {
      id
      title
      state { name }
      assignee { id name email }
      priority
      priorityLabel
      labels { nodes { name } }
      project { id name }
      createdAt
      updatedAt
      comments {
        nodes {
          id
          body
          user { id name email }
          createdAt
        }
      }
    }
  }
}
"""

PROJECTS_QUERY = """
{
  projects(first: 20) {
    nodes {
      id
      name
      state
      lead { id name email }
      targetDate
      createdAt
    }
  }
}
"""

CYCLES_QUERY = """
{
  cycles(first: 5, orderBy: updatedAt) {
    nodes {
      id
      name
      number
      startsAt
      endsAt
      progress
      completedAt
    }
  }
}
"""

USERS_QUERY = """
{
  users(first: 50) {
    nodes {
      id
      name
      email
    }
  }
}
"""

# Mock data for testing
MOCK_ISSUES = [
    {
        "id": "issue-001",
        "title": "Fix authentication flow for SSO",
        "state": {"name": "In Progress"},
        "assignee": {"id": "user-001", "name": "Alice Johnson", "email": "alice@example.com"},
        "priority": 2,
        "priorityLabel": "High",
        "labels": {"nodes": [{"name": "bug"}, {"name": "auth"}]},
        "project": {"id": "proj-001", "name": "Auth Revamp"},
        "createdAt": "2026-03-08T10:00:00Z",
        "updatedAt": "2026-03-11T14:30:00Z",
        "comments": {"nodes": [
            {
                "id": "comment-001",
                "body": "Reproduced on staging. The SAML callback URL is wrong.",
                "user": {"id": "user-002", "name": "Bob Smith", "email": "bob@example.com"},
                "createdAt": "2026-03-09T11:00:00Z",
            }
        ]},
    },
    {
        "id": "issue-002",
        "title": "Add dark mode support",
        "state": {"name": "Backlog"},
        "assignee": None,
        "priority": 4,
        "priorityLabel": "Low",
        "labels": {"nodes": [{"name": "enhancement"}]},
        "project": {"id": "proj-002", "name": "UI Polish"},
        "createdAt": "2026-03-05T09:00:00Z",
        "updatedAt": "2026-03-05T09:00:00Z",
        "comments": {"nodes": []},
    },
]

MOCK_PROJECTS = [
    {
        "id": "proj-001",
        "name": "Auth Revamp",
        "state": "started",
        "lead": {"id": "user-001", "name": "Alice Johnson", "email": "alice@example.com"},
        "targetDate": "2026-04-01",
        "createdAt": "2026-02-15T10:00:00Z",
    },
    {
        "id": "proj-002",
        "name": "UI Polish",
        "state": "planned",
        "lead": None,
        "targetDate": "2026-05-01",
        "createdAt": "2026-03-01T10:00:00Z",
    },
]


def _parse_dt(s: str) -> datetime:
    """Parse ISO datetime string from Linear."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class LinearConnector(BaseConnector):
    name = "linear"
    version = "0.1.0"
    auth_type = "api_key"
    description = "Pull issues, projects, and team from Linear via GraphQL API"

    CREDENTIALS_PATH = "~/.config/linear/credentials.json"

    def __init__(self, mock: bool = False):
        super().__init__(mock=mock)
        self._api_key: str | None = None

    def authenticate(self, credentials: dict) -> bool:
        if self._mock_mode:
            self._authenticated = True
            return True

        # Try credentials dict first, then file
        api_key = credentials.get("api_key")
        if not api_key:
            try:
                creds = AuthHelper.load_json_credentials(self.CREDENTIALS_PATH)
                api_key = creds.get("api_key") or creds.get("token")
            except FileNotFoundError:
                self._authenticated = False
                return False

        self._api_key = api_key
        self._authenticated = True
        return True

    def _graphql(self, query: str) -> dict:
        """Execute a GraphQL query against Linear API."""
        resp = requests.post(
            API_URL,
            json={"query": query},
            headers={
                "Authorization": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        try:
            data = self._graphql("{ viewer { id name } }")
            return "viewer" in data
        except Exception:
            return False

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.DOCUMENT,
                name="Issue",
                description="A Linear issue/ticket",
                properties=["state", "priority", "priority_label", "labels", "kind"],
            ),
            EntitySchema(
                entity_type=EntityType.PROJECT,
                name="Project",
                description="A Linear project",
                properties=["state", "target_date"],
            ),
            EntitySchema(
                entity_type=EntityType.PERSON,
                name="Person",
                description="A Linear team member",
                properties=["email", "name"],
            ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_data(MOCK_ISSUES, MOCK_PROJECTS, since)

        try:
            issues_data = self._graphql(ISSUES_QUERY)
            projects_data = self._graphql(PROJECTS_QUERY)

            issues = issues_data.get("issues", {}).get("nodes", [])
            projects = projects_data.get("projects", {}).get("nodes", [])

            return self._process_data(issues, projects, since)
        except Exception as e:
            print(f"[linear] Live pull failed ({e}), falling back to mock data")
            return self._process_data(MOCK_ISSUES, MOCK_PROJECTS, since)

    def _process_data(
        self,
        issues: list[dict],
        projects: list[dict],
        since: Optional[datetime] = None,
    ) -> list[GraphEvent]:
        events: list[GraphEvent] = []
        seen_people: set[str] = set()
        seen_projects: set[str] = set()

        # --- Process projects first (issues reference them) ---
        for proj in projects:
            proj_id = f"linear-project:{proj['id']}"
            if proj_id in seen_projects:
                continue
            seen_projects.add(proj_id)

            events.append(self._make_node_event(
                Node(
                    id=proj_id,
                    entity_type=EntityType.PROJECT,
                    name=proj["name"],
                    properties={
                        "state": proj.get("state", ""),
                        "target_date": proj.get("targetDate", ""),
                        "source_id": proj["id"],
                    },
                    created_at=_parse_dt(proj.get("createdAt", "")),
                ),
            ))

            # Project lead
            lead = proj.get("lead")
            if lead:
                person_id = f"person:{lead.get('email', lead['id'])}"
                if person_id not in seen_people:
                    seen_people.add(person_id)
                    events.append(self._make_node_event(
                        Node(
                            id=person_id,
                            entity_type=EntityType.PERSON,
                            name=lead["name"],
                            properties={"email": lead.get("email", "")},
                        ),
                    ))
                events.append(self._make_edge_event(
                    Edge(
                        source_id=person_id,
                        target_id=proj_id,
                        relation="LEADS",
                    ),
                ))

        # --- Process issues ---
        for issue in issues:
            updated = _parse_dt(issue.get("updatedAt", ""))
            if since and updated < since:
                continue

            issue_id = f"linear-issue:{issue['id']}"

            # Issue node
            labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
            events.append(self._make_node_event(
                Node(
                    id=issue_id,
                    entity_type=EntityType.DOCUMENT,
                    name=issue["title"],
                    properties={
                        "state": issue.get("state", {}).get("name", ""),
                        "priority": issue.get("priority", 0),
                        "priority_label": issue.get("priorityLabel", ""),
                        "labels": labels,
                        "kind": "ticket",
                        "source_id": issue["id"],
                    },
                    created_at=_parse_dt(issue.get("createdAt", "")),
                    updated_at=updated,
                ),
                raw=issue,
            ))

            # Assignee
            assignee = issue.get("assignee")
            if assignee:
                person_id = f"person:{assignee.get('email', assignee['id'])}"
                if person_id not in seen_people:
                    seen_people.add(person_id)
                    events.append(self._make_node_event(
                        Node(
                            id=person_id,
                            entity_type=EntityType.PERSON,
                            name=assignee["name"],
                            properties={"email": assignee.get("email", "")},
                        ),
                    ))

                # ASSIGNED_TO edge
                events.append(self._make_edge_event(
                    Edge(
                        source_id=person_id,
                        target_id=issue_id,
                        relation="ASSIGNED_TO",
                    ),
                ))

            # BELONGS_TO_PROJECT edge
            project_ref = issue.get("project")
            if project_ref:
                proj_node_id = f"linear-project:{project_ref['id']}"
                events.append(self._make_edge_event(
                    Edge(
                        source_id=issue_id,
                        target_id=proj_node_id,
                        relation="BELONGS_TO_PROJECT",
                    ),
                ))

            # LABELED_WITH edges
            for label_name in labels:
                label_id = f"linear-label:{label_name.lower().replace(' ', '-')}"
                # Create concept node for the label
                events.append(self._make_node_event(
                    Node(
                        id=label_id,
                        entity_type=EntityType.CONCEPT,
                        name=label_name,
                        properties={"kind": "label"},
                    ),
                ))
                events.append(self._make_edge_event(
                    Edge(
                        source_id=issue_id,
                        target_id=label_id,
                        relation="LABELED_WITH",
                    ),
                ))

            # Comments → COMMENTED_ON edges
            for comment in issue.get("comments", {}).get("nodes", []):
                commenter = comment.get("user")
                if commenter:
                    commenter_id = f"person:{commenter.get('email', commenter['id'])}"
                    if commenter_id not in seen_people:
                        seen_people.add(commenter_id)
                        events.append(self._make_node_event(
                            Node(
                                id=commenter_id,
                                entity_type=EntityType.PERSON,
                                name=commenter["name"],
                                properties={"email": commenter.get("email", "")},
                            ),
                        ))

                    events.append(self._make_edge_event(
                        Edge(
                            source_id=commenter_id,
                            target_id=issue_id,
                            relation="COMMENTED_ON",
                            properties={
                                "comment_id": comment["id"],
                                "snippet": comment.get("body", "")[:200],
                            },
                        ),
                    ))

        return events
