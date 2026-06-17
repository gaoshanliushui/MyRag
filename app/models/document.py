"""
Document and Chunk ORM Models

Document represents uploaded files.
Chunk represents semantic text segments with embeddings.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, Integer, String, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin


class DocumentStatus(str, Enum):
    """Document processing status."""

    PENDING = "pending"  # Uploaded, waiting for processing
    PROCESSING = "processing"  # Currently being parsed/chunked/embedded
    INDEXING = "indexing"  # Being indexed into vector/keyword/graph stores
    COMPLETED = "completed"  # Fully processed and ready for retrieval
    FAILED = "failed"  # Processing failed
    DELETED = "deleted"  # Soft deleted


class ChunkType(str, Enum):
    """Type of text chunk."""

    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FORMULA = "formula"
    LIST = "list"
    CODE = "code"
    METADATA = "metadata"  # Header/footer, etc.


class Document(Base, TenantMixin):
    """Document model - represents uploaded files."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_tenant_created", "tenant_id", "created_at"),
    )

    # File metadata
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # pdf, docx, txt, etc.
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # bytes
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )  # storage path

    # Processing status
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    processing_task_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )  # Celery task ID

    # Document statistics
    total_pages: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Access tracking
    access_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Storage tier
    storage_tier: Mapped[str] = mapped_column(
        String(20),
        default="hot",
        nullable=False,
    )  # hot, warm, cold

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Document metadata (custom fields)
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Relationship to chunks
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "status": self.status.value,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "total_tokens": self.total_tokens,
            "access_count": self.access_count,
            "storage_tier": self.storage_tier,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Chunk(Base, TenantMixin):
    """Chunk model - semantic text segment with embedding."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tenant_document", "tenant_id", "document_id"),
        Index("ix_chunks_document_index", "document_id", "chunk_index"),
    )

    # Document reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Chunk position
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # 0-based index within document
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # source page (for PDF)

    # Content
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # SHA-256 hash for dedup

    # Chunk type and structure
    chunk_type: Mapped[ChunkType] = mapped_column(
        SQLEnum(ChunkType),
        default=ChunkType.TEXT,
        nullable=False,
    )
    heading_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # 1-6 for headings
    heading_text: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )  # heading text if this is under a heading

    # Token count
    token_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Chunk metadata (position, formatting, etc.)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Embedding info (actual vector stored in Milvus)
    embedding_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )  # ID in Milvus
    embedding_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )  # pending, completed, failed

    # Retrieval stats
    retrieval_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )  # times retrieved
    last_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Quality scores
    semantic_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )  # semantic coherence score
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )  # retrieval confidence

    # Relationship to document
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (without embedding)."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "document_id": str(self.document_id),
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "content": self.content,
            "content_hash": self.content_hash,
            "chunk_type": self.chunk_type.value,
            "heading_level": self.heading_level,
            "heading_text": self.heading_text,
            "token_count": self.token_count,
            "chunk_metadata": self.chunk_metadata,
            "retrieval_count": self.retrieval_count,
            "semantic_score": self.semantic_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_source_info(self) -> dict[str, Any]:
        """Get source document info for citation."""
        return {
            "chunk_id": str(self.id),
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "chunk_type": self.chunk_type.value,
            "heading_text": self.heading_text,
        }