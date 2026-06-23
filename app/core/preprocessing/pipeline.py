"""
Preprocessing Pipeline Orchestrator

Coordinates the full preprocessing flow:
1. Parse document (LangChain DocumentLoader, format-aware)
2. Clean structural noise
3. Chunk with semantic boundaries (SemanticTextSplitter — a LangChain
   `TextSplitter` subclass that wraps the project's existing
   `SemanticChunker`)
4. Generate embeddings (via `EmbeddingService` → LangChain `Embeddings`)
5. Prepare for indexing (Milvus + Elasticsearch + Neo4j)
"""

import asyncio
import time
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.core.monitoring.metrics import TASKS_TOTAL
from app.core.preprocessing.chunker import SemanticChunk, SemanticChunker, get_chunker
from app.core.preprocessing.cleaner import StructuralCleaner, get_cleaner
from app.core.preprocessing.loaders import load_document
from app.core.preprocessing.parser import DocumentParser, ParsedDocument, get_parser
from app.core.preprocessing.semantic_splitter import SemanticTextSplitter
from app.utils.embeddings import get_embedding_service
from app.utils.exceptions import DocumentProcessingError
from app.utils.logging import get_logger

logger = get_logger("core.preprocessing.pipeline")


def _extract_page_number(metadata: dict[str, Any]) -> int | None:
    """Best-effort page number extraction from LangChain Document metadata."""
    if not metadata:
        return None
    for key in ("page", "page_number", "pageNumber"):
        if key in metadata and metadata[key] is not None:
            try:
                return int(metadata[key])
            except (TypeError, ValueError):
                return None
    return None


class PreprocessingResult:
    """Result of preprocessing pipeline."""

    def __init__(
        self,
        document_id: str,
        tenant_id: str,
        filename: str,
    ):
        self.document_id = document_id
        self.tenant_id = tenant_id
        self.filename = filename
        self.chunks: list[dict[str, Any]] = []
        self.total_pages: int = 0
        self.total_chunks: int = 0
        self.total_tokens: int = 0
        self.processing_time_ms: float = 0
        self.metadata: dict[str, Any] = {}
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "filename": self.filename,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "total_tokens": self.total_tokens,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
            "errors": self.errors,
            "chunks": self.chunks,
        }


