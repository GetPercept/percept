"""Two-pass entity extraction pipeline for Percept CIL.

Fast pass: regex-based extraction (emails, phones, dates, named entities).
LLM pass: semantic extraction for complex entities.
Resolution: exact → fuzzy → contextual → recency → semantic.
"""

import hashlib
import json
import logging
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# Binary path resolution with fallback
def _get_binary_path(name: str) -> str:
    """Get binary path dynamically with fallback."""
    path = shutil.which(name)
    if not path:
        logger.warning(f"Binary '{name}' not found in PATH, action will be skipped")
        return None
    return path

# Confidence thresholds
CONF_AUTO = 0.8       # auto-resolve
CONF_SOFT = 0.5       # soft-resolve (flag uncertainty)
# < 0.5 = needs_human


@dataclass
class ExtractedEntity:
    type: str           # person, email, phone, url, date, mention, org, project
    name: str           # surface form
    confidence: float
    context: str = ""   # surrounding text
    resolved_id: str = None
    resolved_name: str = None
    resolution: str = "unresolved"  # auto, soft, needs_human, unresolved


class EntityExtractor:
    """Two-pass entity extraction with resolution."""

    def __init__(self, db=None, llm_enabled: bool = False):
        self.db = db
        self.llm_enabled = llm_enabled
        self._cache: dict[str, list[dict]] = {}  # text_hash -> entities

    # ── Fast Pass (regex) ──────────────────────────────────────────────

    def extract_fast(self, text: str) -> list[ExtractedEntity]:
        """Rule-based entity extraction."""
        entities = []

        # Emails
        for m in re.finditer(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', text):
            entities.append(ExtractedEntity("email", m.group(), 0.95, text[max(0,m.start()-20):m.end()+20]))

        # Phone numbers
        for m in re.finditer(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', text):
            entities.append(ExtractedEntity("phone", m.group(), 0.9, text[max(0,m.start()-20):m.end()+20]))

        # URLs
        for m in re.finditer(r'https?://\S+', text):
            entities.append(ExtractedEntity("url", m.group(), 0.95, text[max(0,m.start()-20):m.end()+20]))

        # @mentions
        for m in re.finditer(r'@(\w+)', text):
            entities.append(ExtractedEntity("mention", m.group(1), 0.85, text[max(0,m.start()-20):m.end()+20]))

        # Dates: today, tomorrow, next Monday, Feb 21, etc.
        date_patterns = [
            (r'\b(today|tomorrow|yesterday)\b', 0.9),
            (r'\b(next|this|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 0.85),
            (r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b', 0.85),
            (r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b', 0.7),
        ]
        for pat, conf in date_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                entities.append(ExtractedEntity("date", m.group(), conf, text[max(0,m.start()-20):m.end()+20]))

        # Named entities: title prefixes + capitalized words
        for m in re.finditer(r'\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text):
            entities.append(ExtractedEntity("person", m.group(1), 0.85, text[max(0,m.start()-20):m.end()+20]))

        # Company suffixes
        for m in re.finditer(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?)\b', text):
            entities.append(ExtractedEntity("org", m.group(), 0.8, text[max(0,m.start()-20):m.end()+20]))

        # Known products/tech — classify before the generic capitalized phrase pass
        _KNOWN_PRODUCTS = {
            "apple watch", "apple tv", "apple music", "apple pay",
            "google maps", "google drive", "google cloud", "google home",
            "amazon echo", "amazon alexa", "mac mini", "mac pro",
            "microsoft teams", "visual studio", "open ai", "chat gpt",
            "omi pendant", "omi device",
        }

        # Capitalized multi-word phrases (potential names/orgs) — lower confidence
        for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
            name = m.group(1)
            # Skip if already captured
            if not any(e.name == name for e in entities):
                if name.lower() in _KNOWN_PRODUCTS:
                    entities.append(ExtractedEntity("product", name, 0.7, text[max(0,m.start()-20):m.end()+20]))
                else:
                    entities.append(ExtractedEntity("person", name, 0.6, text[max(0,m.start()-20):m.end()+20]))

        return entities

    # ── LLM Pass (semantic) ────────────────────────────────────────────

    def _should_llm_extract(self, text: str) -> bool:
        """Heuristic: does this text likely contain extractable entities?"""
        # Has proper nouns (capitalized words not at sentence start)
        has_proper = bool(re.search(r'(?<=[.!?\s])\s*[a-z].*?\b[A-Z][a-z]+', text))
        # Has action verbs suggesting tasks/projects
        has_actions = bool(re.search(r'\b(working on|building|launching|meeting with|talking to|project|proposal|contract|deal)\b', text, re.IGNORECASE))
        # Has project-sounding phrases
        has_project = bool(re.search(r'\b(phase|sprint|milestone|v\d|version|release|launch|deadline)\b', text, re.IGNORECASE))
        return has_proper or has_actions or has_project

    async def extract_llm(self, text: str) -> list[ExtractedEntity]:
        """LLM-based entity extraction for complex cases."""
        if not self.llm_enabled or not self._should_llm_extract(text):
            return []

        # Check cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self._cache:
            return [ExtractedEntity(**e) for e in self._cache[text_hash]]

        import asyncio
        import os

        prompt = f"""Extract entities from this conversation text. Return JSON array only.
Entity types: person, org, project, product, location, event
For each: {{"type": "...", "name": "...", "confidence": 0.0-1.0, "context": "brief context"}}

Text: "{text[:2000]}"

JSON array:"""

        try:
            openclaw_path = _get_binary_path("openclaw")
            if not openclaw_path:
                logger.warning("[ENTITY] openclaw binary not found, skipping LLM extraction")
                return []
                
            env = os.environ.copy()  # Inherit system PATH
            proc = await asyncio.create_subprocess_exec(
                openclaw_path, "agent", "--message",
                f"ENTITY_EXTRACT (respond with raw JSON array only): {prompt}",
                "--channel", "imessage", "--no-deliver",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                return []

            response = stdout.decode().strip()
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if not json_match:
                return []

            parsed = json.loads(json_match.group())
            entities = []
            for e in parsed:
                entities.append(ExtractedEntity(
                    type=e.get("type", "unknown"),
                    name=e.get("name", ""),
                    confidence=e.get("confidence", 0.5),
                    context=e.get("context", ""),
                ))

            # Cache
            self._cache[text_hash] = [{"type": e.type, "name": e.name, "confidence": e.confidence, "context": e.context} for e in entities]
            return entities

        except Exception as e:
            logger.warning(f"LLM entity extraction failed: {e}")
            return []

    # ── Resolution ─────────────────────────────────────────────────────

    def resolve(self, entity: ExtractedEntity, conversation_id: str = None,
                recent_entities: list[ExtractedEntity] = None) -> ExtractedEntity:
        """Resolve entity to a known ID using multi-strategy resolution."""
        if not self.db:
            return entity

        name = entity.name.strip()
        recent_entities = recent_entities or []

        # 1. Exact match against entity_mentions / contacts / speakers
        resolved = self._exact_match(name)
        if resolved:
            entity.resolved_id = resolved["id"]
            entity.resolved_name = resolved["name"]
            entity.confidence = max(entity.confidence, 0.9)
            entity.resolution = "auto" if entity.confidence >= CONF_AUTO else "soft"
            return entity

        # 2. Fuzzy match
        resolved = self._fuzzy_match(name)
        if resolved:
            entity.resolved_id = resolved["id"]
            entity.resolved_name = resolved["name"]
            entity.confidence = resolved["score"]
            entity.resolution = "auto" if entity.confidence >= CONF_AUTO else "soft"
            return entity

        # 3. Contextual match via relationships
        if conversation_id:
            resolved = self._contextual_match(name, conversation_id)
            if resolved:
                entity.resolved_id = resolved["id"]
                entity.resolved_name = resolved["name"]
                entity.confidence = resolved.get("confidence", 0.7)
                entity.resolution = "soft"
                return entity

        # 4. Recency match (pronoun resolution)
        if name.lower() in ("he", "she", "they", "them", "him", "her", "it", "the client", "the team"):
            resolved = self._recency_match(name, recent_entities)
            if resolved:
                entity.resolved_id = resolved.get("id")
                entity.resolved_name = resolved["name"]
                entity.confidence = 0.65
                entity.resolution = "soft"
                return entity

        # Unresolved — set confidence bucket
        if entity.confidence < CONF_SOFT:
            entity.resolution = "needs_human"
        return entity

    def _exact_match(self, name: str) -> Optional[dict]:
        """Exact match against speakers and contacts."""
        # Speakers
        speakers = self.db.get_speakers()
        for s in speakers:
            if s.get("name") and s["name"].lower() == name.lower():
                return {"id": s["id"], "name": s["name"]}

        # Contacts
        try:
            with self.db._lock:
                row = self.db._conn.execute(
                    "SELECT id, name FROM contacts WHERE LOWER(name) = ?",
                    (name.lower(),)).fetchone()
            if row:
                return {"id": row["id"], "name": row["name"]}
        except Exception:
            pass

        return None

    def _fuzzy_match(self, name: str, threshold: float = 0.85) -> Optional[dict]:
        """Fuzzy match using SequenceMatcher."""
        best = None
        best_score = 0

        # Check speakers
        for s in self.db.get_speakers():
            sname = s.get("name") or ""
            score = SequenceMatcher(None, name.lower(), sname.lower()).ratio()
            if score > best_score and score >= threshold:
                best = {"id": s["id"], "name": sname, "score": score}
                best_score = score

        # Check contacts
        try:
            with self.db._lock:
                rows = self.db._conn.execute("SELECT id, name FROM contacts").fetchall()
            for r in rows:
                score = SequenceMatcher(None, name.lower(), r["name"].lower()).ratio()
                if score > best_score and score >= threshold:
                    best = {"id": r["id"], "name": r["name"], "score": score}
                    best_score = score
        except Exception:
            pass

        return best

    def _contextual_match(self, name: str, conversation_id: str) -> Optional[dict]:
        """Traverse relationship graph for contextual resolution."""
        name_lower = name.lower()

        # Get entities mentioned in this conversation
        try:
            with self.db._lock:
                rows = self.db._conn.execute("""
                    SELECT DISTINCT entity_name, entity_type FROM entity_mentions
                    WHERE conversation_id = ?
                """, (conversation_id,)).fetchall()

            for row in rows:
                rels = self.db.get_relationships(entity_id=row["entity_name"])
                for rel in rels:
                    # If someone says "the client" and we have a client_of relationship
                    if name_lower == "the client" and rel.get("relation_type") == "client_of":
                        target = rel["target_id"] if rel["source_id"] == row["entity_name"] else rel["source_id"]
                        return {"id": target, "name": target, "confidence": 0.7}
                    if name_lower == "the team" and rel.get("relation_type") == "works_on":
                        target = rel["target_id"] if rel["source_id"] == row["entity_name"] else rel["source_id"]
                        return {"id": target, "name": target, "confidence": 0.65}
        except Exception:
            pass

        return None

    def _recency_match(self, pronoun: str, recent_entities: list[ExtractedEntity]) -> Optional[dict]:
        """Resolve pronouns based on recently mentioned entities."""
        pronoun_lower = pronoun.lower()

        # Filter to person entities
        persons = [e for e in recent_entities if e.type == "person" and e.resolved_name]

        if not persons:
            return None

        # Gender-based matching (simple heuristic)
        if pronoun_lower in ("she", "her"):
            # Return most recent female-coded name (imperfect but useful)
            return {"name": persons[-1].resolved_name or persons[-1].name, "id": persons[-1].resolved_id}
        elif pronoun_lower in ("he", "him"):
            return {"name": persons[-1].resolved_name or persons[-1].name, "id": persons[-1].resolved_id}
        elif pronoun_lower in ("they", "them", "the client", "the team"):
            return {"name": persons[-1].resolved_name or persons[-1].name, "id": persons[-1].resolved_id}

        return None

    # ── Batch extraction ───────────────────────────────────────────────

    def extract_from_utterances(self, utterances: list[dict],
                                conversation_id: str = None) -> list[ExtractedEntity]:
        """Extract entities from a batch of utterances (fast pass only for sync)."""
        all_entities = []
        recent_entities = []

        for utt in utterances:
            text = utt.get("text", "")
            entities = self.extract_fast(text)

            # Resolve each entity
            for e in entities:
                e = self.resolve(e, conversation_id=conversation_id, recent_entities=recent_entities)
                all_entities.append(e)

            recent_entities.extend(entities)
            # Keep only last 20 for recency
            recent_entities = recent_entities[-20:]

        return all_entities

    async def extract_from_utterances_async(self, utterances: list[dict],
                                             conversation_id: str = None) -> list[ExtractedEntity]:
        """Extract entities with both fast and LLM passes."""
        all_entities = []
        recent_entities = []

        # Batch text for LLM pass
        batch_text = " ".join(u.get("text", "") for u in utterances)

        # Fast pass per utterance
        for utt in utterances:
            text = utt.get("text", "")
            entities = self.extract_fast(text)
            for e in entities:
                e = self.resolve(e, conversation_id=conversation_id, recent_entities=recent_entities)
                all_entities.append(e)
            recent_entities.extend(entities)
            recent_entities = recent_entities[-20:]

        # LLM pass on batch
        if self.llm_enabled and batch_text.strip():
            llm_entities = await self.extract_llm(batch_text)
            for e in llm_entities:
                # Deduplicate
                if not any(existing.name.lower() == e.name.lower() for existing in all_entities):
                    e = self.resolve(e, conversation_id=conversation_id, recent_entities=recent_entities)
                    all_entities.append(e)

        return all_entities

    def build_relationships(self, entities: list[ExtractedEntity], conversation_id: str = None):
        """Build/update relationships from co-occurring entities."""
        if not self.db or len(entities) < 2:
            return

        # Group by type
        persons = [e for e in entities if e.type == "person"]
        orgs = [e for e in entities if e.type == "org"]
        projects = [e for e in entities if e.type == "project"]

        evidence = f"conversation:{conversation_id}" if conversation_id else None

        # Person-person: mentioned_with
        for i, p1 in enumerate(persons):
            for p2 in persons[i+1:]:
                name1 = p1.resolved_name or p1.name
                name2 = p2.resolved_name or p2.name
                if name1 != name2:
                    self.db.save_relationship(name1, name2, "mentioned_with", evidence)

        # Person-org: works_on or client_of
        for p in persons:
            for o in orgs:
                pname = p.resolved_name or p.name
                oname = o.resolved_name or o.name
                self.db.save_relationship(pname, oname, "works_on", evidence)

        # Person-project: works_on
        for p in persons:
            for proj in projects:
                pname = p.resolved_name or p.name
                projname = proj.resolved_name or proj.name
                self.db.save_relationship(pname, projname, "works_on", evidence)
