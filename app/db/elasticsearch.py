"""
Elasticsearch Client

Provides BM25 keyword search with tenant isolation:
- Index management
- Document indexing with chunk metadata
- BM25 search with field weighting
- Bulk operations for efficiency
"""

import asyncio
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.config import settings
from app.utils.exceptions import ElasticsearchError
from app.utils.logging import get_logger

logger = get_logger("db.elasticsearch")


class ESClient:
    """Elasticsearch client for BM25 search."""

    def __init__(
        self,
        hosts: list[str] | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.hosts = hosts or settings.ES_HOSTS
        self.user = user or settings.ES_USER
        self.password = password or settings.ES_PASSWORD

        # Build client
        kwargs: dict[str, Any] = {"hosts": self.hosts}
        if self.user and self.password:
            kwargs["basic_auth"] = (self.user, self.password)

        self.client = AsyncElasticsearch(**kwargs)

    async def close(self) -> None:
        """Close Elasticsearch connection."""
        await self.client.close()
        logger.info("Closed Elasticsearch connection")

    async def ping(self) -> bool:
        """Check connection."""
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Elasticsearch ping failed: {e}")
            return False

    async def delete_tenant_indices(self, tenant_id: str) -> None:
        """
        Delete all Elasticsearch indices for a tenant.
        """
        try:
            # List indices with tenant prefix
            prefix = f"{settings.ES_INDEX_PREFIX}_{tenant_id}_"
            response = await self.client.indices.get(index=f"{prefix}*")
            indices = list(response.keys())
            if indices:
                # Delete all tenant indices
                await self.client.indices.delete(index=indices)
                logger.info(f"Deleted {len(indices)} indices for tenant {tenant_id}")
            else:
                logger.debug(f"No indices found for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to delete indices for tenant {tenant_id}: {e}")
            raise

    def _get_index_settings(self) -> dict[str, Any]:
        """Get index settings for BM25."""
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard",
                        },
                        "chinese_analyzer": {
                            "type": "ik_max_word",  # For Chinese text
                        },
                    },
                },
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "tenant_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "page_number": {"type": "integer"},
                    "chunk_type": {"type": "keyword"},
                    "heading_text": {
                        "type": "text",
                        "analyzer": "standard",
                        "boost": 2.0,  # Headings have higher weight
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "standard",
                    },
                    "content_hash": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                },
            },
        }

    async def create_index(self, index_name: str) -> bool:
        """Create index for tenant."""
        try:
            # Check if exists
            if await self.client.indices.exists(index=index_name):
                logger.warning(f"Index {index_name} already exists")
                return True

            # Create index
            await self.client.indices.create(
                index=index_name,
                body=self._get_index_settings(),
            )

            logger.info(f"Created index: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            raise ElasticsearchError("create_index", index_name, str(e))

    async def drop_index(self, index_name: str) -> bool:
        """Drop index."""
        try:
            if await self.client.indices.exists(index=index_name):
                await self.client.indices.delete(index=index_name)
                logger.info(f"Dropped index: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop index {index_name}: {e}")
            raise ElasticsearchError("drop_index", index_name, str(e))

    async def index_document(
        self,
        index_name: str,
        doc_id: str,
        document: dict[str, Any],
    ) -> bool:
        """Index a single document/chunk."""
        try:
            await self.client.index(
                index=index_name,
                id=doc_id,
                body=document,
            )

            logger.debug(f"Indexed document {doc_id} in {index_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to index document {doc_id}: {e}")
            raise ElasticsearchError("index_document", index_name, str(e))

    async def bulk_index(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> tuple[int, list[Any]]:
        """
        Bulk index documents.

        Returns (success_count, errors).
        """
        try:
            actions = [
                {
                    "_index": index_name,
                    "_id": doc["id"],
                    "_source": doc,
                }
                for doc in documents
            ]

            success, errors = await async_bulk(
                self.client,
                actions,
                raise_on_error=False,
            )

            if errors:
                logger.warning(f"Bulk index had {len(errors)} errors")

            logger.debug(f"Bulk indexed {success} documents in {index_name}")
            return success, errors

        except Exception as e:
            logger.error(f"Bulk index failed: {e}")
            raise ElasticsearchError("bulk_index", index_name, str(e))

    async def bm25_search(
        self,
        index_name: str,
        query: str,
        top_k: int = 50,
        tenant_id: str | None = None,
        document_ids: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        BM25 search with field weighting.

        Args:
            index_name: Target index
            query: Search query text
            top_k: Number of results
            tenant_id: Filter by tenant
            document_ids: Filter by document IDs
            filters: Additional filters
            min_score: Minimum relevance score

        Returns:
            List of results with BM25 scores
        """
        try:
            # Build query with field boosting
            # Headings get 3x boost, content gets 1x
            search_query = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "heading_text^3.0",  # Higher weight for headings
                                    "content^1.0",
                                ],
                                "type": "best_fields",
                                "operator": "or",
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": [],
                }
            }

            # Add filters
            if tenant_id:
                search_query["bool"]["filter"].append({
                    "term": {"tenant_id": tenant_id}
                })

            if document_ids:
                search_query["bool"]["filter"].append({
                    "terms": {"document_id": document_ids}
                })

            if filters:
                for field, value in filters.items():
                    if isinstance(value, list):
                        search_query["bool"]["filter"].append({
                            "terms": {field: value}
                        })
                    else:
                        search_query["bool"]["filter"].append({
                            "term": {field: value}
                        })

            # Execute search
            response = await self.client.search(
                index=index_name,
                body={
                    "query": search_query,
                    "size": top_k,
                    "min_score": min_score,
                    "_source": [
                        "id", "tenant_id", "document_id", "chunk_index",
                        "page_number", "chunk_type", "heading_text", "content",
                        "content_hash",
                    ],
                },
            )

            # Process results
            hits = response["hits"]["hits"]
            results = []
            for hit in hits:
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"],
                })

            logger.debug(f"BM25 search returned {len(results)} results from {index_name}")
            return results

        except Exception as e:
            logger.error(f"BM25 search failed in {index_name}: {e}")
            raise ElasticsearchError("search", index_name, str(e))

    async def delete_document(
        self,
        index_name: str,
        doc_id: str,
    ) -> bool:
        """Delete a single document."""
        try:
            await self.client.delete(
                index=index_name,
                id=doc_id,
            )

            logger.debug(f"Deleted document {doc_id} from {index_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            raise ElasticsearchError("delete", index_name, str(e))

    async def delete_by_query(
        self,
        index_name: str,
        query: dict[str, Any],
    ) -> int:
        """
        Delete documents matching query.

        Returns number of deleted documents.
        """
        try:
            response = await self.client.delete_by_query(
                index=index_name,
                body={"query": query},
            )

            deleted = response.get("deleted", 0)
            logger.debug(f"Deleted {deleted} documents from {index_name}")
            return deleted

        except Exception as e:
            logger.error(f"Delete by query failed: {e}")
            raise ElasticsearchError("delete_by_query", index_name, str(e))

    async def delete_by_document_id(
        self,
        index_name: str,
        document_id: str,
        tenant_id: str | None = None,
    ) -> int:
        """Delete all chunks for a document."""
        query = {"term": {"document_id": document_id}}
        if tenant_id:
            query = {"bool": {"must": [{"term": {"tenant_id": tenant_id}}, {"term": {"document_id": document_id}}]}}

        return await self.delete_by_query(index_name, query)

    async def get_index_stats(self, index_name: str) -> dict[str, Any]:
        """Get index statistics."""
        try:
            if not await self.client.indices.exists(index=index_name):
                return {"exists": False}

            stats = await self.client.indices.stats(index=index_name)
            count = await self.client.count(index=index_name)

            return {
                "exists": True,
                "name": index_name,
                "doc_count": count.get("count", 0),
                "store_size_bytes": stats["indices"][index_name]["primaries"]["store"].get("size_in_bytes", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get stats for {index_name}: {e}")
            return {"exists": False, "error": str(e)}

    async def refresh_index(self, index_name: str) -> None:
        """Refresh index for immediate searchability."""
        await self.client.indices.refresh(index=index_name)


# Singleton instance
_es_client: ESClient | None = None


async def get_es_client() -> ESClient:
    """Get Elasticsearch client singleton."""
    global _es_client
    if _es_client is None:
        _es_client = ESClient()
    return _es_client