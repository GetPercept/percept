"""Semantic vector store for Percept conversations using NVIDIA NIM + LanceDB."""

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import os
import socket
import threading

logger = logging.getLogger(__name__)

NVIDIA_CREDS_PATH = Path.home() / ".config" / "nvidia" / "credentials.json"
DEFAULT_MODEL = "nvidia/nv-embedqa-e5-v5"
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/embeddings"
LOCAL_MODEL = "all-MiniLM-L6-v2"

# Retry constants
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt


def _retry_with_backoff(fn, max_retries: int = MAX_RETRIES, base_delay: float = RETRY_BASE_DELAY):
    """Execute fn() with exponential backoff. Returns result or raises last exception."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} failed: {e}. Waiting {delay:.1f}s")
            time.sleep(delay)
    raise last_exc


def _load_nvidia_key(path: Path = NVIDIA_CREDS_PATH) -> Optional[str]:
    """Load NVIDIA API key from credentials JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("nim_api_key") or data.get("api_key")
    except Exception:
        return None


def _check_network_connectivity() -> bool:
    """Check if we have network connectivity to NVIDIA API."""
    try:
        socket.create_connection(("integrate.api.nvidia.com", 443), timeout=3)
        return True
    except (socket.error, socket.timeout):
        return False


class LocalEmbedder:
    """Local embedding model using sentence-transformers."""
    
    def __init__(self, model_name: str = LOCAL_MODEL):
        self.model_name = model_name
        self._model = None
        self._embedding_dim = 384  # Known dimension for all-MiniLM-L6-v2
        
    def _load_model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise
            except Exception as e:
                logger.error(f"Failed to load local model {self.model_name}: {e}")
                raise
                
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from local model."""
        if not text.strip():
            return None
            
        try:
            self._load_model()
            # Truncate to reasonable length to avoid memory issues
            text = text[:8000]
            embedding = self._model.encode(text, convert_to_tensor=False)
            return embedding.tolist()
        except Exception as e:
            logger.warning(f"Local embedding failed: {e}")
            return None
            
    def get_embeddings_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Get embeddings for multiple texts."""
        if not texts:
            return None
            
        try:
            self._load_model()
            # Truncate texts
            truncated = [t[:8000] for t in texts if t.strip()]
            if not truncated:
                return None
                
            embeddings = self._model.encode(truncated, convert_to_tensor=False)
            return embeddings.tolist()
        except Exception as e:
            logger.warning(f"Local batch embedding failed: {e}")
            return None
    
    @property
    def embedding_dim(self) -> int:
        """Return embedding dimension."""
        return self._embedding_dim


