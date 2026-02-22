"""Tests for PerceptDB — all CRUD, FTS, purge, settings, relationships."""

import time
import json
import pytest
from src.database import PerceptDB


class TestSettings:
    def test_default_settings_loaded(self, db):
        val = db.get_setting("wake_words")
        assert val == '["hey jarvis"]'

    def test_set_and_get_setting(self, db):
        db.set_setting("custom_key", "custom_value")
        assert db.get_setting("custom_key") == "custom_value"

    def test_get_setting_default(self, db):
        assert db.get_setting("nonexistent", "fallback") == "fallback"

    def test_get_all_settings(self, db):
        settings = db.get_all_settings()
        assert "wake_words" in settings
        assert "silence_timeout" in settings

    def test_set_overwrites(self, db):
        db.set_setting("silence_timeout", "10")
        assert db.get_setting("silence_timeout") == "10"


class TestConversations:
    def test_save_and_get(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        conv = db.get_conversation(sample_conversation_data["id"])
        assert conv is not None
        assert conv["word_count"] == 200
        assert conv["speakers"] == ["David", "SPEAKER_01"]

    def test_upsert(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        db.save_conversation(id=sample_conversation_data["id"], timestamp=sample_conversation_data["timestamp"],
                             date=sample_conversation_data["date"], word_count=300, summary=None)
        conv = db.get_conversation(sample_conversation_data["id"])
        assert conv["word_count"] == 300
        # summary should be preserved via COALESCE
        assert conv["summary"] == "Brief chat about project."

    def test_list_conversations(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        convs = db.get_conversations()
        assert len(convs) == 1

    def test_filter_by_date(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        assert len(db.get_conversations(date="2026-02-21")) == 1
        assert len(db.get_conversations(date="2025-01-01")) == 0

    def test_search_conversations(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        assert len(db.get_conversations(search="project")) == 1
        assert len(db.get_conversations(search="nonexistent_xyz")) == 0

    def test_get_nonexistent(self, db):
        assert db.get_conversation("nope") is None

    def test_get_recent_context(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        ctx = db.get_recent_context(minutes=60)
        assert len(ctx) >= 1


class TestSpeakers:
    def test_create_speaker(self, db):
        db.update_speaker("s1", name="Alice", words_delta=50, segments_delta=3)
        speakers = db.get_speakers()
        assert len(speakers) == 1
        assert speakers[0]["name"] == "Alice"
        assert speakers[0]["total_words"] == 50

    def test_update_speaker_increments(self, db):
        db.update_speaker("s1", name="Alice", words_delta=50, segments_delta=3)
        db.update_speaker("s1", words_delta=20, segments_delta=1)
        speakers = db.get_speakers()
        assert speakers[0]["total_words"] == 70
        assert speakers[0]["total_segments"] == 4

    def test_get_speaker_stats(self, db):
        db.update_speaker("s1", name="Alice", words_delta=100, segments_delta=5)
        stats = db.get_speaker_stats()
        assert len(stats) == 1
        assert stats[0]["total_words"] == 100


class TestContacts:
    def test_save_and_get(self, db):
        db.save_contact("c1", "Alice", email="a@b.com", phone="+1234")
        contacts = db.get_contacts()
        assert len(contacts) == 1
        assert contacts[0]["email"] == "a@b.com"

    def test_upsert_contact(self, db):
        db.save_contact("c1", "Alice", email="a@b.com")
        db.save_contact("c1", "Alice Updated", phone="+999")
        contacts = db.get_contacts()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Alice Updated"
        assert contacts[0]["email"] == "a@b.com"  # preserved via COALESCE
        assert contacts[0]["phone"] == "+999"

    def test_delete_contact(self, db):
        db.save_contact("c1", "Alice")
        db.delete_contact("c1")
        assert len(db.get_contacts()) == 0


class TestActions:
    def test_save_action(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        aid = db.save_action(conversation_id=sample_conversation_data["id"], intent="email",
                             params={"to": "x@y.com"}, raw_text="send email")
        assert aid is not None
        actions = db.get_actions()
        assert len(actions) == 1
        assert actions[0]["intent"] == "email"

    def test_update_action_status(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        aid = db.save_action(conversation_id=sample_conversation_data["id"], intent="reminder")
        db.update_action_status(aid, "executed", "done")
        actions = db.get_actions(status="executed")
        assert len(actions) == 1
        assert actions[0]["result"] == "done"
        assert actions[0]["executed_at"] is not None

    def test_filter_by_status(self, db):
        db.save_action(intent="a", status="pending")
        db.save_action(intent="b", status="executed")
        assert len(db.get_actions(status="pending")) == 1
        assert len(db.get_actions(status="executed")) == 1


class TestUtterances:
    def test_save_and_get(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        db.update_speaker("SPEAKER_00", name="David")
        cid = sample_conversation_data["id"]
        db.save_utterance("u1", cid, "SPEAKER_00", "Hello world", 0.0, 2.0)
        utts = db.get_utterances(cid)
        assert len(utts) == 1
        assert utts[0]["text"] == "Hello world"

    def test_batch_save(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        db.update_speaker("S0", name="Test")
        cid = sample_conversation_data["id"]
        batch = [
            {"id": "u1", "conversation_id": cid, "speaker_id": "S0", "text": "Hello", "started_at": 0, "ended_at": 1},
            {"id": "u2", "conversation_id": cid, "speaker_id": "S0", "text": "World", "started_at": 1, "ended_at": 2},
        ]
        db.save_utterances_batch(batch)
        assert len(db.get_utterances(cid)) == 2

    def test_fts_search(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        db.update_speaker("S0", name="Test")
        cid = sample_conversation_data["id"]
        db.save_utterance("u1", cid, "S0", "The quick brown fox jumps", 0, 2)
        db.save_utterance("u2", cid, "S0", "Lazy dog sleeps", 2, 4)
        results = db.search_utterances("fox")
        assert len(results) >= 1
        assert "fox" in results[0]["text"].lower() or "fox" in results[0].get("highlighted", "").lower()


class TestEntityMentions:
    def test_save_and_search(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        cid = sample_conversation_data["id"]
        db.save_entity_mention(cid, "person", "John Smith")
        results = db.search_entities("John")
        assert len(results) == 1
        assert results[0]["entity_name"] == "John Smith"


class TestRelationships:
    def test_save_new(self, db):
        rid = db.save_relationship("Alice", "Bob", "mentioned_with", evidence="conv:123")
        rels = db.get_relationships(entity_id="Alice")
        assert len(rels) == 1
        assert rels[0]["weight"] == 1.0

    def test_update_existing_bumps_weight(self, db):
        db.save_relationship("Alice", "Bob", "mentioned_with", evidence="conv:1")
        db.save_relationship("Alice", "Bob", "mentioned_with", evidence="conv:2")
        rels = db.get_relationships(entity_id="Alice")
        assert rels[0]["weight"] == 2.0

    def test_filter_by_type(self, db):
        db.save_relationship("A", "B", "mentioned_with")
        db.save_relationship("A", "C", "works_on")
        assert len(db.get_relationships(relation_type="works_on")) == 1

    def test_decay(self, db):
        db.save_relationship("A", "B", "mentioned_with")
        # Force last_seen to be old
        db._conn.execute("UPDATE relationships SET last_seen = ?", (time.time() - 86400 * 30,))
        db._conn.commit()
        db.decay_relationships(days_stale=7, decay_rate=2.0)
        # Weight was 1.0, decayed by 2.0 → ≤0, should be deleted
        assert len(db.get_relationships()) == 0

    def test_update_weight(self, db):
        rid = db.save_relationship("A", "B", "test")
        db.update_relationship_weight(rid, 5.0)
        rels = db.get_relationships()
        assert rels[0]["weight"] == 6.0


class TestPurge:
    def test_purge_conversation(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        db.update_speaker("S0", name="Test")
        cid = sample_conversation_data["id"]
        db.save_utterance("u1", cid, "S0", "Hello", 0, 1)
        db.save_entity_mention(cid, "person", "Alice")
        db.save_action(conversation_id=cid, intent="test")
        db.purge_conversation(cid)
        assert db.get_conversation(cid) is None
        assert len(db.get_utterances(cid)) == 0

    def test_purge_older_than(self, db):
        db.save_conversation(id="old", timestamp=time.time() - 86400 * 100, date="2025-01-01")
        db.save_conversation(id="new", timestamp=time.time(), date="2026-02-21")
        count = db.purge_older_than(30)
        assert count == 1
        assert db.get_conversation("old") is None
        assert db.get_conversation("new") is not None

    def test_purge_expired_ttl(self, db):
        db.save_conversation(id="exp", timestamp=time.time(), date="2026-02-21")
        db._conn.execute("UPDATE conversations SET ttl_expires = '2020-01-01T00:00:00' WHERE id = 'exp'")
        db._conn.commit()
        count = db.purge_expired()
        assert count == 1


class TestAnalytics:
    def test_analytics(self, db, sample_conversation_data):
        db.save_conversation(**sample_conversation_data)
        analytics = db.get_analytics(period="all")
        assert analytics["conversation_count"] == 1
        assert analytics["total_words"] == 200


class TestAudit:
    def test_audit(self, populated_db):
        stats = populated_db.audit()
        assert stats["conversations"] == 1
        assert stats["speakers"] == 2
        assert stats["contacts"] == 2
        assert "storage_bytes" in stats
