"""Tests for ContextEngine — context packet building, entity resolution."""

import pytest
from src.context_engine import ContextEngine


class TestContextPacket:
    def test_basic_packet(self, populated_db):
        engine = ContextEngine(db=populated_db, vector_store=None)
        cid = "2026-02-21_11-00"
        packet = engine.get_context_packet(cid, "email Alice about the meeting")
        assert "conversation" in packet
        assert "command" in packet
        assert "recent_context" in packet
        assert packet["conversation"]["id"] == cid

    def test_nonexistent_conversation(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        packet = engine.get_context_packet("nonexistent", "hello")
        assert packet["conversation"]["id"] == "nonexistent"
        assert packet["conversation"]["duration_minutes"] == 0

    def test_command_intent_detection(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        packet = engine.get_context_packet("test", "send an email to Bob")
        assert packet["command"]["intent"] == "email"

    def test_command_intent_search(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        packet = engine.get_context_packet("test", "search for restaurants")
        assert packet["command"]["intent"] == "search"

    def test_unknown_intent(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        packet = engine.get_context_packet("test", "the weather is nice")
        assert packet["command"]["intent"] == "unknown"


class TestRecentContext:
    def test_get_recent(self, populated_db):
        engine = ContextEngine(db=populated_db, vector_store=None)
        snippets = engine.get_recent_context(minutes=60)
        assert isinstance(snippets, list)

    def test_empty_db(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        snippets = engine.get_recent_context(minutes=60)
        assert snippets == []


class TestEntityResolution:
    def test_resolve_known_contact(self, populated_db):
        engine = ContextEngine(db=populated_db, vector_store=None)
        result = engine.resolve_entity("Alice")
        assert result["surface_form"] == "Alice"
        assert result["resolved_name"] == "Alice"

    def test_resolve_unknown(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        result = engine.resolve_entity("Totally Unknown Person")
        assert result["resolution"] in ("unresolved", "needs_human")


class TestBasicIntentDetection:
    def test_all_intents(self, db):
        engine = ContextEngine(db=db, vector_store=None)
        cases = {
            "email Bob": "email",
            "text mom": "text",
            "remind me": "reminder",
            "search for X": "search",
            "schedule meeting": "calendar",
            "note this": "note",
            "order pizza": "order",
            "nice day": "unknown",
        }
        for text, expected in cases.items():
            assert engine._detect_basic_intent(text) == expected