class PerceptVectorStore:
    def __init__(self, db_path: str = None, nvidia_api_key: str = None,
                 model: str = DEFAULT_MODEL, chunk_size: int = 500, chunk_overlap: int = 50):
        """Initialize vector store with LanceDB backend and auto-fallback embeddings."""
        import lancedb

        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "vectors")
        Path(db_path).mkdir(parents=True, exist_ok=True)

        self._db = lancedb.connect(db_path)
        self._api_key = nvidia_api_key or _load_nvidia_key()
        self._model = model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        
        # Auto-detection: prefer NVIDIA if available, fallback to local
        self._use_nvidia = self._api_key is not None and _check_network_connectivity()
        
        # Queue for chunks that failed embedding (for later retry)
        self._failed_chunks: List[Dict[str, Any]] = []
        self._failed_lock = threading.Lock()
        
        if self._use_nvidia:
            self._table_name = "conversations_nvidia"
            self._embedding_dim = 1024  # NVIDIA NV-EmbedQA-E5-V5 dimension
            logger.info("Using NVIDIA NIM embeddings")
        else:
            self._table_name = "conversations_local"
            self._embedding_dim = 384  # Local model dimension
            self._local_embedder = LocalEmbedder()
            logger.info("Using local embeddings (sentence-transformers)")

    # ── Embeddings ──────────────────────────────────────────────────

    def _get_embedding(self, text: str, input_type: str = "passage") -> Optional[List[float]]:
        """Get embedding using auto-detection (NVIDIA preferred, local fallback)."""
        if self._use_nvidia:
            return self._get_nvidia_embedding(text, input_type)
        else:
            return self._local_embedder.get_embedding(text)
            
    def _get_embeddings_batch(self, texts: List[str], input_type: str = "passage") -> Optional[List[List[float]]]:
        """Get embeddings for multiple texts using auto-detection."""
        if self._use_nvidia:
            return self._get_nvidia_embeddings_batch(texts, input_type)
        else:
            return self._local_embedder.get_embeddings_batch(texts)

    def _get_nvidia_embedding(self, text: str, input_type: str = "passage") -> Optional[List[float]]:
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
            return vec
        except Exception as e:
            logger.warning(f"NVIDIA embedding failed: {e}")
            return None

    def _get_nvidia_embeddings_batch(self, texts: List[str], input_type: str = "passage") -> Optional[List[List[float]]]:
        """Get embeddings for multiple texts from NVIDIA NIM API (max ~50 per request)."""
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
        """Open and return the LanceDB table, or None if it doesn't exist."""
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
        """Embed and store a conversation's chunks with retry + failure queuing.
        
        Returns number of chunks indexed. Failed batches are queued for later retry
        via retry_failed(), and logged but never crash the pipeline.
        """
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

        speakers_str = json.dumps(speakers) if speakers else "[]"
        topics_str = json.dumps(topics) if topics else "[]"

        # Get embeddings in batches of 20 with retry
        all_vecs = []
        batch_size = 20
        failed_batch_chunks = []
        failed_batch_types = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_types = chunk_types[i:i + batch_size]

            try:
                vecs = _retry_with_backoff(
                    lambda b=batch: self._get_embeddings_batch(b, input_type="passage")
                )
            except Exception as e:
                logger.error(f"Embedding failed after {MAX_RETRIES} retries for {conversation_id} batch {i}: {e}")
                vecs = None

            if vecs is None or len(vecs) != len(batch):
                logger.warning(f"Queuing {len(batch)} failed chunks from {conversation_id} for later retry")
                failed_batch_chunks.extend(batch)
                failed_batch_types.extend(batch_types)
                # Pad with None so indexing stays aligned
                all_vecs.extend([None] * len(batch))
            else:
                all_vecs.extend(vecs)

            if i + batch_size < len(chunks):
                time.sleep(0.1)  # rate limit

        # Queue failed chunks for later retry
        if failed_batch_chunks:
            with self._failed_lock:
                self._failed_chunks.append({
                    "conversation_id": conversation_id,
                    "chunks": failed_batch_chunks,
                    "chunk_types": failed_batch_types,
                    "speakers": speakers_str,
                    "topics": topics_str,
                    "date": date or "",
                })
            logger.info(f"Queued {len(failed_batch_chunks)} failed chunks for {conversation_id}")

        # Build records from successfully embedded chunks only
        records = []
        chunk_idx = 0
        for chunk, vec, ctype in zip(chunks, all_vecs, chunk_types):
            if vec is None:
                continue  # Skip failed embeddings
            records.append({
                "conversation_id": conversation_id,
                "chunk_index": chunk_idx,
                "chunk_type": ctype,
                "text": chunk,
                "date": date or "",
                "speakers": speakers_str,
                "topics": topics_str,
                "vector": vec,
            })
            chunk_idx += 1

        if not records:
            logger.warning(f"No chunks successfully embedded for {conversation_id}")
            return 0

        try:
            tbl = self._get_table()
            if tbl is None:
                self._db.create_table(self._table_name, records)
            else:
                tbl.add(records)
        except Exception as e:
            logger.error(f"Failed to write to LanceDB for {conversation_id}: {e}")
            return 0

        return len(records)

    def retry_failed(self) -> dict:
        """Retry embedding and indexing for previously failed chunks.
        
        Returns dict with counts: attempted, succeeded, still_failed.
        """
        with self._failed_lock:
            pending = list(self._failed_chunks)
            self._failed_chunks.clear()

        if not pending:
            return {"attempted": 0, "succeeded": 0, "still_failed": 0}

        attempted = 0
        succeeded = 0
        still_failed_items = []

        for item in pending:
            chunks = item["chunks"]
            chunk_types = item["chunk_types"]
            attempted += len(chunks)

            try:
                vecs = _retry_with_backoff(
                    lambda c=chunks: self._get_embeddings_batch(c, input_type="passage")
                )
            except Exception:
                vecs = None

            if vecs is None or len(vecs) != len(chunks):
                still_failed_items.append(item)
                continue

            records = []
            for idx, (chunk, vec, ctype) in enumerate(zip(chunks, vecs, chunk_types)):
                records.append({
                    "conversation_id": item["conversation_id"],
                    "chunk_index": idx,
                    "chunk_type": ctype,
                    "text": chunk,
                    "date": item["date"],
                    "speakers": item["speakers"],
                    "topics": item["topics"],
                    "vector": vec,
                })

            try:
                tbl = self._get_table()
                if tbl is None:
                    self._db.create_table(self._table_name, records)
                else:
                    tbl.add(records)
                succeeded += len(records)
            except Exception as e:
                logger.error(f"Retry write failed for {item['conversation_id']}: {e}")
                still_failed_items.append(item)

        with self._failed_lock:
            self._failed_chunks.extend(still_failed_items)

        result = {
            "attempted": attempted,
            "succeeded": succeeded,
            "still_failed": sum(len(i["chunks"]) for i in still_failed_items),
        }
        logger.info(f"Retry results: {result}")
        return result

    # ── Search ──────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10, date_filter: str = None) -> List[Dict[str, Any]]:
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

    def hybrid_search(self, query: str, limit: int = 10, alpha: float = 0.5, 
                     date_filter: str = None) -> List[Dict[str, Any]]:
        """Hybrid search combining FTS5 keyword + vector semantic results using Reciprocal Rank Fusion.
        
        Args:
            query: Search query
            limit: Maximum results to return
            alpha: 0 = pure keyword, 1 = pure semantic, 0.5 = balanced
            date_filter: Optional date filter (YYYY-MM-DD)
            
        Returns:
            Unified ranked results with RRF scores
        """
        # Get FTS5 keyword results
        keyword_results = []
        try:
            from .database import PerceptDB
            db = PerceptDB()
            fts_results = db.search_utterances(query, limit=limit * 2)
            db.close()
            
            for i, result in enumerate(fts_results):
                keyword_results.append({
                    "conversation_id": result.get("conversation_id", ""),
                    "text": result.get("text", ""),
                    "score": 1.0 / (i + 1),  # Rank-based score
                    "date": "",  # FTS doesn't have date directly
                    "speakers": "[]",
                    "chunk_type": "fts",
                    "source": "keyword",
                    "rank": i + 1
                })
        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")
            
        # Get semantic vector results
        semantic_results = []
        tbl = self._get_table()
        if tbl is not None:
            vec = self._get_embedding(query, input_type="query")
            if vec is not None:
                try:
                    q = tbl.search(vec).limit(limit * 2)
                    results = q.to_pandas()
                    
                    if date_filter and "date" in results.columns:
                        results = results[results["date"] == date_filter]
                    
                    for i, (_, row) in enumerate(results.iterrows()):
                        semantic_results.append({
                            "conversation_id": row.get("conversation_id", ""),
                            "text": row.get("text", ""),
                            "score": 1.0 / (i + 1),  # Rank-based score  
                            "date": row.get("date", ""),
                            "speakers": row.get("speakers", "[]"),
                            "chunk_type": row.get("chunk_type", ""),
                            "source": "semantic",
                            "rank": i + 1,
                            "vector_distance": float(row.get("_distance", 0))
                        })
                except Exception as e:
                    logger.warning(f"Semantic search failed: {e}")
        
        # Handle edge cases
        if not keyword_results and not semantic_results:
            return []
        elif not semantic_results:
            # Fall back to FTS5 only
            return keyword_results[:limit]
        elif not keyword_results:
            # Use semantic only
            return semantic_results[:limit]
            
        # Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        k = 60  # RRF constant
        
        # Add keyword results to RRF
        if alpha < 1.0:
            for result in keyword_results:
                key = (result["conversation_id"], result["text"][:100])
                rrf_scores[key] = rrf_scores.get(key, {"result": result, "score": 0})
                rrf_scores[key]["score"] += (1 - alpha) * (1 / (k + result["rank"]))
        
        # Add semantic results to RRF
        if alpha > 0.0:
            for result in semantic_results:
                key = (result["conversation_id"], result["text"][:100])
                rrf_scores[key] = rrf_scores.get(key, {"result": result, "score": 0})
                rrf_scores[key]["score"] += alpha * (1 / (k + result["rank"]))
        
        # Sort by RRF score and return
        sorted_results = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        
        final_results = []
        for item in sorted_results[:limit]:
            result = item["result"].copy()
            result["rrf_score"] = item["score"]
            result["source"] = "hybrid"
            final_results.append(result)
            
        return final_results

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
