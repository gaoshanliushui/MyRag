"""
Tests for the LangChain LCEL QA chain.

All tests use mocks/stubs so they don't require network access or
heavyweight model downloads.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.chains.prompts import QA_PROMPT
from app.core.chains.qa_chain import build_qa_chain, format_docs
from app.core.embeddings.bge_m3 import BGE_M3_Embeddings


# ---------- QA prompt tests --------------------------------------------------


def test_qa_prompt_has_system_and_human() -> None:
    """The QA prompt must contain system and human templates."""
    messages = QA_PROMPT.messages
    assert len(messages) == 2
    assert messages[0].prompt.template  # system prompt
    assert "{context}" in messages[1].prompt.template
    assert "{question}" in messages[1].prompt.template


# ---------- format_docs tests ------------------------------------------------


def test_format_docs_empty() -> None:
    assert format_docs([]) == "（无相关参考文档）"


def test_format_docs_with_metadata() -> None:
    docs = [
        Document(
            page_content="Hello",
            metadata={"page_number": 3, "document_id": "doc-1"},
        )
    ]
    out = format_docs(docs)
    assert "[1]" in out
    assert "Hello" in out
    assert "page=3" in out


# ---------- build_qa_chain tests --------------------------------------------


class _StubRetriever:
    """Stand-in for an `EnsembleRetriever` that returns a fixed doc list."""

    def __init__(self, docs: list[Document]):
        self._docs = docs

    def invoke(self, query: str, **kwargs: Any) -> list[Document]:
        return self._docs

    async def ainvoke(self, query: str, **kwargs: Any) -> list[Document]:
        return self._docs


@pytest.fixture
def tenant_stub() -> MagicMock:
    tenant = MagicMock()
    tenant.id = "tenant-test"
    tenant.get_milvus_collection.return_value = "coll"
    tenant.get_es_index.return_value = "idx"
    tenant.get_neo4j_label.return_value = "lbl"
    return tenant


@pytest.fixture
def stubbed_chain(monkeypatch, tenant_stub):
    """Patch external collaborators so `build_qa_chain` runs in-memory."""
    docs = [
        Document(
            page_content="LangChain 是一个 LLM 应用框架。",
            metadata={"page_number": 1, "document_id": "doc-A"},
        ),
        Document(
            page_content="RAG = Retrieval-Augmented Generation。",
            metadata={"page_number": 2, "document_id": "doc-B"},
        ),
    ]

    # Stub ensemble retriever
    monkeypatch.setattr(
        "app.core.chains.qa_chain.build_ensemble_retriever",
        lambda *_a, **_kw: _StubRetriever(docs),
    )

    # Stub chat model
    monkeypatch.setattr(
        "app.core.chains.qa_chain.get_chat_model",
        lambda: FakeListChatModel(
            responses=["这是基于参考文档的回答：LangChain 是 LLM 应用框架。"]
        ),
    )
    return tenant_stub, docs


@pytest.mark.asyncio
async def test_qa_chain_returns_answer(stubbed_chain) -> None:
    tenant, _ = stubbed_chain
    chain = build_qa_chain(
        tenant, weights={"dense": 0.4, "sparse": 0.3, "graph": 0.3}
    )
    answer = await chain.ainvoke("什么是 LangChain？")
    assert "LangChain" in answer


def test_qa_chain_is_runnable(stubbed_chain) -> None:
    """The chain must be a LangChain `Runnable`."""
    tenant, _ = stubbed_chain
    chain = build_qa_chain(tenant, weights={"dense": 0.4, "sparse": 0.3, "graph": 0.3})
    from langchain_core.runnables import Runnable

    assert isinstance(chain, Runnable)


# ---------- Embeddings sanity check ----------------------------------------


def test_bge_m3_class_is_langchain_embeddings() -> None:
    """BGE_M3_Embeddings must satisfy the LangChain `Embeddings` interface."""
    from langchain_core.embeddings import Embeddings

    assert issubclass(BGE_M3_Embeddings, Embeddings)
    fake = FakeEmbeddings(size=4)
    out = fake.embed_query("hello")
    assert isinstance(out, list)
    assert len(out) == 4