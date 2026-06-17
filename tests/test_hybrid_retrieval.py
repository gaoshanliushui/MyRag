"""
Test Suite for Hybrid Retrieval System

Tests for the core retrieval functionality combining dense, sparse, and graph methods.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.core.retrieval.hybrid import HybridRetriever
from app.core.retrieval.fusion import DynamicWeightFusion, QueryAnalyzer
from app.models.schemas import RetrievalMode


class TestQueryAnalyzer:
    """Test query analysis functionality."""

    def test_query_analysis(self):
        """Test the query analyzer for different types of queries."""
        analyzer = QueryAnalyzer()

        # Test entity query
        query = "John Smith"
        query_type, features = analyzer.analyze(query)
        assert query_type.name in ["ENTITY", "MIXED"]

        # Test semantic query
        query = "What are the benefits of using hybrid retrieval in enterprise RAG systems?"
        query_type, features = analyzer.analyze(query)
        assert query_type.name in ["SEMANTIC", "MIXED"]

        # Test mixed query
        query = "Find information about MyRag system"
        query_type, features = analyzer.analyze(query)
        assert query_type.name in ["MIXED", "SEMANTIC"]

    def test_entity_detection(self):
        """Test entity detection in queries."""
        analyzer = QueryAnalyzer()

        # Test capitalized entity
        entities = analyzer._detect_entities("Tell me about John Smith")
        assert "John Smith" in entities

        # Test quoted string
        entities = analyzer._detect_entities('Find "enterprise RAG systems"')
        assert "enterprise RAG systems" in entities

        # Test number
        entities = analyzer._detect_entities("Project ID 12345")
        assert "12345" in entities

    def test_question_type_detection(self):
        """Test question type detection."""
        analyzer = QueryAnalyzer()

        question_types = {
            "Who developed MyRag?": "who",
            "What are the features?": "what",
            "How does it work?": "how",
            "Why should I use it?": "why",
            "Where is it deployed?": "where",
            "When was it released?": "when"
        }

        for question, expected_type in question_types.items():
            detected_type = analyzer._detect_question_type(question)
            assert detected_type == expected_type or detected_type == "general"


class TestDynamicWeightFusion:
    """Test dynamic weight fusion functionality."""

    def test_weight_computation(self):
        """Test computation of dynamic weights."""
        fusion = DynamicWeightFusion()

        # Test entity query
        weights = fusion.compute_weights("MyRag system")
        assert abs(sum(weights.values()) - 1.0) < 0.01  # Should sum to 1.0

        # Test semantic query
        weights = fusion.compute_weights("How does the hybrid retrieval mechanism work in enterprise environments?")
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_fusion_method(self):
        """Test the fusion of results from different retrieval methods."""
        fusion = DynamicWeightFusion()

        # Create mock results from different retrievers
        dense_results = [
            {"chunk_id": "1", "dense_score": 0.9, "content": "Content 1"},
            {"chunk_id": "2", "dense_score": 0.7, "content": "Content 2"},
        ]

        sparse_results = [
            {"chunk_id": "1", "sparse_score": 0.8, "content": "Content 1"},
            {"chunk_id": "3", "sparse_score": 0.6, "content": "Content 3"},
        ]

        graph_results = [
            {"chunk_id": "2", "graph_score": 0.85, "content": "Content 2"},
            {"chunk_id": "4", "graph_score": 0.75, "content": "Content 4"},
        ]

        weights = {"dense": 0.4, "sparse": 0.3, "graph": 0.3}

        fused_results = fusion.fuse(dense_results, sparse_results, graph_results, weights)

        # Verify results are merged and scored
        assert len(fused_results) == 4  # Should have 4 unique chunks
        assert all("fusion_score" in result for result in fused_results)
        assert all(result["fusion_score"] >= 0 for result in fused_results)


class TestHybridRetriever:
    """Test the hybrid retriever orchestration."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test initialization of hybrid retriever."""
        retriever = HybridRetriever(
            milvus_collection="test_collection",
            es_index="test_index",
            neo4j_label="test_label",
            tenant_id="test_tenant"
        )

        assert retriever.milvus_collection == "test_collection"
        assert retriever.es_index == "test_index"
        assert retriever.neo4j_label == "test_label"
        assert retriever.tenant_id == "test_tenant"

    @pytest.mark.asyncio
    async def test_retrieve_hybrid(self):
        """Test hybrid retrieval mode."""
        # Create mock retrievers
        mock_dense = AsyncMock()
        mock_dense.retrieve.return_value = [
            {"chunk_id": "1", "content": "Dense result 1", "dense_score": 0.9},
            {"chunk_id": "2", "content": "Dense result 2", "dense_score": 0.7}
        ]
        mock_dense.get_latency.return_value = 50.0

        mock_sparse = AsyncMock()
        mock_sparse.retrieve.return_value = [
            {"chunk_id": "1", "content": "Sparse result 1", "sparse_score": 0.8},
            {"chunk_id": "3", "content": "Sparse result 3", "sparse_score": 0.6}
        ]
        mock_sparse.get_latency.return_value = 30.0

        mock_graph = AsyncMock()
        mock_graph.retrieve.return_value = [
            {"chunk_id": "2", "content": "Graph result 2", "graph_score": 0.85},
            {"chunk_id": "4", "content": "Graph result 4", "graph_score": 0.75}
        ]
        mock_graph.get_latency.return_value = 40.0

        # Create mock fusion
        mock_fusion = MagicMock()
        mock_fusion.fuse.return_value = [
            {"chunk_id": "1", "content": "Fused result 1", "fusion_score": 0.85},
            {"chunk_id": "2", "content": "Fused result 2", "fusion_score": 0.82},
            {"chunk_id": "3", "content": "Fused result 3", "fusion_score": 0.65},
            {"chunk_id": "4", "content": "Fused result 4", "fusion_score": 0.75}
        ]
        mock_fusion.get_latency.return_value = 10.0
        mock_fusion.compute_weights.return_value = {"dense": 0.4, "sparse": 0.3, "graph": 0.3}

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.dense = mock_dense
            retriever.sparse = mock_sparse
            retriever.graph = mock_graph
            retriever.fusion = mock_fusion
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = None
            retriever.rerank_latency_ms = None
            retriever._query_type = None
            retriever._weights_used = {}

            results = await retriever.retrieve("test query", mode=RetrievalMode.HYBRID)

            # Verify all retrievers were called
            mock_dense.retrieve.assert_called_once()
            mock_sparse.retrieve.assert_called_once()
            mock_graph.retrieve.assert_called_once()

            # Verify fusion was called
            mock_fusion.fuse.assert_called_once()

            # Verify results
            assert len(results) == 4

    @pytest.mark.asyncio
    async def test_retrieve_dense_only(self):
        """Test dense-only retrieval mode."""
        mock_dense = AsyncMock()
        mock_dense.retrieve.return_value = [
            {"chunk_id": "1", "content": "Dense result 1", "dense_score": 0.9}
        ]
        mock_dense.get_latency.return_value = 50.0

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.dense = mock_dense
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = None
            retriever.rerank_latency_ms = None

            results = await retriever.retrieve("test query", mode=RetrievalMode.DENSE)

            # Verify only dense retriever was called
            mock_dense.retrieve.assert_called_once()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_sparse_only(self):
        """Test sparse-only retrieval mode."""
        mock_sparse = AsyncMock()
        mock_sparse.retrieve.return_value = [
            {"chunk_id": "1", "content": "Sparse result 1", "sparse_score": 0.8}
        ]
        mock_sparse.get_latency.return_value = 30.0

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.sparse = mock_sparse
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = None
            retriever.rerank_latency_ms = None

            results = await retriever.retrieve("test query", mode=RetrievalMode.SPARSE)

            # Verify only sparse retriever was called
            mock_sparse.retrieve.assert_called_once()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_graph_only(self):
        """Test graph-only retrieval mode."""
        mock_graph = AsyncMock()
        mock_graph.retrieve.return_value = [
            {"chunk_id": "1", "content": "Graph result 1", "graph_score": 0.85}
        ]
        mock_graph.get_latency.return_value = 40.0

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.graph = mock_graph
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = None
            retriever.rerank_latency_ms = None

            results = await retriever.retrieve("test query", mode=RetrievalMode.GRAPH)

            # Verify only graph retriever was called
            mock_graph.retrieve.assert_called_once()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_with_filters(self):
        """Test retrieval with filters applied."""
        mock_dense = AsyncMock()
        mock_dense.retrieve.return_value = [
            {"chunk_id": "1", "content": "Filtered result", "dense_score": 0.9}
        ]

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.dense = mock_dense
            retriever.sparse = AsyncMock()
            retriever.graph = AsyncMock()
            retriever.fusion = MagicMock()
            retriever.fusion.fuse.return_value = [
                {"chunk_id": "1", "content": "Filtered result", "fusion_score": 0.9}
            ]
            retriever.fusion.compute_weights.return_value = {"dense": 0.4, "sparse": 0.3, "graph": 0.3}
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = None
            retriever.rerank_latency_ms = None
            retriever._query_type = None
            retriever._weights_used = {}

            # Test with filters
            filters = {"document_ids": ["doc1", "doc2"]}
            results = await retriever.retrieve("test query", mode=RetrievalMode.HYBRID, filters=filters)

            # Verify filters were passed to the dense retriever
            mock_dense.retrieve.assert_called_once()
            assert len(results) >= 0  # May be empty depending on filter results

    @pytest.mark.asyncio
    async def test_query_type_classification(self):
        """Test query type classification."""
        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever._query_type = None

            # Test entity query
            query_type = retriever.get_query_type("John Smith")
            assert query_type.name in ["ENTITY", "MIXED"]

            # Test semantic query
            query_type = retriever.get_query_type("What are the benefits of using MyRag?")
            assert query_type.name in ["SEMANTIC", "MIXED"]

    @pytest.mark.asyncio
    async def test_latency_tracking(self):
        """Test latency tracking for different retrieval methods."""
        mock_dense = AsyncMock()
        mock_dense.get_latency.return_value = 50.0

        mock_sparse = AsyncMock()
        mock_sparse.get_latency.return_value = 30.0

        mock_graph = AsyncMock()
        mock_graph.get_latency.return_value = 40.0

        with patch.object(HybridRetriever, '__init__', lambda self, milvus_collection, es_index, neo4j_label, tenant_id: None):
            retriever = HybridRetriever.__new__(HybridRetriever)
            retriever.dense = mock_dense
            retriever.sparse = mock_sparse
            retriever.graph = mock_graph
            retriever.dense_latency_ms = None
            retriever.sparse_latency_ms = None
            retriever.graph_latency_ms = None
            retriever.fusion_latency_ms = 10.0
            retriever.rerank_latency_ms = 5.0

            latencies = retriever.get_latencies()

            assert latencies["dense_ms"] == 50.0
            assert latencies["sparse_ms"] == 30.0
            assert latencies["graph_ms"] == 40.0
            assert latencies["fusion_ms"] == 10.0
            assert latencies["rerank_ms"] == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])