"""Oura Ring connector — pulls biometric data from Oura API v2 into graph events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from percept.connectors.sdk.base import (
    BaseConnector, GraphEvent, Node, Edge, EntitySchema, EntityType,
)


# Oura API v2 endpoints
OURA_BASE = "https://api.ouraring.com/v2/usercollection"
ENDPOINTS = {
    "sleep": f"{OURA_BASE}/daily_sleep",
    "readiness": f"{OURA_BASE}/daily_readiness",
    "activity": f"{OURA_BASE}/daily_activity",
    "heart_rate": f"{OURA_BASE}/heartrate",
}

CREDS_PATH = Path("~/.config/oura/credentials.json").expanduser()


def _load_token() -> str:
    """Load Oura personal access token from credentials file."""
    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"Oura credentials not found at {CREDS_PATH}. "
            "Create it with: {\"token\": \"YOUR_OURA_PAT\"}"
        )
    with open(CREDS_PATH) as f:
        data = json.load(f)
    token = data.get("token") or data.get("personal_access_token", "")
    if not token:
        raise ValueError("No 'token' or 'personal_access_token' field in Oura credentials file")
    return token


def _parse_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD into a timezone-aware datetime."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


class OuraConnector(BaseConnector):
    name = "oura"
    version = "0.1.0"
    auth_type = "api_key"
    description = "Pull sleep, readiness, activity, and heart rate data from Oura Ring API v2"

    # Baselines for anomaly detection (configurable per-user)
    DEFAULT_BASELINES = {
        "sleep_score": 89,
        "readiness_score": 78,
        "activity_score": 90,
        "resting_hr": 52,
    }

    # Mock data for testing
    MOCK_DATA = {
        "sleep": [{
            "id": "mock-sleep-001",
            "day": "2026-03-13",
            "score": 83,
            "contributors": {
                "deep_sleep": 54, "efficiency": 91, "latency": 88,
                "rem_sleep": 95, "restfulness": 70, "timing": 80,
                "total_sleep": 85,
            },
            "timestamp": "2026-03-13T06:30:00+00:00",
        }],
        "readiness": [{
            "id": "mock-readiness-001",
            "day": "2026-03-13",
            "score": 82,
            "contributors": {
                "activity_balance": 85, "body_temperature": 90,
                "hrv_balance": 70, "previous_day_activity": 95,
                "previous_night": 80, "recovery_index": 88,
                "resting_heart_rate": 92, "sleep_balance": 75,
            },
            "timestamp": "2026-03-13T06:30:00+00:00",
        }],
        "activity": [{
            "id": "mock-activity-001",
            "day": "2026-03-13",
            "score": 98,
            "active_calories": 450,
            "steps": 12500,
            "equivalent_walking_distance": 9800,
            "timestamp": "2026-03-13T23:59:00+00:00",
        }],
    }

    def __init__(
        self,
        mock: bool = False,
        lookback_days: int = 7,
        baselines: dict[str, float] | None = None,
    ):
        super().__init__(mock=mock)
        self.lookback_days = lookback_days
        self.baselines = baselines or self.DEFAULT_BASELINES
        self._token: str = ""

    def authenticate(self, credentials: dict) -> bool:
        """Authenticate with Oura API using personal access token."""
        if self._mock_mode:
            self._authenticated = True
            return True
        try:
            token = credentials.get("token") or _load_token()
            # Verify token with a lightweight call
            resp = requests.get(
                f"{OURA_BASE}/personal_info",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                self._token = token
                self._authenticated = True
                return True
            self._authenticated = False
            return False
        except Exception as e:
            self._authenticated = False
            return False

    def test_connection(self) -> bool:
        if self._mock_mode:
            return True
        if not self._token:
            try:
                self._token = _load_token()
            except Exception:
                return False
        resp = requests.get(
            f"{OURA_BASE}/personal_info",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10,
        )
        return resp.status_code == 200

    def discover(self) -> list[EntitySchema]:
        return [
            EntitySchema(
                entity_type=EntityType.EVENT,
                name="SleepSession",
                description="Daily sleep score and contributors",
                properties=["score", "deep_sleep", "rem_sleep", "efficiency",
                            "latency", "total_sleep", "restfulness", "timing"],
            ),
            EntitySchema(
                entity_type=EntityType.EVENT,
                name="ReadinessScore",
                description="Daily readiness score and contributors",
                properties=["score", "hrv_balance", "body_temperature",
                            "resting_heart_rate", "recovery_index",
                            "activity_balance", "sleep_balance"],
            ),
            EntitySchema(
                entity_type=EntityType.EVENT,
                name="ActivitySummary",
                description="Daily activity score, steps, and calories",
                properties=["score", "steps", "active_calories",
                            "equivalent_walking_distance"],
            ),
            EntitySchema(
                entity_type=EntityType.CONCEPT,
                name="HealthAnomaly",
                description="Detected deviation from baseline health metrics",
                properties=["metric", "value", "baseline", "deviation_pct",
                            "direction", "severity"],
            ),
        ]

    def pull(self, since: datetime | None = None) -> list[GraphEvent]:
        if self._mock_mode:
            return self._process_data(self.MOCK_DATA, since)
        try:
            data = self._fetch_all(since)
            return self._process_data(data, since)
        except Exception as e:
            print(f"[oura] Live pull failed ({e}), falling back to mock data")
            return self._process_data(self.MOCK_DATA, since)

    # --- Internal ---

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _fetch_endpoint(
        self, endpoint: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Fetch a single Oura API endpoint."""
        url = ENDPOINTS[endpoint]
        params = {"start_date": start_date, "end_date": end_date}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[oura] {endpoint} returned {resp.status_code}")
            return []
        return resp.json().get("data", [])

    def _fetch_all(self, since: datetime | None = None) -> dict[str, list[dict]]:
        """Fetch all endpoints for the lookback period."""
        if not self._token:
            self._token = _load_token()

        end = datetime.now(timezone.utc)
        start = since or (end - timedelta(days=self.lookback_days))
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        return {
            "sleep": self._fetch_endpoint("sleep", start_str, end_str),
            "readiness": self._fetch_endpoint("readiness", start_str, end_str),
            "activity": self._fetch_endpoint("activity", start_str, end_str),
        }

    def _process_data(
        self, data: dict[str, list[dict]], since: datetime | None = None
    ) -> list[GraphEvent]:
        """Convert Oura API responses into GraphEvents."""
        events: list[GraphEvent] = []

        # Create a persistent user node
        user_node_id = "person:oura_user"
        events.append(self._make_node_event(
            Node(
                id=user_node_id,
                entity_type=EntityType.PERSON,
                name="Oura User",
                properties={"source": "oura_ring"},
            ),
        ))

        # --- Sleep events ---
        for day in data.get("sleep", []):
            day_str = day.get("day", "")
            score = day.get("score")
            if not day_str or score is None:
                continue

            node_id = f"oura:sleep:{day_str}"
            contributors = day.get("contributors", {})

            sleep_node = Node(
                id=node_id,
                entity_type=EntityType.EVENT,
                name=f"Sleep — {day_str}",
                properties={
                    "kind": "sleep_session",
                    "day": day_str,
                    "score": score,
                    "deep_sleep": contributors.get("deep_sleep"),
                    "rem_sleep": contributors.get("rem_sleep"),
                    "efficiency": contributors.get("efficiency"),
                    "latency": contributors.get("latency"),
                    "total_sleep": contributors.get("total_sleep"),
                    "restfulness": contributors.get("restfulness"),
                    "timing": contributors.get("timing"),
                },
                created_at=_parse_date(day_str),
            )
            events.append(self._make_node_event(sleep_node, raw=day))

            # Edge: user → sleep
            events.append(self._make_edge_event(
                Edge(
                    source_id=user_node_id,
                    target_id=node_id,
                    relation="RECORDED",
                    properties={"metric_type": "sleep"},
                ),
            ))

            # Anomaly detection
            events.extend(self._detect_anomalies(
                "sleep_score", score, day_str, node_id
            ))

        # --- Readiness events ---
        for day in data.get("readiness", []):
            day_str = day.get("day", "")
            score = day.get("score")
            if not day_str or score is None:
                continue

            node_id = f"oura:readiness:{day_str}"
            contributors = day.get("contributors", {})

            readiness_node = Node(
                id=node_id,
                entity_type=EntityType.EVENT,
                name=f"Readiness — {day_str}",
                properties={
                    "kind": "readiness_score",
                    "day": day_str,
                    "score": score,
                    "hrv_balance": contributors.get("hrv_balance"),
                    "body_temperature": contributors.get("body_temperature"),
                    "resting_heart_rate": contributors.get("resting_heart_rate"),
                    "recovery_index": contributors.get("recovery_index"),
                    "activity_balance": contributors.get("activity_balance"),
                    "sleep_balance": contributors.get("sleep_balance"),
                    "previous_night": contributors.get("previous_night"),
                    "previous_day_activity": contributors.get("previous_day_activity"),
                },
                created_at=_parse_date(day_str),
            )
            events.append(self._make_node_event(readiness_node, raw=day))

            events.append(self._make_edge_event(
                Edge(
                    source_id=user_node_id,
                    target_id=node_id,
                    relation="RECORDED",
                    properties={"metric_type": "readiness"},
                ),
            ))

            events.extend(self._detect_anomalies(
                "readiness_score", score, day_str, node_id
            ))

        # --- Activity events ---
        for day in data.get("activity", []):
            day_str = day.get("day", "")
            score = day.get("score")
            if not day_str or score is None:
                continue

            node_id = f"oura:activity:{day_str}"

            activity_node = Node(
                id=node_id,
                entity_type=EntityType.EVENT,
                name=f"Activity — {day_str}",
                properties={
                    "kind": "activity_summary",
                    "day": day_str,
                    "score": score,
                    "steps": day.get("steps"),
                    "active_calories": day.get("active_calories"),
                    "equivalent_walking_distance": day.get("equivalent_walking_distance"),
                },
                created_at=_parse_date(day_str),
            )
            events.append(self._make_node_event(activity_node, raw=day))

            events.append(self._make_edge_event(
                Edge(
                    source_id=user_node_id,
                    target_id=node_id,
                    relation="RECORDED",
                    properties={"metric_type": "activity"},
                ),
            ))

            events.extend(self._detect_anomalies(
                "activity_score", score, day_str, node_id
            ))

        return events

    def _detect_anomalies(
        self,
        metric: str,
        value: float,
        day_str: str,
        source_node_id: str,
    ) -> list[GraphEvent]:
        """Detect significant deviations from baseline and emit anomaly nodes."""
        baseline = self.baselines.get(metric)
        if baseline is None or value is None:
            return []

        deviation_pct = ((value - baseline) / baseline) * 100
        abs_dev = abs(deviation_pct)

        # Only flag deviations > 10%
        if abs_dev < 10:
            return []

        severity = "mild"
        if abs_dev > 25:
            severity = "severe"
        elif abs_dev > 15:
            severity = "moderate"

        direction = "above" if value > baseline else "below"
        anomaly_id = f"oura:anomaly:{metric}:{day_str}"

        anomaly_node = Node(
            id=anomaly_id,
            entity_type=EntityType.CONCEPT,
            name=f"Health Anomaly: {metric} {direction} baseline",
            properties={
                "kind": "health_anomaly",
                "metric": metric,
                "value": value,
                "baseline": baseline,
                "deviation_pct": round(deviation_pct, 1),
                "direction": direction,
                "severity": severity,
                "day": day_str,
            },
            created_at=_parse_date(day_str),
        )

        events = [self._make_node_event(anomaly_node)]

        # Edge: anomaly is derived from the source metric node
        events.append(self._make_edge_event(
            Edge(
                source_id=source_node_id,
                target_id=anomaly_id,
                relation="TRIGGERED",
                properties={"deviation_pct": round(deviation_pct, 1)},
            ),
        ))

        return events
