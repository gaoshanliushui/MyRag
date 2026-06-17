"""
Document Processing Celery Tasks

Async tasks for:
- Document processing (parse → chunk → embed → index)
- Document deletion (cleanup from all stores)
"""

import uuid
from datetime import datetime

from celery import shared_task
from sqlalchemy import select, update

from app.config import settings
from app.core.monitoring.metrics import TASKS_TOTAL, update_document_count
from app.core.preprocessing.pipeline import get_pipeline, PreprocessingResult
from app.db.session import get_session_context
from app.models.document import Document, DocumentStatus, Chunk
from app.tasks.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger("tasks.documents")


@shared_task(
    bind=True,
    name="app.tasks.documents.process_document_task",
    max_retries=settings.CELERY_MAX_RETRIES,
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    time_limit=settings.CELERY_TASK_TIME_LIMIT,
    default_retry_delay=settings.CELERY_RETRY_DELAY,
)
def process_document_task(
    self: Any,
    document_id: str,
    tenant_id: str,
) -> dict:
    """
    Process a document asynchronously.

    Flow:
    1. Parse document
    2. Clean and chunk
    3. Generate embeddings
    4. Index into Milvus, ES, Neo4j
    5. Update document status
    """
    logger.info(f"Processing document {document_id} for tenant {tenant_id}")

    # Update status to processing
    async def update_status(status: DocumentStatus, error: str = None):
        async with get_session_context() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=status,
                    processing_error=error,
                    processing_started_at=datetime.utcnow() if status == DocumentStatus.PROCESSING else None,
                    processing_completed_at=datetime.utcnow() if status == DocumentStatus.COMPLETED else None,
                )
            )

    # Run async processing
    import asyncio

    async def process():
        # Get document info
        async with get_session_context() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                raise ValueError(f"Document {document_id} not found")

            file_path = document.file_path
            file_type = document.file_type

        # Update to processing
        await update_status(DocumentStatus.PROCESSING)

        try:
            # Progress callback
            def progress_callback(progress: float, stage: str):
                self.update_state(
                    state="PROGRESS",
                    meta={"progress": progress, "stage": stage}
                )

            # Run preprocessing pipeline
            pipeline = get_pipeline()
            result = await pipeline.process(
                file_path=file_path,
                file_type=file_type,
                document_id=document_id,
                tenant_id=tenant_id,
                progress_callback=progress_callback,
            )

            # Update to indexing
            await update_status(DocumentStatus.INDEXING)

            # Index into stores
            await index_chunks(result, tenant_id)

            # Update document stats
            async with get_session_context() as session:
                await session.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        status=DocumentStatus.COMPLETED,
                        total_pages=result.total_pages,
                        total_chunks=result.total_chunks,
                        total_tokens=result.total_tokens,
                        processing_completed_at=datetime.utcnow(),
                    )
                )

                # Create chunk records
                for chunk_data in result.chunks:
                    chunk = Chunk(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        chunk_index=chunk_data["chunk_index"],
                        page_number=chunk_data["page_number"],
                        content=chunk_data["content"],
                        content_hash=chunk_data["content_hash"],
                        chunk_type=chunk_data["chunk_type"],
                        heading_text=chunk_data["heading_text"],
                        token_count=chunk_data["token_count"],
                        embedding_id=chunk_data["id"],
                        embedding_status="completed",
                    )
                    session.add(chunk)

                await session.commit()

            # Update tenant document count
            async with get_session_context() as session:
                from app.models.tenant import Tenant
                tenant_result = await session.execute(
                    select(Tenant).where(Tenant.id == tenant_id)
                )
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    tenant.current_documents += 1
                    await session.commit()
                    update_document_count(tenant_id, tenant.current_documents, result.total_chunks)

            logger.info(f"Document {document_id} processed successfully")
            TASKS_TOTAL.labels(task_name="process_document", status="success").inc()

            return {
                "document_id": document_id,
                "status": "completed",
                "total_chunks": result.total_chunks,
                "total_tokens": result.total_tokens,
            }

        except Exception as e:
            await update_status(DocumentStatus.FAILED, str(e))
            logger.error(f"Document processing failed: {e}")
            TASKS_TOTAL.labels(task_name="process_document", status="failure").inc()
            raise

    return asyncio.run(process())


