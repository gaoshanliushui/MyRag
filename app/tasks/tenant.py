"""
Tenant Cleanup - Tasks for cleaning up tenant data
"""

from celery import shared_task
import logging
from typing import Any

from app.db.milvus import MilvusClient
from app.db.elasticsearch import ESClient
from app.db.neo4j import Neo4jClient
from app.db.redis import RedisClient
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.tenant import Tenant
from app.utils.logging import get_logger

logger = get_logger("tasks.tenant")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
async def cleanup_tenant_task(self, tenant_id: str) -> None:
    """
    Clean up all tenant data across all storage systems.

    This includes:
    - Database records (soft delete)
    - Milvus collections
    - Elasticsearch indices
    - Neo4j data
    - Redis keys
    """
    logger.info(f"Starting cleanup for tenant {tenant_id}")

    try:
        # 1. Clean Milvus collections
        milvus = MilvusClient()
        milvus.delete_tenant_collections(tenant_id)

        # 2. Clean Elasticsearch indices
        es = ESClient()
        es.delete_tenant_indices(tenant_id)

        # 3. Clean Neo4j data
        neo4j = Neo4jClient()
        neo4j.delete_tenant_data(tenant_id)

        # 4. Clean Redis keys
        redis = RedisClient()
        redis.delete_tenant_keys(tenant_id)

        # 5. Clean database records (mark as deleted)
        async with SessionLocal() as session:
            # Mark documents as deleted
            await session.execute(
                update(Document)
                .where(Document.tenant_id == tenant_id)
                .values(is_deleted=True, deleted_at=func.now())
            )

            # Mark tenant as deleted
            await session.execute(
                update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(is_deleted=True, deleted_at=func.now())
            )

            await session.commit()

        logger.info(f"Successfully cleaned up tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Failed to cleanup tenant {tenant_id}: {e}")
        raise self.retry(exc=e)