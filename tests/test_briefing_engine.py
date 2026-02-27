"""Tests for the Percept briefing engine."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Ensure project root is importable
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_db():
    """Mock database for testing."""
    db = Mock()
    db.search_utterances.return_value = [
        {
            "text": "Rob mentioned the FHIR integration deadline",
            "conversation_id": "conv1",
            "started_at": "2026-02-25T10:30:00"
        }
    ]
    db.get_relationships.return_value = [
        {
            "source_id": "rob_martinez",
            "target_id": "vectorcare_team", 
            "relation_type": "team_member"
        }
    ]
    db.get_commitments.return_value = [
        {
            "text": "I'll send the updated API docs by Friday",
            "assignee": "Rob Martinez",
            "due_date": "2026-02-24",
            "status": "overdue"
        }
    ]
    db.get_entity_mentions.return_value = [
        {"entity_name": "FHIR"},
        {"entity_name": "API"}
    ]
    db.get_conversations.return_value = [
        {
            "id": "conv1",
            "date": "2026-02-25",
            "summary": "Discussed FHIR integration progress and API documentation",
            "speakers": "Rob Martinez, David Emanuel"
        }
    ]
    return db


@pytest.fixture
def mock_vector_store():
    """Mock vector store for testing."""
    vs = Mock()
    vs.hybrid_search.return_value = [
        {
            "text": "Rob mentioned the FHIR integration deadline",
            "conversation_id": "conv1",
            "started_at": "2026-02-25T10:30:00"
        }
    ]
    return vs


def test_briefing_engine_initializes(mock_db, mock_vector_store):
    """Test that BriefingEngine initializes correctly."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine(db=mock_db, vector_store=mock_vector_store)
    assert engine.db is mock_db
    assert engine.vector_store is mock_vector_store


def test_briefing_for_person_basic(mock_db, mock_vector_store):
    """Test basic person briefing generation."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine(db=mock_db, vector_store=mock_vector_store)
    briefing = engine.briefing_for_person("Rob Martinez")
    
    assert briefing["name"] == "Rob Martinez"
    assert "last_interaction" in briefing
    assert "recent_topics" in briefing
    assert "open_commitments" in briefing
    assert "conversation_count" in briefing
    
    # Verify mock calls
    mock_vector_store.hybrid_search.assert_called_once_with("Rob Martinez", limit=20)


def test_briefing_for_person_no_data():
    """Test person briefing when no data is available."""
    from src.briefing_engine import BriefingEngine
    
    # Create empty mocks
    empty_db = Mock()
    empty_db.search_utterances.return_value = []
    empty_db.get_relationships.return_value = []
    empty_db.get_commitments.return_value = []
    empty_db.get_entity_mentions.return_value = []
    empty_db.get_conversations.return_value = []
    
    empty_vs = Mock()
    empty_vs.hybrid_search.return_value = []
    
    engine = BriefingEngine(db=empty_db, vector_store=empty_vs)
    briefing = engine.briefing_for_person("Unknown Person")
    
    assert briefing["name"] == "Unknown Person"
    assert briefing["last_interaction"] is None
    assert briefing["recent_topics"] == []
    assert briefing["open_commitments"] == []
    assert briefing["conversation_count"] == 0


@patch('subprocess.run')
def test_get_upcoming_meetings_success(mock_subprocess):
    """Test successful calendar integration."""
    from src.briefing_engine import BriefingEngine
    
    # Mock successful gog calendar response
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout=json.dumps([
            {
                "id": "meeting1",
                "summary": "VectorCare Standup",
                "start": {"dateTime": "2026-02-27T11:30:00"},
                "end": {"dateTime": "2026-02-27T12:00:00"},
                "attendees": [
                    {"email": "rob@vectorcare.com", "displayName": "Rob Martinez"},
                    {"email": "david@vectorcare.com", "displayName": "David Emanuel"}
                ]
            }
        ])
    )
    
    engine = BriefingEngine()
    meetings = engine._get_upcoming_meetings(60)
    
    assert len(meetings) == 1
    assert meetings[0]["title"] == "VectorCare Standup"
    assert len(meetings[0]["attendees"]) == 2
    assert meetings[0]["attendees"][0]["name"] == "Rob Martinez"


@patch('subprocess.run')
def test_get_upcoming_meetings_no_gog(mock_subprocess):
    """Test graceful degradation when gog CLI not available."""
    from src.briefing_engine import BriefingEngine
    
    # Mock gog not found
    mock_subprocess.side_effect = FileNotFoundError()
    
    engine = BriefingEngine()
    meetings = engine._get_upcoming_meetings(60)
    
    assert meetings == []


@patch('subprocess.run')
def test_generate_briefing_no_meetings(mock_subprocess):
    """Test briefing generation when no upcoming meetings."""
    from src.briefing_engine import BriefingEngine
    
    # Mock empty calendar response
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout="[]"
    )
    
    engine = BriefingEngine()
    briefing = engine.generate_briefing()
    
    assert briefing["status"] == "no_upcoming_meetings"
    assert briefing["meetings"] == []


@patch('subprocess.run')
def test_generate_briefing_with_meetings(mock_subprocess, mock_db, mock_vector_store):
    """Test full briefing generation with meetings."""
    from src.briefing_engine import BriefingEngine
    
    # Mock calendar response
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout=json.dumps([
            {
                "id": "meeting1",
                "summary": "Team Meeting",
                "start": {"dateTime": "2026-02-27T14:00:00"},
                "attendees": [
                    {"email": "rob@company.com", "displayName": "Rob Martinez"}
                ]
            }
        ])
    )
    
    engine = BriefingEngine(db=mock_db, vector_store=mock_vector_store)
    briefing = engine.generate_briefing()
    
    assert briefing["status"] == "success"
    assert len(briefing["meetings"]) == 1
    assert len(briefing["meetings"][0]["attendees"]) == 1
    assert briefing["meetings"][0]["attendees"][0]["name"] == "Rob Martinez"


def test_format_briefing_markdown_no_meetings():
    """Test markdown formatting for no meetings."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine()
    data = {"status": "no_upcoming_meetings", "meetings": []}
    markdown = engine.format_briefing_markdown(data)
    
    assert "No Upcoming Meetings" in markdown
    assert "No meetings found" in markdown


