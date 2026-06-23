"""
Semantic Text Splitter (LangChain `TextSplitter` wrapper)

Wraps the project's existing `SemanticChunker` algorithm (semantic boundary
detection via embedding similarity) into a LangChain `TextSplitter` so that
it composes with LangChain pipelines and loaders.

Note: NOT to be confused with `langchain_experimental.text_splitter.SemanticChunker`,
which is a different implementation.
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

from app.config import settings
from app.core.preprocessing.chunker import SemanticChunker
from app.utils.logging import get_logger

logger = get_logger("core.preprocessing.semantic_splitter")


class SemanticTextSplitter(TextSplitter):
    """Two-stage splitter: coarse RecursiveCharacter → fine semantic boundary."""

    def __init__(
        self,
        min_chunk_tokens: int | None = None,
        max_chunk_tokens: int | None = None,
        min_overlap: int | None = None,
        max_overlap: int | None = None,
        boundary_threshold: float | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        min_c = min_chunk_tokens or settings.CHUNK_MIN_SIZE
        max_c = max_chunk_tokens or settings.CHUNK_MAX_SIZE
        min_o = min_overlap or settings.CHUNK_OVERLAP_MIN
        max_o = max_overlap or settings.CHUNK_OVERLAP_MAX
        threshold = boundary_threshold or settings.SEMANTIC_BOUNDARY_THRESHOLD
        overlap = chunk_overlap if chunk_overlap is not None else min_o

        super().__init__(chunk_size=max_c, chunk_overlap=overlap)
        self._inner = SemanticChunker(
            min_chunk_tokens=min_c,
            max_chunk_tokens=max_c,
            min_overlap=min_o,
            max_overlap=max_o,
            boundary_threshold=threshold,
        )
        self._base = RecursiveCharacterTextSplitter(
            chunk_size=max_c,
            chunk_overlap=overlap,
        )

    def split_text(self, text: str) -> list[str]:  # type: ignore[override]
        """Split text into chunks via coarse-then-fine semantic chunking."""
        coarse_chunks = self._base.split_text(text)
        if not coarse_chunks:
            return []
        joined = "\n\n".join(coarse_chunks)
        chunks = self._inner.chunk_text(joined)
        return [c.content for c in chunks]

    def split_documents(self, documents: list[Document]) -> list[Document]:  # type: ignore[override]
        """LangChain-style document splitter."""
        results: list[Document] = []
        for doc in documents:
            for chunk_text in self.split_text(doc.page_content):
                meta = dict(doc.metadata)
                results.append(Document(page_content=chunk_text, metadata=meta))
        return results