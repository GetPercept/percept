"""Shared pytest fixtures for Percept tests."""

import json
import os
import sys
import time
import pytest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def db():
    """In-memory PerceptDB instance."""
    from src.database import PerceptDB
    instance = PerceptDB(db_path=":memory:")
    yield instance
    instance.close()


@pytest.fixture
def sample_segments():
    """Sample transcript segments as dicts."""
    now = time.time()
    return [
        {"text": "Hey how's it going?", "speaker": "SPEAKER_00", "is_user": True, "start": 0.0, "end": 2.0},
        {"text": "Pretty good, working on the project.", "speaker": "SPEAKER_01", "is_user": False, "start": 2.5, "end": 5.0},
        {"text": "Great, let's schedule a meeting with John.", "speaker": "SPEAKER_00", "is_user": True, "start": 5.5, "end": 8.0},
    ]


@pytest.fixture
def sample_conversation_data():
    """Sample conversation dict for DB insertion."""
    now = time.time()
    return {
        "id": "2026-02-21_11-00",
        "timestamp": now,
        "date": "2026-02-21",
        "duration_seconds": 120.0,
        "segment_count": 10,
        "word_count": 200,
        "speakers": ["David", "SPEAKER_01"],
        "topics": ["project", "meeting"],
        "transcript": "[David] Hey\n[SPEAKER_01] Hello",
        "summary": "Brief chat about project.",
    }


@pytest.fixture
def populated_db(db, sample_conversation_data):
    """DB with one conversation, speaker, contact, and action."""
    db.save_conversation(**sample_conversation_data)
    db.update_speaker("SPEAKER_00", name="David", relationship="owner", words_delta=100, segments_delta=5)
    db.update_speaker("SPEAKER_01", name="Bob", words_delta=50, segments_delta=3)
    db.save_contact("c1", "Alice", email="alice@example.com", phone="+15551234567")
    db.save_contact("c2", "Bob Smith", email="bob@example.com")
    db.save_action(conversation_id=sample_conversation_data["id"], intent="email", params={"to": "alice@example.com"}, raw_text="email alice")
    return db


@pytest.fixture
def entity_extractor(db):
    """EntityExtractor with DB but no LLM."""
    from src.entity_extractor import EntityExtractor
    return EntityExtractor(db=db, llm_enabled=False)


@pytest.fixture
def context_engine(db):
    """ContextEngine instance."""
    from src.context_engine import ContextEngine
    return ContextEngine(db=db, vector_store=None)