def test_format_briefing_markdown_with_meetings():
    """Test markdown formatting with meeting data."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine()
    data = {
        "status": "success",
        "meetings": [
            {
                "meeting": {
                    "title": "Team Standup",
                    "start_time": "2026-02-27T11:30:00"
                },
                "attendees": [
                    {
                        "name": "Rob Martinez",
                        "last_interaction": "2026-02-25",
                        "recent_topics": ["FHIR", "API"],
                        "open_commitments": [
                            {
                                "text": "Send API docs",
                                "due_date": "2026-02-24",
                                "status": "overdue"
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    markdown = engine.format_briefing_markdown(data)
    
    assert "Team Standup" in markdown
    assert "Rob Martinez" in markdown
    assert "Last spoke:" in markdown
    assert "Recent topics:" in markdown
    assert "Open commitments:" in markdown
    assert "OVERDUE" in markdown


def test_mcp_tool_registration():
    """Test that briefing tool is registered with MCP server."""
    from src.mcp_server import mcp
    
    # Access internal tool manager
    tool_manager = mcp._tool_manager
    tool_names = set(tool_manager._tools.keys())
    
    assert "get_briefing" in tool_names


@patch('src.briefing_engine.BriefingEngine')
def test_mcp_get_briefing_tool(mock_engine_class):
    """Test the MCP get_briefing tool."""
    from src.mcp_server import get_briefing
    
    # Mock the engine
    mock_engine = Mock()
    mock_engine.briefing_for_person.return_value = {"name": "Test Person"}
    mock_engine_class.return_value = mock_engine
    
    # Test person-specific briefing
    result = get_briefing(person="Test Person")
    data = json.loads(result)
    
    assert data["name"] == "Test Person"
    mock_engine.briefing_for_person.assert_called_once_with("Test Person")


def test_last_interaction_date_parsing():
    """Test last interaction date parsing logic."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine()
    
    # Test with timestamp
    conversations = [{"started_at": 1709025600}]  # Feb 27, 2024
    date = engine._get_last_interaction_date(conversations)
    assert date == "2024-02-27"
    
    # Test with ISO string
    conversations = [{"started_at": "2026-02-27T10:30:00"}]
    date = engine._get_last_interaction_date(conversations)
    assert date == "2026-02-27"
    
    # Test with no conversations
    date = engine._get_last_interaction_date([])
    assert date is None


def test_extract_recent_topics():
    """Test topic extraction from conversations."""
    from src.briefing_engine import BriefingEngine
    
    engine = BriefingEngine()
    
    conversations = [
        {
            "highlighted": "discussed fhir integration and api documentation",
            "topics": "FHIR, API, Documentation"
        },
        {
            "text": "talked about budget concerns and q2 roadmap",
            "topics": ["Budget", "Roadmap"]
        }
    ]
    
    topics = engine._extract_recent_topics(conversations)
    
    assert len(topics) > 0
    # Should include topics from both text and topics field
    assert any("fhir" in topic.lower() for topic in topics)