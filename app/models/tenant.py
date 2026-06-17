"""
Tenant ORM Model

Multi-tenant isolation with per-tenant Milvus collections,
Elasticsearch indices, and Neo4j subgraphs.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    """Tenant model for multi-tenant isolation."""

    __tablename__ = "tenants"

    # Identity
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # API Authentication
    api_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    api_key_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
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

    # Resource names in external services
    milvus_collection_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    es_index_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    neo4j_label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Quotas
    max_documents: Mapped[int] = mapped_column(
        Integer,
        default=10000,
        nullable=False,
    )
    max_storage_mb: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
    )
    max_queries_per_day: Mapped[int] = mapped_column(
        Integer,
        default=10000,
        nullable=False,
    )

    # Current usage (cached)
    current_documents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    current_storage_mb: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    queries_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    last_query_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Contact/Admin info
    admin_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"

    def get_milvus_collection(self) -> str:
        """Get tenant's Milvus collection name."""
        return self.milvus_collection_name

    def get_es_index(self) -> str:
        """Get tenant's Elasticsearch index name."""
        return self.es_index_name

    def get_neo4j_label(self) -> str:
        """Get tenant's Neo4j node label."""
        return self.neo4j_label

    def check_quota(self, quota_type: str, current: int) -> bool:
        """Check if quota limit is exceeded."""
        limits = {
            "documents": self.max_documents,
            "storage": self.max_storage_mb,
            "queries": self.max_queries_per_day,
        }
        return current < limits.get(quota_type, 0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding sensitive fields)."""
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "milvus_collection_name": self.milvus_collection_name,
            "es_index_name": self.es_index_name,
            "neo4j_label": self.neo4j_label,
            "config": self.config,
            "max_documents": self.max_documents,
            "max_storage_mb": self.max_storage_mb,
            "max_queries_per_day": self.max_queries_per_day,
            "current_documents": self.current_documents,
            "current_storage_mb": self.current_storage_mb,
            "queries_today": self.queries_today,
            "admin_email": self.admin_email,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }