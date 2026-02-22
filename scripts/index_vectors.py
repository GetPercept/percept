#!/usr/bin/env python3
"""Bulk index all Percept conversations into the vector store."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import PerceptDB
from src.vector_store import PerceptVectorStore


def main():
    print("⦿ Percept Vector Indexer")
    print("=" * 40)

    db = PerceptDB()
    vs = PerceptVectorStore()

    # Check API key
    if not vs._api_key:
        print("✗ No NVIDIA API key found. Cannot index.")
        sys.exit(1)
    print(f"✓ NVIDIA API key loaded")
    print(f"✓ Model: {vs._model}")

    # Pre-check
    convos = db.get_conversations(limit=10000)
    print(f"✓ Found {len(convos)} conversations in SQLite")

    existing = vs.stats()
    print(f"✓ Vector store: {existing['total_chunks']} chunks, {existing['total_conversations']} conversations indexed")

    print()
    print("Indexing...")
    start = time.time()
    result = vs.index_all(db)
    elapsed = time.time() - start

    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"  Total:   {result['total']}")
    print(f"  Indexed: {result['indexed']}")
    print(f"  Skipped: {result['skipped']} (already indexed or empty)")
    print(f"  Failed:  {result['failed']}")

    final = vs.stats()
    print(f"\nVector store: {final['total_chunks']} chunks, {final['total_conversations']} conversations")


if __name__ == "__main__":
    main()
