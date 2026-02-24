"""Tests for the Percept MCP server."""

import json
import pytest

# Ensure project root is importable
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_server_initializes():
    """Test that the MCP server object creates successfully."""
    from src.mcp_server import mcp
    assert mcp is not None
    assert mcp.name == "percept"


def test_tools_registered():
    """Test that all expected tools are registered."""
    from src.mcp_server import mcp
    # Access internal tool manager
    tool_manager = mcp._tool_manager
    tool_names = set(tool_manager._tools.keys())
    expected = {
        "percept_search",
        "percept_transcripts",
        "percept_actions",
        "percept_speakers",
        "percept_status",
        "percept_security_log",
        "percept_conversations",
        "percept_listen",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


def test_resources_registered():
    """Test that MCP resources are registered."""
    from src.mcp_server import mcp
    resource_manager = mcp._resource_manager
    # Resources are stored by URI
    resource_uris = set(resource_manager._resources.keys())
    assert "percept://status" in resource_uris or any("status" in str(u) for u in resource_uris)
    assert "percept://speakers" in resource_uris or any("speakers" in str(u) for u in resource_uris)


def test_percept_status_returns_json():
    """Test that percept_status returns valid JSON."""
    from src.mcp_server import percept_status
    result = percept_status()
    data = json.loads(result)
    assert "server" in data
    assert "today" in data


def test_percept_listen_no_file():
    """Test percept_listen when no live file exists."""
    from src.mcp_server import percept_listen
    result = percept_listen()
    data = json.loads(result)
    assert data["status"] in ("no_data", "active", "stale")


def test_percept_transcripts_returns_json():
    """Test percept_transcripts returns valid JSON."""
    from src.mcp_server import percept_transcripts
    result = percept_transcripts(today_only=False, limit=5)
    data = json.loads(result)
    assert "count" in data
    assert "transcripts" in data


def test_percept_actions_returns_json():
    """Test percept_actions returns valid JSON."""
    from src.mcp_server import percept_actions
    result = percept_actions(limit=5)
    data = json.loads(result)
    assert "count" in data
    assert "actions" in data


def test_percept_speakers_returns_json():
    """Test percept_speakers returns valid JSON."""
    from src.mcp_server import percept_speakers
    result = percept_speakers()
    data = json.loads(result)
    assert "count" in data
    assert "speakers" in data


def test_percept_security_log_returns_json():
    """Test percept_security_log returns valid JSON."""
    from src.mcp_server import percept_security_log
    result = percept_security_log(limit=5)
    data = json.loads(result)
    assert "count" in data
    assert "events" in data


def test_percept_conversations_returns_json():
    """Test percept_conversations returns valid JSON."""
    from src.mcp_server import percept_conversations
    result = percept_conversations(limit=5)
    data = json.loads(result)
    assert "count" in data
    assert "conversations" in data
