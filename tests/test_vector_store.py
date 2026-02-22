"""Tests for PerceptVectorStore — init, add, search (mocked embeddings)."""

import pytest
from unittest.mock import patch, MagicMock


class TestVectorStoreInit:
    def test_init_no_key(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "vectors"), nvidia_api_key=None)
            assert vs._api_key is None

    def test_init_with_key(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value="test-key"):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "vectors"), nvidia_api_key="test-key")
            assert vs._api_key == "test-key"


class TestChunking:
    def test_short_text(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None)
            chunks = vs._chunk_text("Hello world")
            assert chunks == ["Hello world"]

    def test_empty_text(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None)
            assert vs._chunk_text("") == []

    def test_long_text(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None, chunk_size=50, chunk_overlap=10)
            text = "a" * 200
            chunks = vs._chunk_text(text)
            assert len(chunks) > 1


class TestEmbeddingsAndSearch:
    def test_get_embedding_no_key(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None)
            assert vs._get_embedding("hello") is None

    def test_search_empty_store(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None)
            results = vs.search("hello")
            assert results == []

    def test_index_and_search_mocked(self, tmp_path):
        """Test indexing with mocked embeddings."""
        fake_vec = [0.1] * 128

        with patch("src.vector_store._load_nvidia_key", return_value="fake"):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key="fake")

            with patch.object(vs, "_get_embeddings_batch", return_value=[fake_vec]):
                count = vs.index_conversation("conv1", "Hello world this is a test", summary=None)
                assert count == 1

            with patch.object(vs, "_get_embedding", return_value=fake_vec):
                results = vs.search("hello", limit=5)
                assert len(results) >= 1
                assert results[0]["conversation_id"] == "conv1"

    def test_skip_already_indexed(self, tmp_path):
        fake_vec = [0.1] * 128
        with patch("src.vector_store._load_nvidia_key", return_value="fake"):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key="fake")
            with patch.object(vs, "_get_embeddings_batch", return_value=[fake_vec]):
                vs.index_conversation("conv1", "Hello world")
                # Index again — should skip
                count = vs.index_conversation("conv1", "Hello world")
                assert count == 0


class TestStats:
    def test_stats_empty(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"), nvidia_api_key=None)
            stats = vs.stats()
            assert stats["total_chunks"] == 0
            assert stats["table_exists"] is False
