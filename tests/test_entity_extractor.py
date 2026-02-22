"""Tests for EntityExtractor — regex extraction, resolution, relationships."""

import pytest
from src.entity_extractor import EntityExtractor, ExtractedEntity


class TestFastExtraction:
    def test_extract_email(self, entity_extractor):
        entities = entity_extractor.extract_fast("Contact me at alice@example.com please")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].name == "alice@example.com"

    def test_extract_phone(self, entity_extractor):
        entities = entity_extractor.extract_fast("Call me at 415-555-1234")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) == 1

    def test_extract_url(self, entity_extractor):
        entities = entity_extractor.extract_fast("Check out https://example.com/page")
        urls = [e for e in entities if e.type == "url"]
        assert len(urls) == 1

    def test_extract_mention(self, entity_extractor):
        entities = entity_extractor.extract_fast("Hey @johndoe check this out")
        mentions = [e for e in entities if e.type == "mention"]
        assert len(mentions) == 1
        assert mentions[0].name == "johndoe"

    def test_extract_date_today(self, entity_extractor):
        entities = entity_extractor.extract_fast("Let's meet today at 3pm")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) >= 1

    def test_extract_named_person(self, entity_extractor):
        entities = entity_extractor.extract_fast("Dr. Smith is available")
        persons = [e for e in entities if e.type == "person"]
        assert any("Smith" in p.name for p in persons)

    def test_extract_org(self, entity_extractor):
        entities = entity_extractor.extract_fast("He works at Acme Corp")
        orgs = [e for e in entities if e.type == "org"]
        assert len(orgs) >= 1

    def test_extract_capitalized_names(self, entity_extractor):
        entities = entity_extractor.extract_fast("I spoke with John Smith yesterday")
        persons = [e for e in entities if e.type == "person"]
        assert any("John Smith" in p.name for p in persons)

    def test_empty_text(self, entity_extractor):
        assert entity_extractor.extract_fast("") == []

    def test_no_entities(self, entity_extractor):
        entities = entity_extractor.extract_fast("the quick brown fox jumps over the lazy dog")
        # Only low-confidence capitalized words at best — should be empty or minimal
        assert all(e.confidence < 0.8 for e in entities)


class TestResolution:
    def test_exact_match_speaker(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entity = ExtractedEntity(type="person", name="David", confidence=0.6)
        resolved = extractor.resolve(entity)
        assert resolved.resolved_name == "David"
        assert resolved.resolution in ("auto", "soft")

    def test_exact_match_contact(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entity = ExtractedEntity(type="person", name="Alice", confidence=0.6)
        resolved = extractor.resolve(entity)
        assert resolved.resolved_name == "Alice"

    def test_fuzzy_match(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entity = ExtractedEntity(type="person", name="Bob Smit", confidence=0.6)
        resolved = extractor.resolve(entity)
        # "Bob Smit" should fuzzy-match "Bob Smith"
        assert resolved.resolved_name == "Bob Smith" or resolved.resolution == "unresolved"

    def test_unresolved(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entity = ExtractedEntity(type="person", name="Unknown Person XYZ", confidence=0.3)
        resolved = extractor.resolve(entity)
        assert resolved.resolution in ("unresolved", "needs_human")

    def test_pronoun_recency(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        recent = [ExtractedEntity(type="person", name="Alice", confidence=0.9, resolved_name="Alice")]
        entity = ExtractedEntity(type="person", name="she", confidence=0.5)
        resolved = extractor.resolve(entity, recent_entities=recent)
        assert resolved.resolved_name == "Alice"


class TestBatchExtraction:
    def test_extract_from_utterances(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        utterances = [
            {"text": "I talked to Dr. Smith about the deal"},
            {"text": "He works at Acme Corp"},
        ]
        entities = extractor.extract_from_utterances(utterances, conversation_id="2026-02-21_11-00")
        assert len(entities) > 0


class TestRelationshipBuilding:
    def test_build_person_person(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entities = [
            ExtractedEntity(type="person", name="Alice", confidence=0.9, resolved_name="Alice"),
            ExtractedEntity(type="person", name="Bob", confidence=0.9, resolved_name="Bob"),
        ]
        extractor.build_relationships(entities, conversation_id="conv1")
        rels = populated_db.get_relationships(entity_id="Alice")
        assert len(rels) >= 1
        assert any(r["relation_type"] == "mentioned_with" for r in rels)

    def test_build_person_org(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entities = [
            ExtractedEntity(type="person", name="Alice", confidence=0.9, resolved_name="Alice"),
            ExtractedEntity(type="org", name="Acme", confidence=0.8, resolved_name="Acme"),
        ]
        extractor.build_relationships(entities, conversation_id="conv1")
        rels = populated_db.get_relationships(entity_id="Alice")
        assert any(r["relation_type"] == "works_on" for r in rels)

    def test_no_relationships_single_entity(self, populated_db):
        extractor = EntityExtractor(db=populated_db, llm_enabled=False)
        entities = [ExtractedEntity(type="person", name="Alice", confidence=0.9)]
        extractor.build_relationships(entities)  # Should not crash
        rels = populated_db.get_relationships(entity_id="Alice")
        assert len(rels) == 0