class PreprocessingPipeline:
    """
    Full preprocessing pipeline orchestrator.

    Flow:
    1. Parse → 2. Clean → 3. Chunk → 4. Embed → 5. Prepare
    """

    def __init__(
        self,
        parser: DocumentParser | None = None,
        cleaner: StructuralCleaner | None = None,
        chunker: SemanticChunker | None = None,
    ):
        self.parser = parser or get_parser()
        self.cleaner = cleaner or get_cleaner()
        self.chunker = chunker or get_chunker()
        self.embedding_service = get_embedding_service()

    async def process(
        self,
        file_path: str,
        file_type: str,
        document_id: str,
        tenant_id: str,
        progress_callback: Any | None = None,
        use_langchain: bool = True,
    ) -> PreprocessingResult:
        """
        Run full preprocessing pipeline.

        Args:
            file_path: Path to document file
            file_type: File extension
            document_id: Document UUID
            tenant_id: Tenant UUID
            progress_callback: Optional callback for progress updates
            use_langchain: When True (default), use LangChain DocumentLoader +
                SemanticTextSplitter; falls back to the legacy parser/chunker
                stack if the LangChain path raises.

        Returns:
            PreprocessingResult with chunks ready for indexing
        """
        start_time = time.time()
        result = PreprocessingResult(
            document_id=document_id,
            tenant_id=tenant_id,
            filename=file_path.split("/")[-1] if file_path else "unknown",
        )

        try:
            chunks: list[SemanticChunk]

            if use_langchain:
                try:
                    chunks = await self._process_via_langchain(
                        file_path=file_path,
                        file_type=file_type,
                        tenant_id=tenant_id,
                        document_id=document_id,
                        progress_callback=progress_callback,
                    )
                except Exception as lc_exc:
                    logger.warning(
                        f"LangChain preprocessing failed ({lc_exc}); "
                        "falling back to legacy parser/chunker"
                    )
                    chunks = await self._process_legacy(
                        file_path=file_path,
                        file_type=file_type,
                        tenant_id=tenant_id,
                        document_id=document_id,
                        progress_callback=progress_callback,
                        result=result,
                    )
            else:
                chunks = await self._process_legacy(
                    file_path=file_path,
                    file_type=file_type,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    progress_callback=progress_callback,
                    result=result,
                )

            # Stage 5: Prepare for indexing
            if progress_callback:
                await progress_callback(0.9, "Preparing for indexing")

            result.chunks = [chunk.to_dict() for chunk in chunks]
            result.total_chunks = len(chunks)
            result.total_tokens = sum(chunk.token_count for chunk in chunks)

            # Finalize
            result.processing_time_ms = (time.time() - start_time) * 1000

            if progress_callback:
                await progress_callback(1.0, "Complete")

            logger.info(
                f"Preprocessing complete: {result.filename} "
                f"→ {result.total_chunks} chunks, {result.total_tokens} tokens "
                f"in {result.processing_time_ms:.2f}ms"
            )

            return result

        except Exception as e:
            result.errors.append(str(e))
            result.processing_time_ms = (time.time() - start_time) * 1000

            logger.error(f"Preprocessing failed for {file_path}: {e}")

            raise DocumentProcessingError(
                document_id,
                "pipeline",
                str(e)
            )

    async def _parse_async(
        self,
        file_path: str,
        file_type: str,
    ) -> ParsedDocument:
        """Async wrapper for parsing."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.parser.parse,
            file_path,
            file_type,
        )

    async def _process_via_langchain(
        self,
        *,
        file_path: str,
        file_type: str,
        tenant_id: str,
        document_id: str,
        progress_callback: Any | None,
    ) -> list[SemanticChunk]:
        """LangChain-native pipeline: Loader → Cleaner → SemanticTextSplitter → Embed."""
        from pathlib import Path

        filename = Path(file_path).name

        # Stage 1: LangChain loader
        if progress_callback:
            await progress_callback(0.1, "Parsing document (LangChain)")
        loop = asyncio.get_event_loop()
        lc_docs: list[Document] = await loop.run_in_executor(
            None, load_document, file_path, file_type
        )
        TASKS_TOTAL.labels(task_name="parse", status="success").inc()

        # Stage 2: Clean (apply structural cleaner to each LangChain Document)
        if progress_callback:
            await progress_callback(0.3, "Cleaning content")
        cleaned_docs: list[Document] = []
        for d in lc_docs:
            cleaned_text = self.cleaner.clean_content(
                d.page_content, section_type="text"
            )
            if cleaned_text:
                cleaned_docs.append(
                    Document(page_content=cleaned_text, metadata=d.metadata)
                )
        TASKS_TOTAL.labels(task_name="clean", status="success").inc()

        # Stage 3: LangChain-aware semantic splitter
        if progress_callback:
            await progress_callback(0.5, "Chunking content (SemanticTextSplitter)")
        splitter = SemanticTextSplitter()
        split_docs = splitter.split_documents(cleaned_docs)

        # Build SemanticChunk objects (the rest of the pipeline expects this shape)
        chunks: list[SemanticChunk] = []
        for i, d in enumerate(split_docs):
            chunk = SemanticChunk(
                content=d.page_content,
                chunk_index=i,
                page_number=_extract_page_number(d.metadata),
                chunk_type=str(d.metadata.get("chunk_type", "text")),
                heading_text=d.metadata.get("heading_text"),
                token_count=self.chunker.estimate_tokens(d.page_content),
            )
            chunk.chunk_metadata["source_filename"] = filename
            chunk.chunk_metadata["document_id"] = document_id
            chunks.append(chunk)
        TASKS_TOTAL.labels(task_name="chunk", status="success").inc()

        # Stage 4: Batch embeddings (delegates to LangChain Embeddings)
        if progress_callback:
            await progress_callback(0.7, "Generating embeddings")
        await self._embed_batch_async(chunks, tenant_id)
        TASKS_TOTAL.labels(task_name="embed", status="success").inc()

        return chunks

    async def _process_legacy(
        self,
        *,
        file_path: str,
        file_type: str,
        tenant_id: str,
        document_id: str,
        progress_callback: Any | None,
        result: "PreprocessingResult",
    ) -> list[SemanticChunk]:
        """Legacy pipeline (preserved for fallback / existing tests)."""
        # Stage 1: Parse
        if progress_callback:
            await progress_callback(0.1, "Parsing document")
        parsed_doc = await self._parse_async(file_path, file_type)
        result.total_pages = parsed_doc.total_pages
        result.metadata = parsed_doc.metadata
        TASKS_TOTAL.labels(task_name="parse", status="success").inc()

        # Stage 2: Clean
        if progress_callback:
            await progress_callback(0.3, "Cleaning content")
        cleaned_doc = await self._clean_async(parsed_doc)
        TASKS_TOTAL.labels(task_name="clean", status="success").inc()

        # Stage 3: Chunk
        if progress_callback:
            await progress_callback(0.5, "Chunking content")
        chunks = await self._chunk_async(cleaned_doc, tenant_id)
        TASKS_TOTAL.labels(task_name="chunk", status="success").inc()

        # Stage 4: Generate embeddings (batch)
        if progress_callback:
            await progress_callback(0.7, "Generating embeddings")
        await self._embed_batch_async(chunks, tenant_id)
        TASKS_TOTAL.labels(task_name="embed", status="success").inc()

        for c in chunks:
            c.chunk_metadata.setdefault("document_id", document_id)
        return chunks

    async def _clean_async(
        self,
        parsed_doc: ParsedDocument,
    ) -> ParsedDocument:
        """Async wrapper for cleaning."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.cleaner.clean_parsed_document,
            parsed_doc,
        )

    async def _chunk_async(
        self,
        cleaned_doc: ParsedDocument,
        tenant_id: str,
    ) -> list[SemanticChunk]:
        """Async wrapper for chunking."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.chunker.chunk_parsed_document,
            cleaned_doc,
            tenant_id,
        )

    async def _embed_batch_async(
        self,
        chunks: list[SemanticChunk],
        tenant_id: str,
    ) -> None:
        """
        Generate embeddings for all chunks.

        Batches for efficiency.
        """
        # Filter chunks that need embeddings
        chunks_to_embed = [c for c in chunks if c.embedding is None]

        if not chunks_to_embed:
            return

        # Batch encode
        texts = [c.content for c in chunks_to_embed]
        embeddings = await self.embedding_service.encode_batch_async(
            texts,
            tenant_id,
            use_cache=True,
        )

        # Assign embeddings
        for chunk, embedding in zip(chunks_to_embed, embeddings):
            chunk.embedding = embedding

    def prepare_for_milvus(
        self,
        chunks: list[SemanticChunk],
        document_id: str,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """
        Prepare chunks for Milvus insertion.

        Returns list of dicts matching Milvus schema.
        """
        data = []
        for chunk in chunks:
            data.append({
                "id": str(chunk.chunk_metadata.get("chunk_id", f"{document_id}_{chunk.chunk_index}")),
                "tenant_id": tenant_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "chunk_type": chunk.chunk_type,
                "heading_text": chunk.heading_text,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "embedding": chunk.embedding,
            })
        return data

    def prepare_for_elasticsearch(
        self,
        chunks: list[SemanticChunk],
        document_id: str,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """
        Prepare chunks for Elasticsearch indexing.

        Returns list of dicts matching ES schema.
        """
        data = []
        for chunk in chunks:
            data.append({
                "id": str(chunk.chunk_metadata.get("chunk_id", f"{document_id}_{chunk.chunk_index}")),
                "tenant_id": tenant_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "chunk_type": chunk.chunk_type,
                "heading_text": chunk.heading_text,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
            })
        return data


def get_pipeline() -> PreprocessingPipeline:
    """Get preprocessing pipeline instance."""
    return PreprocessingPipeline()