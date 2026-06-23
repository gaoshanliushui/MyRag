"""
Tests for the LangChain-based retrievers and the preprocessing loader.

All tests use mocks/stubs so no external service (Milvus/ES/Neo4j/HF Hub)
is contacted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings

from app.core.preprocessing.loaders import get_supported_types, load_document
from app.core.retrieval.langchain_retrievers import (
    ESTenantRetriever,
    MilvusTenantRetriever,
    Neo4jTenantRetriever,
)


# ---------- Retriever: hit → Document conversion ---------------------------


def _fake_embedding() -> FakeEmbeddings:
    return FakeEmbeddings(size=8)


@pytest.mark.asyncio
async def test_milvus_retriever_returns_documents() -> None:
    milvus = MagicMock()
    milvus.search_vectors_async = AsyncMock(
        return_value=[
            {
                "id": "c1",
                "document_id": "d1",
                "chunk_index": 0,
                "page_number": 1,
                "chunk_type": "text",
                "heading_text": None,
                "content": "Hello world",
                "score": 0.9,
            }
        ]
    )
    r = MilvusTenantRetriever(
        collection_name="coll",
        tenant_id="t1",
        embedding=_fake_embedding(),
        milvus=milvus,
        top_k=5,
    )
    docs = await r._aget_relevant_documents("query")
    assert len(docs) == 1
    assert docs[0].page_content == "Hello world"
    assert docs[0].metadata["channel"] == "dense"
    assert docs[0].metadata["dense_score"] == 0.9


@pytest.mark.asyncio
async def test_milvus_retriever_returns_empty_on_failure() -> None:
    milvus = MagicMock()
    milvus.search_vectors_async = AsyncMock(side_effect=RuntimeError("down"))
    r = MilvusTenantRetriever(
        collection_name="coll",
        tenant_id="t1",
        embedding=_fake_embedding(),
        milvus=milvus,
    )
    docs = await r._aget_relevant_documents("query")
    assert docs == []


@pytest.mark.asyncio
async def test_es_retriever_returns_documents() -> None:
    es = MagicMock()
    es.bm25_search = AsyncMock(
        return_value=[
            {
                "id": "c2",
                "document_id": "d2",
                "chunk_index": 1,
                "page_number": 2,
                "chunk_type": "text",
                "heading_text": None,
                "content": "BM25 result",
                "score": 1.5,
            }
        ]
    )
    r = ESTenantRetriever(
        index_name="idx",
        tenant_id="t1",
        es=es,
        top_k=5,
    )
    docs = await r._aget_relevant_documents("query")
    assert len(docs) == 1
    assert docs[0].page_content == "BM25 result"
    assert docs[0].metadata["channel"] == "sparse"


@pytest.mark.asyncio
async def test_neo4j_retriever_extracts_entities_and_calls_neo4j() -> None:
    neo4j = MagicMock()
    neo4j.multi_hop_search_async = AsyncMock(
        return_value=[
            {
                "chunk_id": "c3",
                "document_id": "d3",
                "chunk_index": 0,
                "page_number": 1,
                "content_preview": "Graph hit",
                "score": 0.8,
            }
        ]
    )
    r = Neo4jTenantRetriever(
        label="L",
        tenant_id="t1",
        neo4j=neo4j,
        top_k=5,
    )
    docs = await r._aget_relevant_documents('Find "Foo"')
    assert len(docs) == 1
    assert docs[0].metadata["channel"] == "graph"
    assert docs[0].page_content == "Graph hit"


@pytest.mark.asyncio
async def test_neo4j_retriever_returns_empty_when_no_entities() -> None:
    neo4j = MagicMock()
    neo4j.multi_hop_search_async = AsyncMock(return_value=[])
    r = Neo4jTenantRetriever(label="L", tenant_id="t1", neo4j=neo4j)
    docs = await r._aget_relevant_documents("普通问句没有任何实体")
    assert docs == []


# ---------- Semantic splitter (with stubbed embeddings) --------------------


def test_semantic_splitter_with_fake_embedding(monkeypatch) -> None:
    """Splitter must work with fake embeddings (no HF downloads)."""
    from app.core.preprocessing import semantic_splitter as ss_mod

    monkeypatch.setattr(ss_mod, "SemanticChunker", _FakeChunker)
    from app.core.preprocessing.semantic_splitter import SemanticTextSplitter

    text = ("第一段内容。\n\n" * 30) + ("第二段内容。\n\n" * 30) + ("第三段内容。\n\n" * 30)
    splitter = SemanticTextSplitter(
        min_chunk_tokens=20,
        max_chunk_tokens=120,
        chunk_overlap=10,
    )
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert isinstance(c, str)
        assert len(c) > 0


def test_semantic_splitter_handles_empty_text(monkeypatch) -> None:
    from app.core.preprocessing import semantic_splitter as ss_mod

    monkeypatch.setattr(ss_mod, "SemanticChunker", _FakeChunker)
    from app.core.preprocessing.semantic_splitter import SemanticTextSplitter

    splitter = SemanticTextSplitter()
    assert splitter.split_text("") == []


class _FakeChunker:
    """Lightweight SemanticChunker stub that uses `RecursiveCharacterTextSplitter` only."""

    def __init__(self, *args, **kwargs):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=kwargs.get("max_chunk_tokens") or 1000,
            chunk_overlap=kwargs.get("min_overlap") or 50,
        )

    def chunk_text(self, text: str):
        from app.core.preprocessing.chunker import SemanticChunk

        return [
            SemanticChunk(content=t, chunk_index=i, token_count=len(t))
            for i, t in enumerate(self._splitter.split_text(text))
        ]


# ---------- Document loaders ------------------------------------------------


def test_loaders_registry_lists_supported_types() -> None:
    types = get_supported_types()
    assert "txt" in types
    assert "md" in types


def test_load_document_txt(tmp_path: Path) -> None:
    f = tmp_path / "sample.txt"
    f.write_text("Hello from MyRag.", encoding="utf-8")
    docs = load_document(str(f), "txt")
    assert len(docs) >= 1
    assert "MyRag" in docs[0].page_content
    assert docs[0].metadata.get("source") == "sample.txt"