"""
Semantic Chunker

Adaptive semantic boundary detection and chunking:
- Analyzes semantic similarity between adjacent sections
- Dynamic chunk size based on content coherence
- Preserves heading hierarchy
- Handles tables and special content
"""

import re
import hashlib
from typing import Any

from app.config import settings
from app.utils.embeddings import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger("core.preprocessing.chunker")


class SemanticChunk:
    """Semantic chunk with metadata."""

    def __init__(
        self,
        content: str,
        chunk_index: int,
        page_number: int | None = None,
        chunk_type: str = "text",
        heading_level: int | None = None,
        heading_text: str | None = None,
        token_count: int = 0,
        embedding: list[float] | None = None,
    ):
        self.content = content
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.chunk_type = chunk_type
        self.heading_level = heading_level
        self.heading_text = heading_text
        self.token_count = token_count
        self.embedding = embedding
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()
        self.chunk_metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "chunk_type": self.chunk_type,
            "heading_level": self.heading_level,
            "heading_text": self.heading_text,
            "token_count": self.token_count,
            "content_hash": self.content_hash,
            "embedding": self.embedding,
            "chunk_metadata": self.chunk_metadata,
        }


class SemanticChunker:
    """
    Semantic boundary detection chunker.

    Key features:
    - Detects semantic boundaries using embedding similarity
    - Dynamic chunk size (min-max range)
    - Preserves heading hierarchy for context
    - Handles tables, formulas, lists as atomic units
    """

    def __init__(
        self,
        min_chunk_tokens: int = None,
        max_chunk_tokens: int = None,
        min_overlap: int = None,
        max_overlap: int = None,
        boundary_threshold: float = None,
    ):
        self.min_chunk_tokens = min_chunk_tokens or settings.CHUNK_MIN_SIZE
        self.max_chunk_tokens = max_chunk_tokens or settings.CHUNK_MAX_SIZE
        self.min_overlap = min_overlap or settings.CHUNK_OVERLAP_MIN
        self.max_overlap = max_overlap or settings.CHUNK_OVERLAP_MAX
        self.boundary_threshold = boundary_threshold or settings.SEMANTIC_BOUNDARY_THRESHOLD
        self.embedding_service = get_embedding_service()

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Simple estimation: ~4 chars per token for Chinese/English mix.
        """
        # More accurate: count words and characters
        chinese_chars = len(re.findall(r"[^\x00-\xff]", text))
        english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
        # Chinese: ~1 token per char, English: ~1 token per word
        return chinese_chars + english_words + (len(text) - chinese_chars) // 4

    def compute_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Compute semantic similarity between two texts.

        Uses cosine similarity of embeddings.
        """
        if not text1 or not text2:
            return 0.0

        emb1 = self.embedding_service.encode_single(text1)
        emb2 = self.embedding_service.encode_single(text2)

        # Cosine similarity (already normalized)
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        return dot_product

    def detect_boundary(
        self,
        prev_text: str,
        curr_text: str,
    ) -> bool:
        """
        Detect if there's a semantic boundary between sections.

        Returns True if similarity is below threshold.
        """
        similarity = self.compute_similarity(prev_text, curr_text)
        return similarity < self.boundary_threshold

    def chunk_parsed_document(
        self,
        parsed_doc: Any,
        tenant_id: str | None = None,
    ) -> list[SemanticChunk]:
        """
        Chunk a parsed document.

        Args:
            parsed_doc: ParsedDocument from parser
            tenant_id: Tenant for caching embeddings

        Returns:
            List of SemanticChunks
        """
        chunks: list[SemanticChunk] = []
        current_content: list[str] = []
        current_tokens = 0
        current_page = None
        current_heading = None
        chunk_index = 0

        sections = parsed_doc.sections

        for i, section in enumerate(sections):
            content = section["content"]
            section_type = section.get("section_type", "text")
            page_number = section.get("page_number")
            heading_level = section.get("heading_level")
            heading_text = section.get("heading_text")

            # Tables, formulas are atomic - create separate chunk
            if section_type in ("table", "formula"):
                if current_content:
                    # Flush current chunk first
                    chunk = self._create_chunk(
                        current_content,
                        chunk_index,
                        current_page,
                        "text",
                        current_heading,
                        tenant_id,
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_content = []
                    current_tokens = 0

                # Create atomic chunk for table/formula
                chunk = self._create_chunk(
                    [content],
                    chunk_index,
                    page_number,
                    section_type,
                    heading_text,
                    tenant_id,
                )
                chunks.append(chunk)
                chunk_index += 1
                continue

            # Heading - flush current and start new
            if section_type == "heading" and heading_level:
                if current_content:
                    chunk = self._create_chunk(
                        current_content,
                        chunk_index,
                        current_page,
                        "text",
                        current_heading,
                        tenant_id,
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                current_content = [content]
                current_tokens = self.estimate_tokens(content)
                current_heading = heading_text
                current_page = page_number
                continue

            # Regular text - accumulate
            text_tokens = self.estimate_tokens(content)

            # Check semantic boundary
            if current_content and len(current_content) > 0:
                prev_text = current_content[-1]
                is_boundary = self.detect_boundary(prev_text, content)

                # Also check if adding would exceed max
                would_exceed = (current_tokens + text_tokens) > self.max_chunk_tokens

                if is_boundary or would_exceed:
                    # Flush current chunk
                    if current_tokens >= self.min_chunk_tokens or is_boundary:
                        chunk = self._create_chunk(
                            current_content,
                            chunk_index,
                            current_page,
                            "text",
                            current_heading,
                            tenant_id,
                        )
                        chunks.append(chunk)
                        chunk_index += 1

                        # Start new with overlap if needed
                        overlap_content = self._get_overlap(current_content)
                        current_content = overlap_content
                        current_tokens = sum(self.estimate_tokens(c) for c in overlap_content)

            # Add content
            current_content.append(content)
            current_tokens += text_tokens

            if current_page is None and page_number:
                current_page = page_number

        # Flush remaining
        if current_content:
            chunk = self._create_chunk(
                current_content,
                chunk_index,
                current_page,
                "text",
                current_heading,
                tenant_id,
            )
            chunks.append(chunk)

        logger.info(
            f"Chunked {parsed_doc.filename}: {len(chunks)} chunks "
            f"from {len(sections)} sections"
        )

        return chunks

    def _create_chunk(
        self,
        content_parts: list[str],
        chunk_index: int,
        page_number: int | None,
        chunk_type: str,
        heading_text: str | None,
        tenant_id: str | None,
    ) -> SemanticChunk:
        """Create a SemanticChunk from content parts."""
        content = "\n\n".join(content_parts).strip()
        token_count = self.estimate_tokens(content)

        # Get embedding
        embedding = None
        if tenant_id:
            embedding = self.embedding_service.encode_single(content)
        else:
            embedding = self.embedding_service.encode_single(content)

        chunk = SemanticChunk(
            content=content,
            chunk_index=chunk_index,
            page_number=page_number,
            chunk_type=chunk_type,
            heading_text=heading_text,
            token_count=token_count,
            embedding=embedding,
        )

        return chunk

    def _get_overlap(self, content_parts: list[str]) -> list[str]:
        """
        Get overlap content from current chunk.

        Ensures smooth transition between chunks.
        """
        if not content_parts:
            return []

        # Take last portion that fits min overlap
        overlap_parts: list[str] = []
        overlap_tokens = 0

        for part in reversed(content_parts[-3:]):  # Max 3 parts for overlap
            part_tokens = self.estimate_tokens(part)
            if overlap_tokens + part_tokens <= self.max_overlap:
                overlap_parts.insert(0, part)
                overlap_tokens += part_tokens
            else:
                break

        return overlap_parts if overlap_tokens >= self.min_overlap else []

    def chunk_text(
        self,
        text: str,
        chunk_type: str = "text",
        page_number: int | None = None,
        heading_text: str | None = None,
        tenant_id: str | None = None,
    ) -> list[SemanticChunk]:
        """
        Chunk plain text without parsed document.

        Uses sliding window with semantic boundary detection.
        """
        # Split into sentences/paragraphs
        paragraphs = re.split(r"\n\s*\n", text)

        # Create synthetic sections
        sections = [{"content": p.strip(), "section_type": "text"} for p in paragraphs if p.strip()]

        # Create synthetic parsed doc
        from app.core.preprocessing.parser import ParsedDocument
        synthetic_doc = ParsedDocument(
            filename="text_input",
            file_type="txt",
            total_pages=1,
        )
        synthetic_doc.sections = sections

        return self.chunk_parsed_document(synthetic_doc, tenant_id)


def get_chunker() -> SemanticChunker:
    """Get semantic chunker instance."""
    return SemanticChunker()