async def index_chunks(
    result: PreprocessingResult,
    tenant_id: str,
) -> None:
    """Index chunks into Milvus, Elasticsearch, and Neo4j."""
    from app.db.milvus import get_milvus_client
    from app.db.elasticsearch import get_es_client
    from app.db.neo4j import get_neo4j_client

    # Get tenant resources
    async with get_session_context() as session:
        from app.models.tenant import Tenant
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        collection_name = tenant.milvus_collection_name
        es_index = tenant.es_index_name
        neo4j_label = tenant.neo4j_label

    # Prepare data
    pipeline = get_pipeline()
    chunks = []
    for chunk_data in result.chunks:
        from app.core.preprocessing.chunker import SemanticChunk
        chunk = SemanticChunk(
            content=chunk_data["content"],
            chunk_index=chunk_data["chunk_index"],
            page_number=chunk_data["page_number"],
            chunk_type=chunk_data["chunk_type"],
            heading_text=chunk_data["heading_text"],
            token_count=chunk_data["token_count"],
            embedding=chunk_data["embedding"],
        )
        chunk.chunk_metadata["chunk_id"] = chunk_data["id"]
        chunks.append(chunk)

    # Index to Milvus
    milvus_data = pipeline.prepare_for_milvus(
        chunks,
        result.document_id,
        tenant_id,
    )
    milvus = get_milvus_client()
    await milvus.create_collection_async(collection_name)
    await milvus.insert_vectors_async(collection_name, milvus_data)
    logger.info(f"Indexed {len(milvus_data)} vectors to Milvus")

    # Index to Elasticsearch
    es_data = pipeline.prepare_for_elasticsearch(
        chunks,
        result.document_id,
        tenant_id,
    )
    es = await get_es_client()
    await es.create_index(es_index)
    await es.bulk_index(es_index, es_data)
    await es.refresh_index(es_index)
    logger.info(f"Indexed {len(es_data)} documents to Elasticsearch")

    # Index to Neo4j (entity extraction)
    neo4j = get_neo4j_client()
    await neo4j.create_tenant_label_async(neo4j_label)

    for chunk in chunks:
        await neo4j.add_chunk_node_async(
            neo4j_label,
            chunk.chunk_metadata.get("chunk_id", ""),
            result.document_id,
            chunk.chunk_index,
            chunk.content[:500],
            chunk.page_number,
        )

    logger.info(f"Indexed {len(chunks)} nodes to Neo4j")


@shared_task(
    bind=True,
    name="app.tasks.documents.delete_document_task",
    max_retries=3,
)
def delete_document_task(
    self: Any,
    document_id: str,
    tenant_id: str,
) -> dict:
    """
    Delete document from all stores.

    Removes:
    - PostgreSQL chunk records
    - Milvus vectors
    - Elasticsearch documents
    - Neo4j nodes
    """
    logger.info(f"Deleting document {document_id} for tenant {tenant_id}")

    import asyncio

    async def delete():
        # Get tenant info
        async with get_session_context() as session:
            from app.models.tenant import Tenant
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            collection_name = tenant.milvus_collection_name
            es_index = tenant.es_index_name
            neo4j_label = tenant.neo4j_label

            # Delete chunks from database
            await session.execute(
                update(Chunk).where(
                    Chunk.document_id == document_id,
                    Chunk.tenant_id == tenant_id,
                ).values(is_deleted=True)
            )
            await session.commit()

        # Delete from Milvus
        from app.db.milvus import get_milvus_client
        milvus = get_milvus_client()
        await milvus.delete_vectors_async(collection_name, document_id=document_id)

        # Delete from Elasticsearch
        from app.db.elasticsearch import get_es_client
        es = await get_es_client()
        await es.delete_by_document_id(es_index, document_id, tenant_id)

        # Delete from Neo4j
        from app.db.neo4j import get_neo4j_client
        neo4j = get_neo4j_client()
        # Note: Neo4j doesn't have document_id direct filter, need custom query

        # Update tenant count
        async with get_session_context() as session:
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if tenant:
                tenant.current_documents -= 1
                await session.commit()

        logger.info(f"Document {document_id} deleted from all stores")

        return {"document_id": document_id, "status": "deleted"}

    return asyncio.run(delete())