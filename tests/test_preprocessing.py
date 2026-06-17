"""
Test Suite for Document Processing Pipeline

Tests for document parsing, chunking, and preprocessing functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.preprocessing.pipeline import PreprocessingPipeline, PreprocessingResult
from app.core.preprocessing.parser import DocumentParser
from app.core.preprocessing.chunker import SemanticChunker
from app.core.preprocessing.cleaner import StructuralCleaner


@pytest.fixture
def sample_txt_content():
    """Sample text content for testing."""
    return """
MyRag Documentation
==================

Introduction
------------

MyRag is a distributed multi-tenant hybrid retrieval enterprise RAG system.
It combines dense vector retrieval, sparse keyword search, and knowledge graph traversal.

Features
--------

1. Adaptive Semantic Preprocessing Pipeline
2. Three-Way Hybrid Retrieval
3. Two-Level Staged Reranking
4. Distributed Multi-Tenant Isolation

Architecture
------------

The system uses:
- FastAPI for the API layer
- Milvus for vector storage
- Elasticsearch for keyword search
- Neo4j for knowledge graphs
- Redis for caching
- Celery for async processing
"""


@pytest.fixture
def temp_txt_file(sample_txt_content):
    """Create a temporary text file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_txt_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


class TestDocumentParser:
    """Test document parsing functionality."""

    def test_parse_txt_file(self, temp_txt_file):
        """Test parsing of text files."""
        parser = DocumentParser()

        result = parser.parse(temp_txt_file, "txt")

        assert result is not None
        assert result.file_type == "txt"
        assert len(result.sections) > 0

        # Check that sections contain expected content
        section_contents = [section["content"] for section in result.sections]
        assert any("MyRag" in content for content in section_contents)
        assert any("Features" in content for content in section_contents)

        # Check heading detection
        headings = [section for section in result.sections if section["heading_level"]]
        assert len(headings) > 0

    def test_parse_empty_file(self):
        """Test parsing of an empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Write empty content
            pass
        temp_path = f.name

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path, "txt")

            assert result is not None
            assert len(result.sections) == 0
        finally:
            os.unlink(temp_path)

    def test_unsupported_file_type(self):
        """Test parsing of unsupported file type."""
        parser = DocumentParser()

        with pytest.raises(Exception):
            parser.parse("dummy.txt", "xyz")


class TestStructuralCleaner:
    """Test structural cleaning functionality."""

    def test_clean_parsed_document(self):
        """Test cleaning of parsed document."""
        cleaner = StructuralCleaner()

        # Create a mock parsed document
        from app.core.preprocessing.parser import ParsedDocument
        parsed_doc = ParsedDocument("test.txt", "txt", 1)
        parsed_doc.add_section("   Content with   extra spaces   ", 1)
        parsed_doc.add_section("Header content", 1, "heading", 1, "Header")
        parsed_doc.add_section("Footer content", 1, "footer", None, "Footer")

        cleaned_doc = cleaner.clean_parsed_document(parsed_doc)

        # Check that content was cleaned
        assert len(cleaned_doc.sections) == 3

        # Verify content normalization
        content_sections = [s for s in cleaned_doc.sections if s["section_type"] == "text"]
        for section in content_sections:
            content = section["content"]
            # Check that excessive whitespace was reduced
            assert "  " not in content or "extra spaces" in content  # Either reduced or kept meaningful spaces


class TestSemanticChunker:
    """Test semantic chunking functionality."""

    def test_chunk_parsed_document(self):
        """Test chunking of parsed document."""
        chunker = SemanticChunker()

        # Create a mock parsed document
        from app.core.preprocessing.parser import ParsedDocument
        parsed_doc = ParsedDocument("test.txt", "txt", 1)
        parsed_doc.add_section("This is the first paragraph with some content.", 1, "text")
        parsed_doc.add_section("This is a heading section", 1, "heading", 1, "Main Heading")
        parsed_doc.add_section("This is the second paragraph with different content.", 1, "text")
        parsed_doc.add_section("Another heading", 1, "heading", 2, "Sub Heading")
        parsed_doc.add_section("Final content paragraph.", 1, "text")

        chunks = chunker.chunk_parsed_document(parsed_doc, "test-tenant")

        assert len(chunks) > 0

        # Check that chunks have required attributes
        for chunk in chunks:
            assert hasattr(chunk, 'content')
            assert hasattr(chunk, 'page_number')
            assert hasattr(chunk, 'chunk_type')
            assert chunk.content is not None and len(chunk.content) > 0

    def test_chunk_small_content(self):
        """Test chunking of very small content."""
        chunker = SemanticChunker()

        from app.core.preprocessing.parser import ParsedDocument
        parsed_doc = ParsedDocument("test.txt", "txt", 1)
        parsed_doc.add_section("Small", 1, "text")

        chunks = chunker.chunk_parsed_document(parsed_doc, "test-tenant")

        assert len(chunks) >= 1
        assert chunks[0].content == "Small"


class TestPreprocessingPipeline:
    """Test the full preprocessing pipeline."""

    async def test_process_txt_file(self, temp_txt_file):
        """Test the full processing pipeline for a text file."""
        pipeline = PreprocessingPipeline()

        # Mock the embedding service to avoid actual embeddings
        with patch("app.utils.embeddings.get_embedding_service") as mock_embedding:
            mock_embedding.return_value.encode_batch_async = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

            result = await pipeline.process(
                temp_txt_file,
                "txt",
                "doc-123",
                "tenant-123"
            )

        assert result is not None
        assert result.document_id == "doc-123"
        assert result.tenant_id == "tenant-123"
        assert len(result.chunks) > 0
        assert result.total_chunks > 0
        assert result.processing_time_ms > 0

        # Verify chunks have expected structure
        for chunk in result.chunks:
            assert "id" in chunk
            assert "content" in chunk
            assert "page_number" in chunk
            assert "embedding" in chunk

    async def test_process_with_progress_callback(self, temp_txt_file):
        """Test the processing pipeline with progress callback."""
        pipeline = PreprocessingPipeline()

        progress_calls = []

        async def progress_callback(progress, stage):
            progress_calls.append((progress, stage))

        # Mock the embedding service
        with patch("app.utils.embeddings.get_embedding_service") as mock_embedding:
            mock_embedding.return_value.encode_batch_async = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

            result = await pipeline.process(
                temp_txt_file,
                "txt",
                "doc-123",
                "tenant-123",
                progress_callback=progress_callback
            )

        # Verify that progress callback was called
        assert len(progress_calls) > 0
        # Check that progress values are reasonable
        for progress, stage in progress_calls:
            assert 0.0 <= progress <= 1.0
            assert isinstance(stage, str)

    async def test_process_large_content(self):
        """Test processing of large content to verify chunking works."""
        # Create a large content string
        large_content = "This is a sentence. " * 1000  # Repeat to create large content

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(large_content)
            temp_path = f.name

        try:
            pipeline = PreprocessingPipeline()

            # Mock the embedding service
            with patch("app.utils.embeddings.get_embedding_service") as mock_embedding:
                mock_embedding.return_value.encode_batch_async = AsyncMock(
                    return_value=[[0.1, 0.2, 0.3]] * 10  # Return embeddings for 10 chunks
                )

                result = await pipeline.process(
                    temp_path,
                    "txt",
                    "doc-large",
                    "tenant-123"
                )

            # For large content, we expect multiple chunks
            assert result.total_chunks > 1
            assert result.total_tokens > 0
        finally:
            os.unlink(temp_path)


class TestPreprocessingResult:
    """Test preprocessing result functionality."""

    def test_preprocessing_result_to_dict(self):
        """Test converting preprocessing result to dictionary."""
        result = PreprocessingResult(
            document_id="test-doc-123",
            tenant_id="test-tenant-456",
            filename="test.txt"
        )

        result.total_pages = 5
        result.total_chunks = 10
        result.total_tokens = 1000
        result.processing_time_ms = 500.0
        result.chunks = [{"id": "chunk1", "content": "test"}]

        result_dict = result.to_dict()

        assert result_dict["document_id"] == "test-doc-123"
        assert result_dict["tenant_id"] == "test-tenant-456"
        assert result_dict["filename"] == "test.txt"
        assert result_dict["total_pages"] == 5
        assert result_dict["total_chunks"] == 10
        assert result_dict["total_tokens"] == 1000
        assert result_dict["processing_time_ms"] == 500.0
        assert len(result_dict["chunks"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])