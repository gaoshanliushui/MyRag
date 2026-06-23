"""
Milvus Vector Database Client

Provides high-level interface for vector operations:
- Collection management (create, drop, load, release)
- Vector insertion with metadata
- ANN similarity search
- Tenant-isolated collections
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)
from pymilvus.orm.types import CONSISTENCY_STRONG

from app.config import settings
from app.utils.exceptions import MilvusError
from app.utils.logging import get_logger

logger = get_logger("db.milvus")

# Thread pool for sync Milvus operations in async context
_executor = ThreadPoolExecutor(max_workers=4)


class MilvusClient:
    """Milvus client with tenant-isolated collections."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        alias: str = None,
    ):
        self.host = host or settings.MILVUS_HOST
        self.port = port or settings.MILVUS_PORT
        self.alias = alias or settings.MILVUS_ALIAS
        self._connected = False

    def connect(self) -> None:
        """Connect to Milvus server."""
        if self._connected:
            return

        try:
            connections.connect(
                alias=self.alias,
                host=self.host,
                port=self.port,
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise MilvusError("connect", "default", str(e))

    def disconnect(self) -> None:
        """Disconnect from Milvus server."""
        if self._connected:
            connections.disconnect(self.alias)
            self._connected = False
            logger.info("Disconnected from Milvus")

    def check_connection(self) -> bool:
        """Check if connection is active."""
        try:
            self.connect()
            # Try to list collections as connection test
            utility.list_collections(using=self.alias)
            return True
        except Exception as e:
            logger.error(f"Milvus connection check failed: {e}")
            return False

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run sync function in thread pool."""
        self.connect()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, func, *args, **kwargs)

    def _get_collection_schema(self) -> CollectionSchema:
        """Get schema for chunk collection."""
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
            FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=36),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=36),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="page_number", dtype=DataType.INT64, nullable=True),
            FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=20),
            FieldSchema(name="heading_text", dtype=DataType.VARCHAR, max_length=500, nullable=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8000),
            FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIMENSION),
        ]

        schema = CollectionSchema(
            fields=fields,
            description="Document chunks with embeddings",
        )
        return schema

    def create_collection(
        self,
        collection_name: str,
        description: str = "Tenant chunk collection",
    ) -> Collection:
        """Create a new collection for tenant."""
        self.connect()

        try:
            # Check if exists
            if utility.has_collection(collection_name, using=self.alias):
                logger.warning(f"Collection {collection_name} already exists")
                return Collection(collection_name, using=self.alias)

            schema = self._get_collection_schema()
            collection = Collection(
                name=collection_name,
                schema=schema,
                description=description,
                using=self.alias,
            )

            # Create HNSW index for vector search
            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {
                    "M": 16,
                    "efConstruction": 256,
                },
            }
            collection.create_index(
                field_name="embedding",
                index_params=index_params,
            )

            # Load collection to memory
            collection.load()

            logger.info(f"Created collection: {collection_name}")
            return collection

        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            raise MilvusError("create_collection", collection_name, str(e))

    async def create_collection_async(self, collection_name: str) -> Collection:
        """Async wrapper for collection creation."""
        return await self._run_sync(self.create_collection, collection_name)

    def drop_collection(self, collection_name: str) -> None:
        """Drop a collection."""
        self.connect()

        try:
            if utility.has_collection(collection_name, using=self.alias):
                utility.drop_collection(collection_name, using=self.alias)
                logger.info(f"Dropped collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to drop collection {collection_name}: {e}")
            raise MilvusError("drop_collection", collection_name, str(e))

    async def drop_collection_async(self, collection_name: str) -> None:
        """Async wrapper for dropping collection."""
        await self._run_sync(self.drop_collection, collection_name)

    def insert_vectors(
        self,
        collection_name: str,
        data: list[dict[str, Any]],
    ) -> list[str]:
        """
        Insert vectors with metadata.

        Args:
            collection_name: Target collection
            data: List of dicts with keys matching schema fields

        Returns:
            List of inserted IDs
        """
        self.connect()

        try:
            collection = Collection(collection_name, using=self.alias)

            # Prepare data in column format
            columns = {
                "id": [d["id"] for d in data],
                "tenant_id": [d["tenant_id"] for d in data],
                "document_id": [d["document_id"] for d in data],
                "chunk_index": [d["chunk_index"] for d in data],
                "page_number": [d.get("page_number") for d in data],
                "chunk_type": [d["chunk_type"] for d in data],
                "heading_text": [d.get("heading_text") for d in data],
                "content": [d["content"][:8000] if len(d["content"]) > 8000 else d["content"] for d in data],
                "content_hash": [d["content_hash"] for d in data],
                "embedding": [d["embedding"] for d in data],
            }

            # Insert
            result = collection.insert(columns)
            collection.flush()

            logger.debug(f"Inserted {len(data)} vectors into {collection_name}")
            return result.primary_keys

        except Exception as e:
            logger.error(f"Failed to insert vectors into {collection_name}: {e}")
            raise MilvusError("insert", collection_name, str(e))

    async def insert_vectors_async(
        self,
        collection_name: str,
        data: list[dict[str, Any]],
    ) -> list[str]:
        """Async wrapper for vector insertion."""
        return await self._run_sync(self.insert_vectors, collection_name, data)

    def search_vectors(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 50,
        tenant_id: str | None = None,
        document_ids: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            collection_name: Target collection
            query_vector: Query embedding
            top_k: Number of results
            tenant_id: Filter by tenant
            document_ids: Filter by document IDs
            filter_expr: Custom filter expression

        Returns:
            List of results with scores and metadata
        """
        self.connect()

        try:
            collection = Collection(collection_name, using=self.alias)
            collection.load()

            # Build filter expression
            expr_parts = []
            if tenant_id:
                expr_parts.append(f'tenant_id == "{tenant_id}"')
            if document_ids:
                doc_ids_str = ", ".join(f'"{d}"' for d in document_ids)
                expr_parts.append(f'document_id in [{doc_ids_str}]')
            if filter_expr:
                expr_parts.append(filter_expr)

            expr = " && ".join(expr_parts) if expr_parts else None

            # Search parameters for HNSW
            search_params = {
                "metric_type": "COSINE",
                "params": {
                    "ef": 100,  # Higher ef = more accurate but slower
                },
            }

            # Execute search
            results = collection.search(
                data=[query_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=[
                    "id", "tenant_id", "document_id", "chunk_index",
                    "page_number", "chunk_type", "heading_text", "content",
                    "content_hash",
                ],
                consistency_level=CONSISTENCY_STRONG,
            )

            # Process results
            hits = results[0]
            output = []
            for hit in hits:
                entity = hit.entity
                output.append({
                    "id": entity.get("id"),
                    "tenant_id": entity.get("tenant_id"),
                    "document_id": entity.get("document_id"),
                    "chunk_index": entity.get("chunk_index"),
                    "page_number": entity.get("page_number"),
                    "chunk_type": entity.get("chunk_type"),
                    "heading_text": entity.get("heading_text"),
                    "content": entity.get("content"),
                    "content_hash": entity.get("content_hash"),
                    "score": hit.score,  # Cosine similarity (0-1)
                })

            logger.debug(f"Search returned {len(output)} results from {collection_name}")
            return output

        except Exception as e:
            logger.error(f"Search failed in {collection_name}: {e}")
            raise MilvusError("search", collection_name, str(e))

    async def search_vectors_async(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 50,
        tenant_id: str | None = None,
        document_ids: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """Async wrapper for vector search."""
        return await self._run_sync(
            self.search_vectors,
            collection_name,
            query_vector,
            top_k,
            tenant_id,
            document_ids,
            filter_expr,
        )

    def delete_vectors(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        document_id: str | None = None,
        tenant_id: str | None = None,
    ) -> int:
        """
        Delete vectors by ID or document ID.

        Returns number of deleted vectors.
        """
        self.connect()

        try:
            collection = Collection(collection_name, using=self.alias)

            # Build filter expression
            expr_parts = []
            if ids:
                ids_str = ", ".join(f'"{id}"' for id in ids)
                expr_parts.append(f'id in [{ids_str}]')
            if document_id:
                expr_parts.append(f'document_id == "{document_id}"')
            if tenant_id:
                expr_parts.append(f'tenant_id == "{tenant_id}"')

            expr = " && ".join(expr_parts) if expr_parts else None

            if expr:
                collection.delete(expr)
                collection.flush()
                logger.debug(f"Deleted vectors from {collection_name} with expr: {expr}")
                return 1  # Milvus doesn't return count directly

            return 0

        except Exception as e:
            logger.error(f"Failed to delete vectors from {collection_name}: {e}")
            raise MilvusError("delete", collection_name, str(e))

    async def delete_vectors_async(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        document_id: str | None = None,
        tenant_id: str | None = None,
    ) -> int:
        """Async wrapper for vector deletion."""
        return await self._run_sync(
            self.delete_vectors,
            collection_name,
            ids,
            document_id,
            tenant_id,
        )

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get collection statistics."""
        self.connect()

        try:
            if not utility.has_collection(collection_name, using=self.alias):
                return {"exists": False}

            collection = Collection(collection_name, using=self.alias)
            stats = collection.stats()

            return {
                "exists": True,
                "name": collection_name,
                "num_entities": stats.get("row_count", 0),
                "loaded": utility.load_state(collection_name, using=self.alias).name == "Loaded",
                "index_info": stats.get("index_info", []),
            }

        except Exception as e:
            logger.error(f"Failed to get stats for {collection_name}: {e}")
            return {"exists": False, "error": str(e)}

    def load_collection(self, collection_name: str) -> None:
        """Load collection to memory."""
        self.connect()

        try:
            collection = Collection(collection_name, using=self.alias)
            collection.load()
            logger.debug(f"Loaded collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to load collection {collection_name}: {e}")
            raise MilvusError("load", collection_name, str(e))

    def release_collection(self, collection_name: str) -> None:
        """Release collection from memory."""
        self.connect()

        try:
            collection = Collection(collection_name, using=self.alias)
            collection.release()
            logger.debug(f"Released collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to release collection {collection_name}: {e}")
            raise MilvusError("release", collection_name, str(e))


    def delete_tenant_collections(self, tenant_id: str) -> None:
        """
        Delete all collections for a tenant.

        Args:
            tenant_id: Tenant ID
        """
        self.connect()
        try:
            # List all collections
            collections = utility.list_collections(using=self.alias)
            prefix = f"{settings.MILVUS_COLLECTION_PREFIX}_{tenant_id}_"

            # Filter collections for this tenant
            tenant_collections = [
                c for c in collections
                if c.startswith(prefix)
            ]

            # Delete each collection
            for collection in tenant_collections:
                logger.info(f"Deleting collection {collection}")
                utility.drop_collection(collection, using=self.alias)

            logger.info(f"Deleted {len(tenant_collections)} collections for tenant {tenant_id}")

        except Exception as e:
            logger.error(f"Failed to delete collections for tenant {tenant_id}: {e}")
            raise MilvusError("delete_tenant", tenant_id, str(e))

    async def delete_tenant_collections_async(self, tenant_id: str) -> None:
        """Async wrapper for tenant collection deletion."""
        return await self._run_sync(self.delete_tenant_collections, tenant_id)


# Module-level singleton accessor
_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """Return the process-wide `MilvusClient` singleton (lazily created)."""
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient()
        _milvus_client.connect()
    return _milvus_client