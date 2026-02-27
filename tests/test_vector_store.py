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


class TestLocalEmbedder:
    """Test the new LocalEmbedder class."""
    
    def test_local_embedder_init(self):
        from src.vector_store import LocalEmbedder
        embedder = LocalEmbedder()
        assert embedder.model_name == "all-MiniLM-L6-v2"
        assert embedder.embedding_dim == 384
        
    def test_local_embedder_lazy_loading(self):
        from src.vector_store import LocalEmbedder
        embedder = LocalEmbedder()
        assert embedder._model is None  # Not loaded yet
        
    @patch("src.vector_store.LocalEmbedder._load_model")
    def test_get_embedding_384_dims(self, mock_load):
        """Test that local embedder produces 384-dim vectors."""
        from src.vector_store import LocalEmbedder
        
        # Mock the model to return a 384-dim vector
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1] * 384
        
        embedder = LocalEmbedder()
        embedder._model = mock_model
        
        result = embedder.get_embedding("test text")
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)
        
    @patch("src.vector_store.LocalEmbedder._load_model")  
    def test_get_embeddings_batch(self, mock_load):
        from src.vector_store import LocalEmbedder
        
        mock_model = MagicMock()
        mock_array = MagicMock()
        mock_array.tolist.return_value = [[0.1] * 384, [0.2] * 384]
        mock_model.encode.return_value = mock_array
        
        embedder = LocalEmbedder()
        embedder._model = mock_model
        
        result = embedder.get_embeddings_batch(["text1", "text2"])
        assert len(result) == 2
        assert len(result[0]) == 384
        assert len(result[1]) == 384


class TestAutoDetection:
    """Test the auto-detection logic for NVIDIA vs Local embeddings."""
    
    def test_nvidia_preferred_when_available(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value="test-key"), \
             patch("src.vector_store._check_network_connectivity", return_value=True):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            assert vs._use_nvidia is True
            assert vs._table_name == "conversations_nvidia"
            assert vs._embedding_dim == 1024
            
    def test_local_fallback_no_key(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            assert vs._use_nvidia is False
            assert vs._table_name == "conversations_local"
            assert vs._embedding_dim == 384
            
    def test_local_fallback_no_network(self, tmp_path):
        with patch("src.vector_store._load_nvidia_key", return_value="test-key"), \
             patch("src.vector_store._check_network_connectivity", return_value=False):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            assert vs._use_nvidia is False
            assert vs._table_name == "conversations_local"


class TestHybridSearch:
    """Test hybrid search functionality."""
    
    def test_hybrid_search_empty_store(self, tmp_path, mock_db):
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            
            # Mock empty FTS results
            mock_db.search_utterances.return_value = []
            
            with patch("src.database.PerceptDB", return_value=mock_db):
                results = vs.hybrid_search("test query")
                assert results == []
                
    def test_hybrid_search_fts_only_fallback(self, tmp_path, mock_db):
        """Test fallback to FTS when vector store is empty."""
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            
            # Mock FTS results
            mock_fts_results = [
                {"conversation_id": "conv1", "text": "Hello world"},
                {"conversation_id": "conv2", "text": "Test message"}
            ]
            mock_db.search_utterances.return_value = mock_fts_results
            
            with patch("src.database.PerceptDB", return_value=mock_db):
                results = vs.hybrid_search("test")
                assert len(results) == 2
                assert results[0]["source"] == "keyword"
                assert results[0]["conversation_id"] == "conv1"
                
    def test_hybrid_search_rrf_scoring(self, tmp_path, mock_db):
        """Test Reciprocal Rank Fusion scoring."""
        fake_vec = [0.1] * 384
        
        with patch("src.vector_store._load_nvidia_key", return_value=None):
            from src.vector_store import PerceptVectorStore
            vs = PerceptVectorStore(db_path=str(tmp_path / "v"))
            
            # Mock both FTS and vector results
            mock_fts_results = [
                {"conversation_id": "conv1", "text": "Hello world"}
            ]
            mock_db.search_utterances.return_value = mock_fts_results
            
            # Add some data to vector store
            with patch.object(vs._local_embedder, "get_embeddings_batch", return_value=[fake_vec]):
                vs.index_conversation("conv1", "Hello world")
            
            with patch.object(vs._local_embedder, "get_embedding", return_value=fake_vec):
                with patch("src.database.PerceptDB", return_value=mock_db):
                    results = vs.hybrid_search("hello", alpha=0.5)
                    assert len(results) >= 1
                    assert "rrf_score" in results[0]
                    assert results[0]["source"] == "hybrid"


@pytest.fixture
def mock_db():
    """Mock database for testing."""
    mock = MagicMock()
    mock.search_utterances.return_value = []
    mock.close.return_value = None
    return mock
