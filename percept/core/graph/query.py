"""Query engine — structured queries + natural language (keyword-based MVP)."""
from __future__ import annotations

import re
from typing import Optional

from .database import GraphDB
from .models import Node, Edge


class QueryEngine:
    """Query engine for the knowledge graph.
    
    MVP uses keyword matching for natural language queries.
    Future: plug in Claude Haiku via Bedrock for NL→query translation.
    """

    def __init__(self, db: GraphDB):
        self.db = db

    def query(self, text: str) -> dict:
        """Process a natural language query and return results."""
        text_lower = text.lower().strip()

        # Pattern: "who works at X" / "who is at X"
        m = re.match(r"who (?:works|is) at (.+?)[\?]?$", text_lower)
        if m:
            return self._who_works_at(m.group(1).strip())

        # Pattern: "what does X use" / "what tools does X use"
        m = re.match(r"what (?:tools? )?does (.+?) use[\?]?$", text_lower)
        if m:
            return self._what_uses(m.group(1).strip())

        # Pattern: "what decisions ... about X"
        m = re.match(r"what decisions (?:were made |)(?:about |regarding )(.+?)[\?]?$", text_lower)
        if m:
            return self._decisions_about(m.group(1).strip())

        # Pattern: "what projects does X own/have"
        m = re.match(r"what projects? does (.+?) (?:own|have|run|manage)[\?]?$", text_lower)
        if m:
            return self._projects_of(m.group(1).strip())

        # Pattern: "what is X" / "tell me about X"
        m = re.match(r"(?:what is|tell me about|describe|info on) (.+?)[\?]?$", text_lower)
        if m:
            return self._about(m.group(1).strip())

        # Pattern: "lessons about X" / "what did we learn about X"
        m = re.match(r"(?:lessons?|what did (?:we|i) learn) (?:about |on |from )(.+?)[\?]?$", text_lower)
        if m:
            return self._lessons_about(m.group(1).strip())

        # Fallback: FTS search
        return self._fts_search(text)

    def _who_works_at(self, org_name: str) -> dict:
        org = self.db.find_node(org_name, "Organization")
        if not org:
            return {"query": f"who works at {org_name}", "results": [], "summary": f"No organization '{org_name}' found."}
        
        neighbors = self.db.neighbors(org.id, edge_type="WORKS_AT", direction="in")
        people = [n.name for _, n in neighbors if n]
        return {
            "query": f"who works at {org_name}",
            "results": [{"name": p} for p in people],
            "summary": f"{', '.join(people) if people else 'No one found'} works at {org.name}.",
        }

    def _what_uses(self, person_name: str) -> dict:
        person = self.db.find_node(person_name, "Person")
        if not person:
            return {"query": f"what does {person_name} use", "results": [], "summary": f"No person '{person_name}' found."}
        
        neighbors = self.db.neighbors(person.id, edge_type="USES", direction="out")
        tools = [{"name": n.name, "type": n.type, **n.properties} for _, n in neighbors if n]
        names = [t["name"] for t in tools]
        return {
            "query": f"what does {person_name} use",
            "results": tools,
            "summary": f"{person.name} uses: {', '.join(names) if names else 'nothing found'}.",
        }

    def _decisions_about(self, topic: str) -> dict:
        # Search for Concept nodes that match the topic
        nodes = self.db.search_nodes(topic, node_type="Concept")
        if not nodes:
            # Broaden search
            nodes = self.db.search_nodes(topic)
        
        results = []
        for node in nodes:
            # Get DECIDED edges pointing to this node
            edges_in = self.db.neighbors(node.id, edge_type="DECIDED", direction="in")
            for edge, person in edges_in:
                if person:
                    results.append({
                        "decision": node.name,
                        "by": person.name,
                        "properties": node.properties,
                    })
            # Also include the node itself if it looks like a decision
            if "decision" in node.type.lower() or node.properties.get("alternatives"):
                results.append({
                    "decision": node.name,
                    "properties": node.properties,
                })

        summary_parts = [r["decision"] for r in results[:5]]
        return {
            "query": f"decisions about {topic}",
            "results": results,
            "summary": f"Found {len(results)} decision(s): {'; '.join(summary_parts)}" if results else f"No decisions found about '{topic}'.",
        }

    def _projects_of(self, person_name: str) -> dict:
        person = self.db.find_node(person_name, "Person")
        if not person:
            return {"query": f"projects of {person_name}", "results": [], "summary": f"No person '{person_name}' found."}
        
        neighbors = self.db.neighbors(person.id, edge_type="OWNS", direction="out")
        # Also get BUILT edges
        built = self.db.neighbors(person.id, edge_type="BUILT", direction="out")
        all_projects = [(e, n) for e, n in neighbors + built if n and n.type == "Project"]
        
        results = [{"name": n.name, **n.properties} for _, n in all_projects]
        names = [r["name"] for r in results]
        return {
            "query": f"projects of {person_name}",
            "results": results,
            "summary": f"{person.name}'s projects: {', '.join(names) if names else 'none found'}.",
        }

    def _about(self, name: str) -> dict:
        node = self.db.find_node(name)
        if not node:
            nodes = self.db.search_nodes(name)
            if nodes:
                node = nodes[0]
        
        if not node:
            return {"query": f"about {name}", "results": [], "summary": f"Nothing found about '{name}'."}
        
        neighbors = self.db.neighbors(node.id)
        connections = []
        for edge, neighbor in neighbors:
            if neighbor:
                connections.append(f"{edge.type} → {neighbor.name} [{neighbor.type}]")
        
        return {
            "query": f"about {name}",
            "results": [{
                "name": node.name,
                "type": node.type,
                "properties": node.properties,
                "connections": connections,
            }],
            "summary": f"{node.name} [{node.type}]: {len(connections)} connections. " +
                       (f"Connected to: {', '.join(connections[:5])}" if connections else "No connections."),
        }

    def _lessons_about(self, topic: str) -> dict:
        nodes = self.db.search_nodes(topic, node_type="Concept")
        results = []
        for node in nodes:
            if node.properties.get("lesson"):
                results.append({"lesson": node.name, "details": node.properties})
        
        if not results:
            # Broaden: search all nodes
            all_nodes = self.db.search_nodes(topic)
            for node in all_nodes:
                if "lesson" in str(node.properties).lower() or "learned" in str(node.properties).lower():
                    results.append({"topic": node.name, "details": node.properties})
        
        return {
            "query": f"lessons about {topic}",
            "results": results,
            "summary": f"Found {len(results)} lesson(s) about '{topic}'." if results else f"No lessons found about '{topic}'.",
        }

    def _fts_search(self, query: str) -> dict:
        """Fallback: full-text search."""
        # Clean query for FTS5
        clean = re.sub(r'[^\w\s]', '', query)
        terms = clean.split()
        if not terms:
            return {"query": query, "results": [], "summary": "Empty query."}
        
        fts_query = " OR ".join(terms)
        try:
            nodes = self.db.search_nodes(fts_query)
        except Exception:
            # If FTS fails, do LIKE search
            nodes = []
            for term in terms:
                rows = self.db.conn.execute(
                    "SELECT * FROM nodes WHERE name LIKE ? OR properties LIKE ? LIMIT 20",
                    (f"%{term}%", f"%{term}%")
                ).fetchall()
                nodes.extend([Node.from_row(dict(r)) for r in rows])
        
        # Deduplicate
        seen = set()
        unique = []
        for n in nodes:
            if n.id not in seen:
                seen.add(n.id)
                unique.append(n)
        
        results = [{"name": n.name, "type": n.type, "properties": n.properties} for n in unique[:20]]
        return {
            "query": query,
            "results": results,
            "summary": f"Found {len(results)} result(s) matching '{query}'.",
        }
