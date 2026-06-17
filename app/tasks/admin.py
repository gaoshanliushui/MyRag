"""
Admin Tasks - Background tasks for admin operations
"""

from celery import shared_task
from typing import Any
import time

from app.db.milvus import MilvusClient
from app.db.elasticsearch import ESClient
from app.db.neo4j import Neo4jClient
from app.db.redis import RedisClient
from app.utils.logging import get_logger

logger = get_logger("tasks.admin")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cleanup_tenant_task(self, tenant_id: str) -> None:
    """
    Clean up tenant data across all storage systems.

    This task is called when a tenant is deleted to remove:
    - Milvus collections
    - Elasticsearch indices
    - Neo4j subgraphs
    - Redis keys
    """
    try:
        logger.info(f"Starting cleanup for tenant {tenant_id}")
        start_time = time.time()

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

        duration = time.time() - start_time
        logger.info(f"Completed cleanup for tenant {tenant_id} in {duration:.2f}s")

    except Exception as e:
        logger.error(f"Failed to cleanup tenant {tenant_id}: {e}")
        raise self.retry(exc=e)