"""Semantic vector store for Percept conversations using NVIDIA NIM + LanceDB."""

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NVIDIA_CREDS_PATH = Path.home() / ".config" / "nvidia" / "credentials.json"
DEFAULT_MODEL = "nvidia/nv-embedqa-e5-v5"
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/embeddings"


def _load_nvidia_key(path: Path = NVIDIA_CREDS_PATH) -> Optional[str]:
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("nim_api_key") or data.get("api_key")
    except Exception:
        return None


class PerceptVectorStore:
    def __init__(self, db_path: str = None, nvidia_api_key: str = None,
                 model: str = DEFAULT_MODEL, chunk_size: int = 500, chunk_overlap: int = 50):
        import lancedb

        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "vectors")
        Path(db_path).mkdir(parents=True, exist_ok=True)

        self._db = lancedb.connect(db_path)
        self._api_key = nvidia_api_key or _load_nvidia_key()
        self._model = model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._table_name = "conversations"
        self._embedding_dim = None  # discovered on first call

        if not self._api_key:
            logger.warning("No NVIDIA API key found — vector store will be read-only")

    # ── Embeddings ──────────────────────────────────────────────────

    def _get_embedding(self, text: str, input_type: str = "passage") -> Optional[list[float]]:
        """Get embedding from NVIDIA NIM API."""
        if not self._api_key:
            return None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = json.dumps({
            "input": [text[:8000]],  # truncate to avoid token limits
            "model": self._model,
            "input_type": input_type,
            "encoding_format": "float",
        }).encode()
        try:
            req = urllib.request.Request(NVIDIA_ENDPOINT, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            vec = result["data"][0]["embedding"]
            if self._embedding_dim is None:
                self._embedding_dim = len(vec)
            return vec
        except Exception as e:
            logger.warning(f"NVIDIA embedding failed: {e}")
            return None

    def _get_embeddings_batch(self, texts: list[str], input_type: str = "passage") -> Optional[list[list[float]]]:
        """Get embeddings for multiple texts in one call (max ~50 per request)."""
        if not self._api_key or not texts:
            return None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        truncated = [t[:8000] for t in texts]
        payload = json.dumps({
            "input": truncated,
            "model": self._model,
            "input_type": input_type,
            "encoding_format": "float",
        }).encode()
        try:
            req = urllib.request.Request(NVIDIA_ENDPOINT, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read())
            vecs = [d["embedding"] for d in sorted(result["data"], key=lambda x: x["index"])]
            if self._embedding_dim is None and vecs:
                self._embedding_dim = len(vecs[0])
            return vecs
        except Exception as e:
            logger.warning(f"NVIDIA batch embedding failed: {e}")
            return None

    # ── Chunking ────────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []
        sz, ov = self._chunk_size, self._chunk_overlap
        if len(text) <= sz:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + sz
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - ov
        return chunks

    # ── Table management ────────────────────────────────────────────

    def _get_table(self):
        try:
            return self._db.open_table(self._table_name)
        except Exception:
            return None

    def _indexed_conversation_ids(self) -> set[str]:
        """Return set of conversation IDs already indexed."""
        tbl = self._get_table()
        if tbl is None:
            return set()
        try:
            df = tbl.to_pandas()
            return set(df["conversation_id"].unique())
        except Exception:
            return set()

    # ── Indexing ─────────────────────────────────────────────────────

    def index_conversation(self, conversation_id: str, transcript: str,
                           summary: str = None, speakers: list = None,
                           date: str = None, topics: list = None) -> int:
        """Embed and store a conversation's chunks. Returns number of chunks indexed."""
        import pyarrow as pa

        # Skip if already indexed
        if conversation_id in self._indexed_conversation_ids():
            logger.debug(f"Already indexed: {conversation_id}")
            return 0

        # Build chunks: transcript chunks + summary (high-signal)
        chunks = self._chunk_text(transcript or "")
        chunk_types = ["transcript"] * len(chunks)
        if summary:
            chunks.append(summary)
            chunk_types.append("summary")

        if not chunks:
            return 0

        # Get embeddings in batches of 20
        all_vecs = []
        batch_size = 20
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            vecs = self._get_embeddings_batch(batch, input_type="passage")
            if vecs is None:
                logger.warning(f"Embedding failed for {conversation_id}, batch {i}")
                return 0
            all_vecs.extend(vecs)
            if i + batch_size < len(chunks):
                time.sleep(0.1)  # rate limit

        if len(all_vecs) != len(chunks):
            logger.warning(f"Embedding count mismatch for {conversation_id}")
            return 0

        speakers_str = json.dumps(speakers) if speakers else "[]"
        topics_str = json.dumps(topics) if topics else "[]"

        records = []
        for idx, (chunk, vec, ctype) in enumerate(zip(chunks, all_vecs, chunk_types)):
            records.append({
                "conversation_id": conversation_id,
                "chunk_index": idx,
                "chunk_type": ctype,
                "text": chunk,
                "date": date or "",
                "speakers": speakers_str,
                "topics": topics_str,
                "vector": vec,
            })

        tbl = self._get_table()
        if tbl is None:
            self._db.create_table(self._table_name, records)
        else:
            tbl.add(records)

        return len(records)

    # ── Search ──────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10, date_filter: str = None) -> list[dict]:
        """Semantic search across all conversations."""
        tbl = self._get_table()
        if tbl is None:
            return []

        vec = self._get_embedding(query, input_type="query")
        if vec is None:
            return []

        q = tbl.search(vec).limit(limit * 3 if date_filter else limit)

        try:
            results = q.to_pandas()
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            return []

        if date_filter and "date" in results.columns:
            results = results[results["date"] == date_filter]

        results = results.head(limit)

        out = []
        for _, row in results.iterrows():
            out.append({
                "conversation_id": row.get("conversation_id", ""),
                "text": row.get("text", ""),
                "score": float(row.get("_distance", 0)),
                "date": row.get("date", ""),
                "speakers": row.get("speakers", "[]"),
                "chunk_type": row.get("chunk_type", ""),
            })
        return out

    # ── Context retrieval ───────────────────────────────────────────

    def get_relevant_context(self, text: str, minutes: int = 60, limit: int = 5) -> str:
        """Get relevant context combining recency + semantic search.

        Used for action resolution: 'email the client' → find who 'the client' is.
        """
        # Semantic results
        sem_results = self.search(text, limit=limit)

        # Recent conversations from SQLite
        recent_context = []
        try:
            from src.database import PerceptDB
            db = PerceptDB()
            recent = db.get_recent_context(minutes=minutes)
            for r in recent[:3]:
                snippet = (r.get("transcript") or "")[:300]
                if snippet:
                    recent_context.append(f"[Recent] {snippet}")
        except Exception:
            pass

        # Combine
        parts = recent_context[:]
        for r in sem_results:
            parts.append(f"[Relevant] {r['text'][:300]}")

        return "\n---\n".join(parts) if parts else ""

    # ── Bulk indexing ───────────────────────────────────────────────

    def index_all(self, db=None) -> dict:
        """Bulk index all conversations from SQLite."""
        if db is None:
            from src.database import PerceptDB
            db = PerceptDB()

        already = self._indexed_conversation_ids()
        convos = db.get_conversations(limit=10000)
        total = len(convos)
        indexed = 0
        skipped = 0
        failed = 0

        for i, c in enumerate(convos):
            cid = c["id"]
            if cid in already:
                skipped += 1
                continue

            transcript = c.get("transcript") or ""
            if not transcript.strip():
                skipped += 1
                continue

            n = self.index_conversation(
                conversation_id=cid,
                transcript=transcript,
                summary=c.get("summary"),
                speakers=c.get("speakers"),
                date=c.get("date"),
                topics=c.get("topics"),
            )
            if n > 0:
                indexed += 1
            else:
                failed += 1

            if (i + 1) % 10 == 0:
                print(f"  Indexed {indexed}/{total} conversations... (skipped {skipped}, failed {failed})")

        return {"total": total, "indexed": indexed, "skipped": skipped, "failed": failed}

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return vector store stats."""
        tbl = self._get_table()
        if tbl is None:
            return {"total_chunks": 0, "total_conversations": 0, "table_exists": False}
        try:
            total_chunks = tbl.count_rows()
            # Get unique conversation count
            df = tbl.to_pandas()
            return {
                "total_chunks": total_chunks,
                "total_conversations": int(df["conversation_id"].nunique()),
                "table_exists": True,
            }
        except Exception as e:
            logger.warning(f"Stats error: {e}")
            try:
                return {"total_chunks": tbl.count_rows(), "total_conversations": 0, "table_exists": True}
            except Exception:
                return {"total_chunks": 0, "total_conversations": 0, "table_exists": True}
