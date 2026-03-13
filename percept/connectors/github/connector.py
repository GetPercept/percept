"""GitHub connector — uses gh CLI to pull PRs, issues, and repos into graph events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)
from percept.connectors.sdk.auth import AuthHelper


# gh CLI JSON output formats (flat arrays, NOT nested {nodes:[]}):
#
# gh pr list --json ... returns:
#   [{"number":42, "title":"...", "state":"OPEN", "author":{"login":"..."}, "createdAt":"...",
#     "url":"...", "reviews":[{"author":{"login":"..."},"state":"APPROVED"}],
#     "reviewRequests":[{"login":"..."}]}]
#
# gh issue list --json ... returns:
#   [{"number":1, "title":"...", "state":"OPEN", "author":{"login":"..."},
#     "createdAt":"...", "url":"...", "assignees":[{"login":"..."}],
#     "labels":[{"name":"bug"}]}]


def _extract_login(author_field) -> str:
    """Extract login from author field — handles both dict and nested formats."""
    if isinstance(author_field, dict):
        return author_field.get("login", "unknown")
    return str(author_field) if author_field else "unknown"


class GitHubConnector(BaseConnector):
    name = "github"
    version = "0.2.0"
    auth_type = "token"
    description = "Pull PRs, issues, and repos from GitHub via gh CLI"

    GH_CLI = "/opt/homebrew/bin/gh"

    MOCK_PRS = [
        {
            "number": 142,
            "title": "feat: add FHIR R4 patient endpoint",
            "state": "OPEN",
            "author": {"login": "ilya-dev"},
            "createdAt": "2026-03-10T10:00:00Z",
            "url": "https://github.com/vectorcare/platform/pull/142",
            "repository": {"nameWithOwner": "vectorcare/platform"},
            "reviews": [{"author": {"login": "butler-ai"}, "state": "APPROVED"}],
            "reviewRequests": [{"login": "butler-ai"}],
        },
        {
            "number": 143,
            "title": "fix: transport scheduling timezone bug",
            "state": "MERGED",
            "author": {"login": "carol-chen"},
            "createdAt": "2026-03-09T15:30:00Z",
            "url": "https://github.com/vectorcare/platform/pull/143",
            "repository": {"nameWithOwner": "vectorcare/platform"},
            "reviews": [{"author": {"login": "ilya-dev"}, "state": "APPROVED"}],
            "reviewRequests": [],
        },
    ]

    MOCK_ISSUES = [
        {
            "number": 301,
            "title": "DME tracking dashboard crashes on Firefox",
            "state": "OPEN",
            "author": {"login": "carol-chen"},
            "createdAt": "2026-03-11T08:00:00Z",
            "url": "https://github.com/vectorcare/platform/issues/301",
            "repository": {"nameWithOwner": "vectorcare/platform"},
            "assignees": [{"login": "ilya-dev"}],
            "labels": [{"name": "bug"}],
        },
    ]

    def __init__(self, repos: list[str] | None = None, mock: bool = False, max_repos: int = 10):
        super().__init__(mock=mock)
        self.repos = repos or []
        self.max_repos = max_repos

    def authenticate(self, credentials: dict) -> bool:
        if self._mock_mode:
            self._authenticated = True
            return True
        token = AuthHelper.get_gh_token()
        if token:
            self._authenticated = True
            return True
        self._authenticated = False
        return False

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        ok, output = AuthHelper.run_cli([self.GH_CLI, "auth", "status"])
        return ok

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.PERSON,
                name="Contributor",
                description="GitHub user",
                properties=["login", "url"],
            ),
            EntitySchema(
                entity_type=EntityType.PROJECT,
                name="Repository",
                description="GitHub repository",
                properties=["full_name", "url"],
            ),
            EntitySchema(
                entity_type=EntityType.DOCUMENT,
                name="Pull Request",
                description="A pull request",
                properties=["number", "title", "state", "url"],
            ),
            EntitySchema(
                entity_type=EntityType.DOCUMENT,
                name="Issue",
                description="A GitHub issue",
                properties=["number", "title", "state", "url", "labels"],
            ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_prs(self.MOCK_PRS, since) + self._process_issues(self.MOCK_ISSUES, since)
        try:
            return self._pull_live(since)
        except Exception as e:
            print(f"[github] Live pull failed ({e}), falling back to mock data")
            return self._process_prs(self.MOCK_PRS, since) + self._process_issues(self.MOCK_ISSUES, since)

    def _pull_live(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        events: list[GraphEvent] = []

        # Determine repos to query
        repos = self.repos
        if not repos:
            ok, output = AuthHelper.run_cli([
                self.GH_CLI, "repo", "list", "--json", "nameWithOwner",
                "--limit", str(self.max_repos),
            ])
            if ok:
                try:
                    repos = [r["nameWithOwner"] for r in json.loads(output)]
                except (json.JSONDecodeError, KeyError):
                    repos = []

        for repo in repos:
            # Pull PRs
            ok, output = AuthHelper.run_cli([
                self.GH_CLI, "pr", "list", "-R", repo, "--state", "all",
                "--json", "number,title,state,author,createdAt,url,reviews,reviewRequests",
                "--limit", "20",
            ], timeout=30)
            if ok:
                try:
                    prs = json.loads(output)
                    for pr in prs:
                        pr.setdefault("repository", {"nameWithOwner": repo})
                    events.extend(self._process_prs(prs, since))
                except json.JSONDecodeError:
                    pass

            # Pull issues (some repos have issues disabled — don't fail)
            ok, output = AuthHelper.run_cli([
                self.GH_CLI, "issue", "list", "-R", repo, "--state", "all",
                "--json", "number,title,state,author,createdAt,url,assignees,labels",
                "--limit", "20",
            ], timeout=30)
            if ok:
                try:
                    issues = json.loads(output)
                    for issue in issues:
                        issue.setdefault("repository", {"nameWithOwner": repo})
                    events.extend(self._process_issues(issues, since))
                except json.JSONDecodeError:
                    pass

        return events

    def _process_prs(self, prs: list[dict], since: Optional[datetime] = None) -> list[GraphEvent]:
        events: list[GraphEvent] = []
        seen_people: set[str] = set()
        seen_repos: set[str] = set()

        for pr in prs:
            created = pr.get("createdAt", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if since and dt < since:
                        continue
                except ValueError:
                    dt = datetime.now(timezone.utc)
            else:
                dt = datetime.now(timezone.utc)

            repo_name = pr.get("repository", {}).get("nameWithOwner", "unknown/unknown")
            author = _extract_login(pr.get("author"))
            pr_id = f"pr:{repo_name}#{pr['number']}"
            person_id = f"person:gh:{author}"
            repo_id = f"repo:{repo_name}"

            # Repo node
            if repo_id not in seen_repos:
                seen_repos.add(repo_id)
                events.append(self._make_node_event(
                    Node(id=repo_id, entity_type=EntityType.PROJECT, name=repo_name,
                         properties={"full_name": repo_name}),
                ))

            # Author node
            if person_id not in seen_people:
                seen_people.add(person_id)
                events.append(self._make_node_event(
                    Node(id=person_id, entity_type=EntityType.PERSON, name=author,
                         properties={"login": author, "platform": "github"}),
                ))

            # PR node
            state = pr.get("state", "")
            events.append(self._make_node_event(
                Node(
                    id=pr_id, entity_type=EntityType.DOCUMENT,
                    name=pr.get("title", ""),
                    properties={
                        "number": pr["number"],
                        "state": state,
                        "url": pr.get("url", ""),
                        "kind": "pull_request",
                        "created_at": created,
                    },
                    created_at=dt,
                ),
                raw=pr,
            ))

            # Edge: AUTHORED
            events.append(self._make_edge_event(
                Edge(source_id=person_id, target_id=pr_id, relation="AUTHORED"),
            ))

            # Edge: belongs to repo
            events.append(self._make_edge_event(
                Edge(source_id=pr_id, target_id=repo_id, relation="PART_OF"),
            ))

            # Reviewer edges — gh returns flat array (not nested {nodes:[...]})
            reviews = pr.get("reviews", [])
            # Handle both formats: flat array or {nodes: [...]}
            if isinstance(reviews, dict):
                reviews = reviews.get("nodes", [])
            for review in reviews:
                reviewer = _extract_login(review.get("author"))
                if reviewer and reviewer != "unknown":
                    reviewer_id = f"person:gh:{reviewer}"
                    if reviewer_id not in seen_people:
                        seen_people.add(reviewer_id)
                        events.append(self._make_node_event(
                            Node(id=reviewer_id, entity_type=EntityType.PERSON, name=reviewer,
                                 properties={"login": reviewer, "platform": "github"}),
                        ))
                    events.append(self._make_edge_event(
                        Edge(source_id=reviewer_id, target_id=pr_id, relation="REVIEWED",
                             properties={"state": review.get("state", "")}),
                    ))

        return events

    def _process_issues(self, issues: list[dict], since: Optional[datetime] = None) -> list[GraphEvent]:
        events: list[GraphEvent] = []
        seen_people: set[str] = set()

        for issue in issues:
            created = issue.get("createdAt", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if since and dt < since:
                        continue
                except ValueError:
                    dt = datetime.now(timezone.utc)
            else:
                dt = datetime.now(timezone.utc)

            repo_name = issue.get("repository", {}).get("nameWithOwner", "unknown/unknown")
            author = _extract_login(issue.get("author"))
            issue_id = f"issue:{repo_name}#{issue['number']}"
            person_id = f"person:gh:{author}"

            # Author
            if person_id not in seen_people:
                seen_people.add(person_id)
                events.append(self._make_node_event(
                    Node(id=person_id, entity_type=EntityType.PERSON, name=author,
                         properties={"login": author, "platform": "github"}),
                ))

            # Labels — handle both flat array and nested {nodes:[...]}
            labels_raw = issue.get("labels", [])
            if isinstance(labels_raw, dict):
                labels_raw = labels_raw.get("nodes", [])
            labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in labels_raw]

            # Issue node
            events.append(self._make_node_event(
                Node(
                    id=issue_id, entity_type=EntityType.DOCUMENT,
                    name=issue.get("title", ""),
                    properties={
                        "number": issue["number"],
                        "state": issue.get("state", ""),
                        "url": issue.get("url", ""),
                        "labels": labels,
                        "kind": "issue",
                        "created_at": created,
                    },
                    created_at=dt,
                ),
                raw=issue,
            ))

            # AUTHORED edge
            events.append(self._make_edge_event(
                Edge(source_id=person_id, target_id=issue_id, relation="AUTHORED"),
            ))

            # ASSIGNED_TO edges — handle both flat array and nested {nodes:[...]}
            assignees_raw = issue.get("assignees", [])
            if isinstance(assignees_raw, dict):
                assignees_raw = assignees_raw.get("nodes", [])
            for assignee in assignees_raw:
                a_login = _extract_login(assignee)
                if a_login and a_login != "unknown":
                    a_id = f"person:gh:{a_login}"
                    if a_id not in seen_people:
                        seen_people.add(a_id)
                        events.append(self._make_node_event(
                            Node(id=a_id, entity_type=EntityType.PERSON, name=a_login,
                                 properties={"login": a_login, "platform": "github"}),
                        ))
                    events.append(self._make_edge_event(
                        Edge(source_id=a_id, target_id=issue_id, relation="ASSIGNED_TO"),
                    ))

        return events
