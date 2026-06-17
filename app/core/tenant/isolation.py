"""
Tenant Isolation Manager - Verifies and enforces data isolation
"""

from typing import Any, Optional
from uuid import UUID

from app.db.milvus import MilvusClient
from app.db.elasticsearch import ESClient
from app.db.neo4j import Neo4jClient
from app.db.redis import RedisClient
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.tenant import Tenant
from app.utils.exceptions import IsolationError
from app.utils.logging import get_logger

logger = get_logger("core.tenant.isolation")


class TenantIsolationManager:
    """
    Manages verification and enforcement of tenant data isolation.
    """

    async def verify_isolation(self, tenant_id: str) -> dict[str, Any]:
        """
        Verify tenant data isolation across all storage systems.

        Returns:
            dict with verification results for each system
        """
        results: dict[str, Any] = {}

        # Verify in database
        results["database"] = await self._verify_database_isolation(tenant_id)

        # Verify in Milvus
        results["milvus"] = await self._verify_milvus_isolation(tenant_id)

        # Verify in Elasticsearch
        results["elasticsearch"] = await self._verify_elasticsearch_isolation(tenant_id)

        # Verify in Neo4j
        results["neo4j"] = await self._verify_neo4j_isolation(tenant_id)

        # Verify in Redis
        results["redis"] = await self._verify_redis_isolation(tenant_id)

        # Check overall status
        all_ok = all(r["status"] == "ok" for r in results.values())
        results["overall_status"] = "ok" if all_ok else "failed"

        return results

    async def _verify_database_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Verify tenant data isolation in the database."""
        async with SessionLocal() as session:
            # Check documents
            doc_count = await session.scalar(
                select(func.count(Document.id)).where(
                    Document.tenant_id == tenant_id,
                    Document.is_deleted == False
                )
            ) or 0

            # Check cross-tenant access
            other_tenant = await session.scalar(
                select(Tenant).where(Tenant.id != tenant_id).limit(1)
            )

            if other_tenant:
                cross_docs = await session.scalar(
                    select(func.count(Document.id)).where(
                        Document.tenant_id == other_tenant.id,
                        Document.is_deleted == False
                    )
                ) or 0
            else:
                cross_docs = 0

            return {
                "status": "ok" if doc_count > 0 and cross_docs == 0 else "failed",
                "doc_count": doc_count,
                "cross_tenant_access": cross_docs
            }

    async def _verify_milvus_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Verify tenant data isolation in Milvus."""
        try:
            milvus = MilvusClient()
            result = milvus.verify_tenant_isolation(tenant_id)
            return {
                "status": "ok" if result["is_isolated"] else "failed",
                "collection_count": result["collection_count"],
                "vector_count": result["vector_count"],
                "cross_tenant_access": result["cross_tenant_access"]
            }
        except Exception as e:
            logger.error(f"Milvus isolation check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _verify_elasticsearch_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Verify tenant data isolation in Elasticsearch."""
        try:
            es = ESClient()
            result = es.verify_tenant_isolation(tenant_id)
            return {
                "status": "ok" if result["is_isolated"] else "failed",
                "index_count": result["index_count"],
                "document_count": result["document_count"],
                "cross_tenant_access": result["cross_tenant_access"]
            }
        except Exception as e:
            logger.error(f"Elasticsearch isolation check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _verify_neo4j_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Verify tenant data isolation in Neo4j."""
        try:
            neo4j = Neo4jClient()
            result = neo4j.verify_tenant_isolation(tenant_id)
            return {
                "status": "ok" if result["is_isolated"] else "failed",
                "node_count": result["node_count"],
                "relationship_count": result["relationship_count"],
                "cross_tenant_access": result["cross_tenant_access"]
            }
        except Exception as e:
            logger.error(f"Neo4j isolation check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _verify_redis_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Verify tenant data isolation in Redis."""
        try:
            redis = RedisClient()
            result = redis.verify_tenant_isolation(tenant_id)
            return {
                "status": "ok" if result["is_isolated"] else "failed",
                "key_count": result["key_count"],
                "cross_tenant_access": result["cross_tenant_access"]
            }
        except Exception as e:
            logger.error(f"Redis isolation check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }