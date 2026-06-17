"""
Neo4j Knowledge Graph Client

Provides graph-based retrieval:
- Entity extraction and linking
- Multi-hop traversal
- Relationship-based scoring
- Tenant-isolated subgraphs
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from neo4j import GraphDatabase, Session

from app.config import settings
from app.utils.exceptions import Neo4jError
from app.utils.logging import get_logger

logger = get_logger("db.neo4j")

# Thread pool for sync Neo4j operations
_executor = ThreadPoolExecutor(max_workers=4)


class Neo4jClient:
    """Neo4j client for knowledge graph operations."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE

        self._driver = None

    def connect(self) -> None:
        """Initialize Neo4j driver."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                )
                logger.info(f"Connected to Neo4j at {self.uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise Neo4jError("connect", str(e))

    def disconnect(self) -> None:
        """Close Neo4j driver."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Disconnected from Neo4j")

    def check_connection(self) -> bool:
        """Verify Neo4j connection."""
        try:
            self.connect()
            with self._driver.session(database=self.database) as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            logger.error(f"Neo4j connection check failed: {e}")
            return False

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run sync function in thread pool."""
        self.connect()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, func, *args, **kwargs)

    def _get_session(self) -> Session:
        """Get Neo4j session."""
        self.connect()
        return self._driver.session(database=self.database)

    def create_tenant_label(self, label: str) -> None:
        """Create tenant-specific label/schema."""
        self.connect()

        with self._get_session() as session:
            # Create index for efficient queries
            session.run(
                f"CREATE INDEX tenant_entity_id_{label} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.entity_id)"
            )
            session.run(
                f"CREATE INDEX tenant_chunk_id_{label} IF NOT EXISTS "
                f"FOR (n:{label}Chunk) ON (n.chunk_id)"
            )

        logger.info(f"Created tenant graph label: {label}")

    async def create_tenant_label_async(self, label: str) -> None:
        """Async wrapper for label creation."""
        await self._run_sync(self.create_tenant_label, label)

    def add_entity(
        self,
        label: str,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """
        Add an entity node to the knowledge graph.

        Args:
            label: Tenant label
            entity_id: Unique entity identifier
            entity_type: Type of entity (PERSON, ORG, LOCATION, etc.)
            name: Entity name/display text
            properties: Additional properties
        """
        self.connect()

        props = properties or {}
        props.update({
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": name,
        })

        with self._get_session() as session:
            session.run(
                f"MERGE (e:{label}:{entity_type} {{entity_id: $entity_id}}) "
                "SET e += $props",
                entity_id=entity_id,
                props=props,
            )

        logger.debug(f"Added entity: {name} ({entity_type})")

    async def add_entity_async(
        self,
        label: str,
        entity_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Async wrapper for adding entity."""
        await self._run_sync(
            self.add_entity,
            label,
            entity_id,
            entity_type,
            name,
            properties,
        )

    def add_chunk_node(
        self,
        label: str,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        content_preview: str,
        page_number: int | None = None,
    ) -> None:
        """Add a chunk node linked to entities."""
        self.connect()

        with self._get_session() as session:
            session.run(
                f"MERGE (c:{label}Chunk {{chunk_id: $chunk_id}}) "
                "SET c.document_id = $document_id, "
                "c.chunk_index = $chunk_index, "
                "c.content_preview = $content_preview, "
                "c.page_number = $page_number",
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=chunk_index,
                content_preview=content_preview[:500],
                page_number=page_number,
            )

        logger.debug(f"Added chunk node: {chunk_id}")

    async def add_chunk_node_async(
        self,
        label: str,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        content_preview: str,
        page_number: int | None = None,
    ) -> None:
        """Async wrapper for chunk node."""
        await self._run_sync(
            self.add_chunk_node,
            label,
            chunk_id,
            document_id,
            chunk_index,
            content_preview,
            page_number,
        )

    def link_chunk_to_entity(
        self,
        label: str,
        chunk_id: str,
        entity_id: str,
        relation_type: str = "MENTIONS",
    ) -> None:
        """Create relationship between chunk and entity."""
        self.connect()

        with self._get_session() as session:
            session.run(
                f"MATCH (c:{label}Chunk {{chunk_id: $chunk_id}}) "
                f"MATCH (e:{label} {{entity_id: $entity_id}}) "
                f"MERGE (c)-[r:{relation_type}]->(e) "
                "SET r.created_at = datetime()",
                chunk_id=chunk_id,
                entity_id=entity_id,
            )

        logger.debug(f"Linked chunk {chunk_id} to entity {entity_id}")

    async def link_chunk_to_entity_async(
        self,
        label: str,
        chunk_id: str,
        entity_id: str,
        relation_type: str = "MENTIONS",
    ) -> None:
        """Async wrapper for linking."""
        await self._run_sync(
            self.link_chunk_to_entity,
            label,
            chunk_id,
            entity_id,
            relation_type,
        )

    def multi_hop_search(
        self,
        label: str,
        query_entities: list[str],
        max_hops: int = 2,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Multi-hop retrieval via entity traversal.

        Finds chunks connected to query entities through
        shared entities or direct relationships.

        Args:
            label: Tenant label
            query_entities: List of entity names/IDs to start from
            max_hops: Maximum traversal depth
            top_k: Number of chunks to return

        Returns:
            List of chunks with graph scores
        """
        self.connect()

        with self._get_session() as session:
            # Build query for multi-hop traversal
            # 1-hop: Chunks directly mentioning query entities
            # 2-hop: Chunks mentioning entities that share entities with query entities

            query = (
                f"MATCH (q:{label}) WHERE q.name IN $entities "
                # 1-hop: Direct mentions
                f"OPTIONAL MATCH (c1:{label}Chunk)-[:MENTIONS]->(q) "
                # 2-hop: Shared entities
                f"OPTIONAL MATCH (c2:{label}Chunk)-[:MENTIONS]->(shared:{label})<-[:MENTIONS]-(q) "
                # Collect all matching chunks
                "WITH COALESCE(c1, c2) AS chunk, q, shared "
                f"WHERE chunk IS NOT NULL AND chunk:{label}Chunk "
                # Calculate score based on hop distance and shared entity count
                "WITH chunk, "
                "CASE WHEN c1 IS NOT NULL THEN 1.0 ELSE 0.5 END AS hop_score, "
                "COUNT(DISTINCT shared) AS shared_count "
                # Return results
                "RETURN DISTINCT chunk.chunk_id AS chunk_id, "
                "chunk.document_id AS document_id, "
                "chunk.chunk_index AS chunk_index, "
                "chunk.page_number AS page_number, "
                "chunk.content_preview AS content_preview, "
                "hop_score + (shared_count * 0.1) AS score "
                "ORDER BY score DESC "
                "LIMIT $top_k"
            )

            result = session.run(
                query,
                entities=query_entities,
                top_k=top_k,
            )

            chunks = []
            for record in result:
                chunks.append({
                    "chunk_id": record["chunk_id"],
                    "document_id": record["document_id"],
                    "chunk_index": record["chunk_index"],
                    "page_number": record["page_number"],
                    "content_preview": record["content_preview"],
                    "score": record["score"],
                })

            logger.debug(f"Multi-hop search found {len(chunks)} chunks for {query_entities}")
            return chunks

    async def multi_hop_search_async(
        self,
        label: str,
        query_entities: list[str],
        max_hops: int = 2,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """Async wrapper for multi-hop search."""
        return await self._run_sync(
            self.multi_hop_search,
            label,
            query_entities,
            max_hops,
            top_k,
        )

    def get_related_entities(
        self,
        label: str,
        entity_name: str,
        relation_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get entities related to a given entity."""
        self.connect()

        rels = relation_types or ["MENTIONS", "RELATED_TO", "SAME_AS"]

        with self._get_session() as session:
            query = (
                f"MATCH (e:{label}) WHERE e.name = $name "
                f"MATCH (e)-[r]->(related:{label}) "
                f"WHERE type(r) IN $rels "
                "RETURN related.entity_id AS entity_id, "
                "related.name AS name, "
                "related.entity_type AS entity_type, "
                "type(r) AS relation_type"
            )

            result = session.run(query, name=entity_name, rels=rels)

            entities = []
            for record in result:
                entities.append({
                    "entity_id": record["entity_id"],
                    "name": record["name"],
                    "entity_type": record["entity_type"],
                    "relation_type": record["relation_type"],
                })

            return entities

    def delete_tenant_data(self, label: str) -> int:
        """Delete all nodes for a tenant."""
        self.connect()

        with self._get_session() as session:
            result = session.run(
                f"MATCH (n:{label}) DETACH DELETE n "
                f"MATCH (n:{label}Chunk) DETACH DELETE n "
                "RETURN count(n) AS deleted"
            )
            deleted = result.single()["deleted"] if result.peek() else 0

        logger.info(f"Deleted {deleted} nodes with label {label}")
        return deleted

    async def delete_tenant_data_async(self, label: str) -> int:
        """Async wrapper for tenant deletion."""
        return await self._run_sync(self.delete_tenant_data, label)

    async def delete_tenant_data_async(self, label: str) -> int:
        """Async wrapper for tenant deletion."""
        return await self._run_sync(self.delete_tenant_data, label)
        """Get statistics for tenant subgraph."""
        self.connect()

        with self._get_session() as session:
            # Count nodes
            entity_count = session.run(
                f"MATCH (n:{label}) RETURN count(n) AS count"
            ).single()["count"]

            chunk_count = session.run(
                f"MATCH (n:{label}Chunk) RETURN count(n) AS count"
            ).single()["count"]

            # Count relationships
            rel_count = session.run(
                f"MATCH ()-[r]-() WHERE startNode(r):{label} OR endNode(r):{label} "
                "RETURN count(r) AS count"
            ).single()["count"]

        return {
            "label": label,
            "entity_count": entity_count,
            "chunk_count": chunk_count,
            "relationship_count": rel_count,
        }


# Singleton instance
_neo4j_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    """Get Neo4j client singleton."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client