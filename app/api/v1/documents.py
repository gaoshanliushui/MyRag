"""
Document Management Endpoints

Upload, list, retrieve, and delete documents for a tenant.
"""

import os
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentTenant, DBSession, Pagination
from app.config import settings
from app.models.document import Document, DocumentStatus
from app.models.schemas import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    PaginatedParams,
)
from app.models.tenant import Tenant
from app.utils.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
    TenantQuotaExceededError,
)
from app.utils.logging import get_logger

logger = get_logger("api.documents")

router = APIRouter()


def get_allowed_extensions() -> set[str]:
    """Get allowed file extensions."""
    return set(settings.ALLOWED_EXTENSIONS)


async def save_uploaded_file(
    file: UploadFile,
    tenant_id: uuid.UUID,
    upload_dir: Path,
) -> tuple[Path, str]:
    """Save uploaded file and return path and extension."""
    # Create tenant upload directory
    tenant_dir = upload_dir / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_id = uuid.uuid4()
    original_ext = Path(file.filename or "unknown").suffix.lower().lstrip(".")
    new_filename = f"{file_id}.{original_ext}"
    file_path = tenant_dir / new_filename

    # Save file
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    return file_path, original_ext


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    tenant: CurrentTenant,
    session: DBSession,
    file: UploadFile = File(...),
    metadata: dict[str, Any] | None = None,
) -> DocumentResponse:
    """Upload a document for processing."""
    # Validate file type
    allowed = get_allowed_extensions()
    original_ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if original_ext not in allowed:
        raise InvalidFileTypeError(file.filename or "unknown", original_ext, list(allowed))

    # Validate file size
    if file.size and file.size > settings.MAX_UPLOAD_SIZE:
        raise FileTooLargeError(file.filename or "unknown", file.size, settings.MAX_UPLOAD_SIZE)

    # Check tenant quota
    if tenant.current_documents >= tenant.max_documents:
        raise TenantQuotaExceededError(
            str(tenant.id),
            "documents",
            tenant.current_documents,
            tenant.max_documents
        )

    # Save file
    upload_dir = Path(settings.UPLOAD_DIR)
    file_path, file_ext = await save_uploaded_file(file, tenant.id, upload_dir)

    # Create document record
    document = Document(
        tenant_id=tenant.id,
        filename=Path(file_path).name,
        original_filename=file.filename or "unknown",
        file_type=file_ext,
        file_size=file.size or 0,
        file_path=str(file_path),
        status=DocumentStatus.PENDING,
        metadata=metadata or {},
    )

    session.add(document)
    await session.flush()
    await session.refresh(document)

    # Trigger async processing task
    from app.tasks.documents import process_document_task
    task = process_document_task.delay(str(document.id), str(tenant.id))
    document.processing_task_id = task.id
    await session.flush()

    logger.info(
        f"Document uploaded: {document.original_filename} ({document.id}) "
        f"by tenant {tenant.name}"
    )

    return DocumentResponse.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    tenant: CurrentTenant,
    session: DBSession,
    pagination: Pagination = Depends(),
    status_filter: DocumentStatus | None = None,
    file_type: str | None = None,
) -> DocumentListResponse:
    """List documents for tenant with pagination."""
    query = select(Document).where(
        Document.tenant_id == tenant.id,
        Document.is_deleted == False,
    )

    if status_filter:
        query = query.where(Document.status == status_filter)

    if file_type:
        query = query.where(Document.file_type == file_type)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginate
    offset = (pagination.page - 1) * pagination.page_size
    query = query.order_by(Document.created_at.desc()).offset(offset).limit(pagination.page_size)

    result = await session.execute(query)
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        has_more=(offset + pagination.page_size) < total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    session: DBSession,
) -> DocumentResponse:
    """Get document details."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant.id,
            Document.is_deleted == False,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(str(document_id), str(tenant.id))

    # Update access count
    document.access_count += 1
    from datetime import datetime
    document.last_accessed_at = datetime.utcnow()
    await session.flush()

    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    session: DBSession,
) -> DocumentStatusResponse:
    """Get document processing status."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant.id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(str(document_id), str(tenant.id))

    # Calculate progress
    progress = 0.0
    if document.status == DocumentStatus.COMPLETED:
        progress = 1.0
    elif document.status == DocumentStatus.PROCESSING:
        progress = 0.5
    elif document.status == DocumentStatus.INDEXING:
        progress = 0.8

    # Get task status if available
    estimated_completion = None
    if document.processing_task_id:
        from app.tasks.documents import process_document_task
        from celery.result import AsyncResult
        task_result = AsyncResult(document.processing_task_id, app=process_document_task.app)
        if task_result.state == "PROGRESS":
            progress = task_result.info.get("progress", progress)

    return DocumentStatusResponse(
        id=document.id,
        status=document.status,
        total_pages=document.total_pages,
        total_chunks=document.total_chunks,
        total_tokens=document.total_tokens,
        processing_progress=progress,
        processing_error=document.processing_error,
        estimated_completion=estimated_completion,
    )


@router.get("/{document_id}/detail", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    session: DBSession,
) -> DocumentDetailResponse:
    """Get document with chunk preview."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant.id,
            Document.is_deleted == False,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(str(document_id), str(tenant.id))

    # Get chunk preview (first 10)
    chunk_query = select(Document.__table__.model_class).where(
        # This is a placeholder - actual chunk query would use Chunk model
    )

    # For now, return empty preview
    from app.models.document import Chunk, ChunkType
    from app.models.schemas import ChunkPreview

    chunks_result = await session.execute(
        select(Chunk).where(
            Chunk.document_id == document_id,
            Chunk.tenant_id == tenant.id,
        ).order_by(Chunk.chunk_index).limit(10)
    )
    chunks = chunks_result.scalars().all()

    chunk_preview = [
        ChunkPreview(
            id=c.id,
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            content_preview=c.content[:200] if len(c.content) > 200 else c.content,
            chunk_type=c.chunk_type,
            heading_text=c.heading_text,
        )
        for c in chunks
    ]

    return DocumentDetailResponse(
        document=DocumentResponse.model_validate(document),
        chunks_preview=chunk_preview,
        chunk_count=document.total_chunks,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    session: DBSession,
) -> None:
    """Soft delete a document."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant.id,
            Document.is_deleted == False,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(str(document_id), str(tenant.id))

    # Soft delete
    document.is_deleted = True
    document.status = DocumentStatus.DELETED
    from datetime import datetime
    document.deleted_at = datetime.utcnow()

    await session.flush()

    # Trigger cleanup task to remove from vector stores
    from app.tasks.documents import delete_document_task
    delete_document_task.delay(str(document.id), str(tenant.id))

    logger.info(f"Document deleted: {document.original_filename} ({document.id})")