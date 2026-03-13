"""{{NAME}} connector — scaffold for a new Percept connector."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)


class {{CLASS_NAME}}Connector(BaseConnector):
    name = "{{NAME}}"
    version = "0.1.0"
    auth_type = "{{AUTH_TYPE}}"  # "oauth2", "api_key", "token", "none"
    description = "{{DESCRIPTION}}"

    def authenticate(self, credentials: dict) -> bool:
        if self._mock_mode:
            self._authenticated = True
            return True
        # TODO: implement authentication
        raise NotImplementedError

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        # TODO: verify connection works
        raise NotImplementedError

    def discover(self) -> list[EntitySchema]:
        return [
            # TODO: define entity types this connector produces
            # EntitySchema(
            #     entity_type=EntityType.DOCUMENT,
            #     name="MyEntity",
            #     description="Description",
            #     properties=["prop1", "prop2"],
            # ),
        ]

    def pull(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._pull_mock(since)
        return self._pull_live(since)

    def _pull_live(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        # TODO: implement live data pull
        raise NotImplementedError

    def _pull_mock(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        # TODO: return mock data for testing
        return []
