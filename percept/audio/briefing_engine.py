"""Briefing Engine — pre-meeting context intelligence for Percept CIL.

Before a meeting, automatically assemble a context packet about each attendee:
- Past conversations and topics discussed
- Open commitments and promises
- Relationship context and entity co-occurrences
- Recent conversation summaries where they were mentioned
- AI-synthesized talking points
"""

import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class BriefingEngine:
    """Generate pre-meeting context briefings for attendees."""

    def __init__(self, db=None, vector_store=None):
        """Initialize briefing engine with database and vector store."""
        if db is None:
            from .database import PerceptDB
            db = PerceptDB()
        if vector_store is None:
            from .vector_store import PerceptVectorStore
            vector_store = PerceptVectorStore()
        
        self.db = db
        self.vector_store = vector_store

    def generate_briefing(self, minutes_ahead: int = 60) -> Dict[str, Any]:
        """Generate briefings for upcoming meetings within specified minutes.
        
        Args:
            minutes_ahead: Look for meetings within this many minutes (default 60)
            
        Returns:
            Dict with meeting info and briefings for each attendee
        """
        # Get upcoming meetings from calendar
        meetings = self._get_upcoming_meetings(minutes_ahead)
        
        if not meetings:
            return {
                "status": "no_upcoming_meetings",
                "meetings": [],
                "generated_at": datetime.now().isoformat()
            }
        
        briefings = []
        for meeting in meetings:
            meeting_briefing = {
                "meeting": meeting,
                "attendees": []
            }
            
            for attendee in meeting.get("attendees", []):
                person_briefing = self.briefing_for_person(attendee["name"])
                person_briefing["email"] = attendee.get("email")
                meeting_briefing["attendees"].append(person_briefing)
            
            briefings.append(meeting_briefing)
        
        return {
            "status": "success",
            "meetings": briefings,
            "generated_at": datetime.now().isoformat()
        }

    def briefing_for_person(self, name: str) -> Dict[str, Any]:
        """Generate comprehensive briefing for a specific person.
        
        Args:
            name: Person's name to search for
            
        Returns:
            Dict with all available context about this person
        """
        logger.info(f"Generating briefing for: {name}")
        
        # Search conversations mentioning this person
        conversations = self._find_conversations_with_person(name)
        
        # Get relationship graph edges
        relationships = self._get_person_relationships(name)
        
        # Check open commitments
        commitments = self._get_person_commitments(name)
        
        # Get entity co-occurrences (pass conversations to avoid duplicate search)
        entities = self._get_person_entities(name, conversations=conversations)
        
        # Get recent conversation summaries
        recent_summaries = self._get_recent_summaries_with_person(name)
        
        # Generate AI talking points (optional)
        talking_points = self._generate_talking_points(name, conversations, commitments)
        
        return {
            "name": name,
            "last_interaction": self._get_last_interaction_date(conversations),
            "relationship_context": relationships,
            "recent_topics": self._extract_recent_topics(conversations),
            "open_commitments": commitments,
            "key_entities": entities,
            "conversation_summaries": recent_summaries,
            "suggested_talking_points": talking_points,
            "conversation_count": len(conversations),
            "generated_at": datetime.now().isoformat()
        }

    def _get_upcoming_meetings(self, minutes_ahead: int) -> List[Dict[str, Any]]:
        """Get upcoming meetings from calendar using gog CLI.
        
        Args:
            minutes_ahead: Look for meetings within this many minutes
            
        Returns:
            List of meeting dictionaries
        """
        try:
            # Calculate time range
            now = datetime.now()
            end_time = now + timedelta(minutes=minutes_ahead)
            
            # Use gog CLI to get calendar events
            cmd = [
                "/opt/homebrew/bin/gog", "calendar", "events",
                "--json",
                "--from", now.strftime("%Y-%m-%dT%H:%M:%S"),
                "--to", end_time.strftime("%Y-%m-%dT%H:%M:%S")
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.warning(f"gog calendar command failed: {result.stderr}")
                return []
            
            events = json.loads(result.stdout) if result.stdout.strip() else []
            
            # Parse events and extract attendees
            meetings = []
            for event in events:
                # Skip all-day events and events without attendees
                if event.get("allDay") or not event.get("attendees"):
                    continue
                
                # Extract attendee names and emails
                attendees = []
                for attendee in event.get("attendees", []):
                    # Extract name from email or use display name
                    name = attendee.get("displayName") or attendee.get("email", "").split("@")[0]
                    if name:
                        attendees.append({
                            "name": name,
                            "email": attendee.get("email"),
                            "response": attendee.get("responseStatus")
                        })
                
                if attendees:
                    meetings.append({
                        "id": event.get("id"),
                        "title": event.get("summary", "Untitled Meeting"),
                        "start_time": event.get("start", {}).get("dateTime"),
                        "end_time": event.get("end", {}).get("dateTime"),
                        "location": event.get("location"),
                        "attendees": attendees
                    })
            
            logger.info(f"Found {len(meetings)} upcoming meetings with attendees")
            return meetings
            
        except subprocess.TimeoutExpired:
            logger.error("gog calendar command timed out")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse gog calendar output: {e}")
            return []
        except FileNotFoundError:
            logger.warning("gog CLI not found, skipping calendar integration")
            return []
        except Exception as e:
            logger.error(f"Error getting calendar events: {e}")
            return []

    def _find_conversations_with_person(self, name: str) -> List[Dict[str, Any]]:
        """Find conversations mentioning this person using hybrid search."""
        try:
            # Use hybrid search for best results
            results = self.vector_store.hybrid_search(name, limit=20)
            
            # Also try keyword search as fallback
            if not results:
                results = self.db.search_utterances(name, limit=10)
            
            return results or []
            
        except Exception as e:
            logger.warning(f"Error searching conversations for {name}: {e}")
            return []

    def _get_person_relationships(self, name: str) -> List[Dict[str, Any]]:
        """Get relationship graph edges for this person."""
        try:
            # Search for relationships where this person is mentioned
            relationships = self.db.get_relationships()
            
            # Filter for relationships involving this person
            person_relationships = []
            for rel in relationships:
                if (name.lower() in rel.get("source_id", "").lower() or 
                    name.lower() in rel.get("target_id", "").lower()):
                    person_relationships.append(rel)
            
            return person_relationships
            
        except Exception as e:
            logger.warning(f"Error getting relationships for {name}: {e}")
            return []

    def _get_person_commitments(self, name: str) -> List[Dict[str, Any]]:
        """Get open commitments involving this person."""
        try:
            # Try to use CommitmentTracker to get commitments
            from .commitment_tracker import CommitmentTracker
            tracker = CommitmentTracker(db=self.db)
            
            # Get all open commitments and filter by person
            commitments = tracker.get_open_commitments()
            
            person_commitments = []
            for commitment in commitments:
                # Check if person is mentioned in commitment text or speaker
                if (name.lower() in commitment.get("text", "").lower() or
                    name.lower() in commitment.get("speaker", "").lower()):
                    person_commitments.append(commitment)
            
            return person_commitments
            
        except Exception as e:
            logger.info(f"Failed to get open commitments: {e}")
            # Graceful fallback - return empty list
            return []

    def _get_person_entities(self, name: str, conversations: List[Dict] = None) -> List[str]:
        """Get entities frequently co-occurring with this person."""
        try:
            # Get entity mentions from conversations mentioning this person
            if conversations is None:
                conversations = self._find_conversations_with_person(name)
            
            entities = set()
            for conv in conversations:
                conv_id = conv.get("conversation_id")
                if conv_id:
                    mentions = self.db.get_entity_mentions(conversation_id=conv_id)
                    for mention in mentions:
                        entity_name = mention.get("entity_name")
                        if entity_name and entity_name.lower() != name.lower():
                            entities.add(entity_name)
            
            return list(entities)[:10]  # Limit to top 10
            
        except Exception as e:
            logger.warning(f"Error getting entities for {name}: {e}")
            return []

    def _get_recent_summaries_with_person(self, name: str) -> List[Dict[str, Any]]:
        """Get recent conversation summaries where this person was mentioned."""
        try:
            # Get conversations mentioning this person (limited to recent ones)
            conversations = self.db.get_conversations(
                search=name,
                limit=10
            )
            
            summaries = []
            for conv in conversations:
                if conv.get("summary"):
                    summaries.append({
                        "date": conv.get("date"),
                        "summary": conv.get("summary"),
                        "speakers": conv.get("speakers"),
                        "conversation_id": conv.get("id")
                    })
            
            return summaries
            
        except Exception as e:
            logger.warning(f"Error getting summaries for {name}: {e}")
            return []

    def _generate_talking_points(self, name: str, conversations: List[Dict], 
                                commitments: List[Dict]) -> Optional[List[str]]:
        """Generate AI-synthesized talking points (optional feature)."""
        try:
            # Check if openclaw binary is available
            result = subprocess.run(["which", "openclaw"], capture_output=True)
            if result.returncode != 0:
                logger.info("OpenClaw not available, skipping AI talking points")
                return None
            
            # Prepare context for AI
            context = f"""Generate 3-4 brief talking points for an upcoming meeting with {name}.
            
Recent conversations:
{json.dumps(conversations[:5], indent=2)}

Open commitments:
{json.dumps(commitments, indent=2)}

Keep talking points concise and actionable."""

            # Call OpenClaw agent
            result = subprocess.run([
                "openclaw", "agent", "--prompt", context, "--max-tokens", "200"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse response into list of talking points
                response = result.stdout.strip()
                points = [line.strip() for line in response.split("\n") 
                         if line.strip() and not line.startswith("#")]
                return points[:4]  # Limit to 4 points
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.info(f"Could not generate AI talking points: {e}")
        
        return None

    def _get_last_interaction_date(self, conversations: List[Dict]) -> Optional[str]:
        """Get the date of the most recent interaction."""
        if not conversations:
            return None
        
        # Sort by timestamp and get most recent
        try:
            most_recent = max(conversations, 
                            key=lambda c: c.get("started_at") or c.get("timestamp") or 0)
            
            # Convert timestamp to readable date
            timestamp = most_recent.get("started_at") or most_recent.get("timestamp")
            if timestamp:
                if isinstance(timestamp, str):
                    # Try to parse ISO format
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                else:
                    # Assume Unix timestamp
                    dt = datetime.fromtimestamp(timestamp)
                return dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Error parsing last interaction date: {e}")
        
        return None

    def _extract_recent_topics(self, conversations: List[Dict]) -> List[str]:
        """Extract recent topics from conversations."""
        topics = set()
        
        for conv in conversations[:10]:  # Look at recent 10 conversations
            # Extract from summary if available
            summary = conv.get("highlighted") or conv.get("text") or ""
            if summary:
                # Simple topic extraction - look for key phrases
                words = summary.lower().split()
                for i, word in enumerate(words):
                    # Look for meaningful multi-word phrases
                    if i < len(words) - 1:
                        phrase = f"{word} {words[i+1]}"
                        if len(phrase) > 6 and not any(c in phrase for c in ["the ", "and ", "or ", "but "]):
                            topics.add(phrase.title())
            
            # Also check conversation topics if available
            conv_topics = conv.get("topics")
            if conv_topics:
                if isinstance(conv_topics, str):
                    topics.update(topic.strip() for topic in conv_topics.split(","))
                elif isinstance(conv_topics, list):
                    topics.update(conv_topics)
        
        return list(topics)[:8]  # Limit to top 8 topics

    def format_briefing_markdown(self, briefing_data: Dict[str, Any]) -> str:
        """Format briefing data as human-readable markdown."""
        if briefing_data.get("status") == "no_upcoming_meetings":
            return "## No Upcoming Meetings\n\nNo meetings found in the next 60 minutes."
        
        output = []
        
        for meeting_data in briefing_data.get("meetings", []):
            meeting = meeting_data.get("meeting", {})
            attendees = meeting_data.get("attendees", [])
            
            # Meeting header
            title = meeting.get("title", "Untitled Meeting")
            start_time = meeting.get("start_time", "")
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    time_str = dt.strftime("%I:%M %p").lstrip("0")
                except:
                    time_str = start_time
            else:
                time_str = "Unknown time"
            
            output.append(f"## Pre-Meeting Briefing: {title} ({time_str})")
            output.append("")
            
            # Attendee briefings
            for attendee in attendees:
                name = attendee.get("name", "Unknown")
                output.append(f"### {name}")
                
                # Last interaction
                last_interaction = attendee.get("last_interaction")
                if last_interaction:
                    output.append(f"**Last spoke:** {last_interaction}")
                else:
                    output.append("**Last spoke:** No prior conversations found")
                
                # Relationship context
                relationships = attendee.get("relationship_context", [])
                if relationships:
                    output.append(f"**Relationship:** {relationships[0].get('relation_type', 'Unknown')}")
                
                # Recent topics
                topics = attendee.get("recent_topics", [])
                if topics:
                    output.append(f"**Recent topics:** {', '.join(topics[:5])}")
                
                # Open commitments
                commitments = attendee.get("open_commitments", [])
                if commitments:
                    output.append("**Open commitments:**")
                    for commitment in commitments[:3]:
                        text = commitment.get("text", "")[:80]
                        due_date = commitment.get("due_date", "")
                        status_note = " (OVERDUE)" if commitment.get("status") == "overdue" else ""
                        output.append(f"- \"{text}\" ({due_date}{status_note})")
                
                # Key entities/context
                entities = attendee.get("key_entities", [])
                if entities:
                    output.append(f"**Key context:** Frequently mentions {', '.join(entities[:3])}")
                
                # Talking points
                talking_points = attendee.get("suggested_talking_points")
                if talking_points:
                    output.append("**Suggested talking points:**")
                    for point in talking_points:
                        output.append(f"- {point}")
                
                output.append("")
        
        return "\n".join(output)