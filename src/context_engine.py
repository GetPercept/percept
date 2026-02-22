"""Context Packet Assembly for Percept CIL.

Assembles full context packets for agent action resolution by combining
conversation data, entity resolution, relationships, and recent context.
"""

import json
import logging
import time
from typing import Optional

from src.database import PerceptDB
from src.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)

# Optional vector store integration
try:
    from src.vector_store import PerceptVectorStore
except ImportError:
    PerceptVectorStore = None


class ContextEngine:
    """Assembles context packets for agent actions."""

    def __init__(self, db: PerceptDB, vector_store=None):
        self.db = db
        self.vector_store = vector_store
        self.entity_extractor = EntityExtractor(db=db)

    def get_context_packet(self, conversation_id: str, command_text: str) -> dict:
        """Assemble full context packet for agent action resolution.

        Returns:
            {
                "conversation": {"id", "mode", "duration_minutes", "speakers": [...]},
                "command": {"raw_text", "intent", "resolved_entities": {...}},
                "recent_context": ["...", "..."]
            }
        """
        # Conversation info
        conv = self.db.get_conversation(conversation_id)
        conv_info = {
            "id": conversation_id,
            "mode": "ambient",
            "duration_minutes": 0,
            "speakers": [],
        }
        if conv:
            duration_s = conv.get("duration_seconds") or 0
            conv_info["duration_minutes"] = round(duration_s / 60, 1)
            speakers = conv.get("speakers") or []
            if isinstance(speakers, str):
                try:
                    speakers = json.loads(speakers)
                except Exception:
                    speakers = []
            conv_info["speakers"] = speakers

        # Entity resolution on command text
        entities = self.entity_extractor.extract_fast(command_text)
        resolved_entities = {}
        recent_utterances = self.db.get_utterances(conversation_id)
        recent_entity_list = self.entity_extractor.extract_from_utterances(
            recent_utterances[-10:], conversation_id
        ) if recent_utterances else []

        for e in entities:
            e = self.entity_extractor.resolve(
                e, conversation_id=conversation_id, recent_entities=recent_entity_list
            )
            resolved_entities[e.name] = {
                "type": e.type,
                "resolved_name": e.resolved_name,
                "resolved_id": e.resolved_id,
                "confidence": e.confidence,
                "resolution": e.resolution,
            }

        # Intent (basic — IntentParser handles the full version)
        intent = self._detect_basic_intent(command_text)

        # Recent context
        recent = self.get_recent_context(minutes=30, limit=10)

        return {
            "conversation": conv_info,
            "command": {
                "raw_text": command_text,
                "intent": intent,
                "resolved_entities": resolved_entities,
            },
            "recent_context": recent,
        }

    def resolve_entity(self, surface_form: str, conversation_id: str = None) -> dict:
        """Resolve ambiguous reference to a specific entity.

        Resolution chain: exact → fuzzy → contextual (graph) → recency → semantic.
        """
        from src.entity_extractor import ExtractedEntity

        entity = ExtractedEntity(type="unknown", name=surface_form, confidence=0.5)

        # Get recent entities for recency matching
        recent_entities = []
        if conversation_id:
            utterances = self.db.get_utterances(conversation_id)
            recent_entities = self.entity_extractor.extract_from_utterances(
                utterances[-10:], conversation_id
            )

        entity = self.entity_extractor.resolve(
            entity, conversation_id=conversation_id, recent_entities=recent_entities
        )

        # 5. Semantic search fallback
        if entity.resolution == "unresolved" and self.vector_store:
            try:
                results = self.vector_store.search(surface_form, limit=3)
                if results:
                    # Extract entity names from search results
                    for r in results:
                        text = r.get("text", "")
                        sub_entities = self.entity_extractor.extract_fast(text)
                        for se in sub_entities:
                            if se.type in ("person", "org", "project"):
                                entity.resolved_name = se.name
                                entity.confidence = 0.55
                                entity.resolution = "soft"
                                break
                        if entity.resolution != "unresolved":
                            break
            except Exception as e:
                logger.debug(f"Semantic search fallback failed: {e}")

        return {
            "surface_form": surface_form,
            "resolved_name": entity.resolved_name,
            "resolved_id": entity.resolved_id,
            "type": entity.type,
            "confidence": entity.confidence,
            "resolution": entity.resolution,
        }

    def get_recent_context(self, minutes: int = 30, limit: int = 10) -> list[str]:
        """Get recent conversation snippets for context."""
        conversations = self.db.get_recent_context(minutes=minutes)
        snippets = []
        for conv in conversations[:limit]:
            transcript = conv.get("transcript") or conv.get("summary") or ""
            if transcript:
                # Truncate to ~200 chars
                snippet = transcript[:200].strip()
                if len(transcript) > 200:
                    snippet += "..."
                snippets.append(snippet)
        return snippets

    def _detect_basic_intent(self, text: str) -> str:
        """Basic intent detection from command text."""
        text_lower = text.lower()
        intents = {
            "email": ["email", "send an email", "shoot an email"],
            "text": ["text", "message", "send a text", "tell"],
            "reminder": ["remind", "reminder", "don't forget"],
            "search": ["search", "look up", "find", "research", "what is", "who is"],
            "calendar": ["schedule", "book", "calendar", "meeting"],
            "note": ["remember", "note", "save this", "jot down"],
            "order": ["order", "buy", "shopping"],
        }
        for intent, keywords in intents.items():
            if any(kw in text_lower for kw in keywords):
                return intent
        return "unknown"
