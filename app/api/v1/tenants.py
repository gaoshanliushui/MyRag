"""
Tenant Management Endpoints

Admin endpoints for creating, updating, and managing tenants.
Requires admin API key for access.
"""

import hashlib
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminAccess, DBSession
from app.config import settings
from app.models.schemas import (
    TenantAPIKeyResponse,
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)
from app.models.tenant import Tenant
from app.utils.exceptions import TenantAlreadyExistsError, TenantNotFoundError
from app.utils.logging import get_logger

logger = get_logger("api.tenants")

router = APIRouter()


def generate_tenant_names(slug: str) -> dict[str, str]:
    """Generate resource names for tenant isolation."""
    prefix = settings.MILVUS_COLLECTION_PREFIX
    return {
        "milvus_collection": f"{prefix}_{slug}_chunks",
        "es_index": f"{settings.ES_INDEX_PREFIX}_{slug}_docs",
        "neo4j_label": f"Tenant_{slug}",
    }


def generate_api_key() -> tuple[str, str]:
    """Generate API key and its hash."""
    api_key = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, api_key_hash


@router.post("", response_model=TenantAPIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    admin: AdminAccess,
    session: DBSession,
) -> TenantAPIKeyResponse:
    """Create a new tenant with isolated resources."""
    # Check if slug already exists
    existing = await session.execute(
        select(Tenant).where(Tenant.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise TenantAlreadyExistsError(data.slug)

    # Generate API key
    api_key, api_key_hash = generate_api_key()

    # Generate resource names
    names = generate_tenant_names(data.slug)

    # Create tenant
    tenant = Tenant(
        name=data.name,
        slug=data.slug,
        api_key=api_key,
        api_key_hash=api_key_hash,
        milvus_collection_name=names["milvus_collection"],
        es_index_name=names["es_index"],
        neo4j_label=names["neo4j_label"],
        admin_email=data.admin_email,
        description=data.description,
        max_documents=data.max_documents,
        max_storage_mb=data.max_storage_mb,
        max_queries_per_day=data.max_queries_per_day,
        config=data.config,
    )

    session.add(tenant)
    await session.flush()
    await session.refresh(tenant)

    logger.info(f"Tenant created: {tenant.name} ({tenant.id})")

    # Return with API key (only shown once)
    return TenantAPIKeyResponse(
        tenant=TenantResponse.model_validate(tenant),
        api_key=api_key,
    )


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    admin: AdminAccess,
    session: DBSession,
    page: int = 1,
    page_size: int = 20,
    is_active: bool | None = None,
) -> TenantListResponse:
    """List all tenants with pagination."""
    # Build query
    query = select(Tenant).where(Tenant.is_deleted == False)

    if is_active is not None:
        query = query.where(Tenant.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Tenant.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    tenants = result.scalars().all()

    return TenantListResponse(
        tenants=[TenantResponse.model_validate(t) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Get tenant details by ID."""
    result = await session.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_deleted == False
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError(str(tenant_id))

    return TenantResponse.model_validate(tenant)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    data: TenantUpdate,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Update tenant configuration."""
    result = await session.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_deleted == False
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError(str(tenant_id))

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await session.flush()
    await session.refresh(tenant)

    logger.info(f"Tenant updated: {tenant.name} ({tenant.id})")

    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID,
    admin: AdminAccess,
    session: DBSession,
) -> None:
    """Soft delete a tenant."""
    result = await session.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_deleted == False
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError(str(tenant_id))

    # Soft delete
    tenant.is_deleted = True
    tenant.is_active = False
    from datetime import datetime
    tenant.deleted_at = datetime.utcnow()

    await session.flush()

    logger.info(f"Tenant deleted: {tenant.name} ({tenant.id})")


@router.post("/{tenant_id}/regenerate-key", response_model=TenantAPIKeyResponse)
async def regenerate_api_key(
    tenant_id: uuid.UUID,
    admin: AdminAccess,
    session: DBSession,
) -> TenantAPIKeyResponse:
    """Regenerate tenant API key."""
    result = await session.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_deleted == False
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError(str(tenant_id))

    # Generate new API key
    api_key, api_key_hash = generate_api_key()
    tenant.api_key = api_key
    tenant.api_key_hash = api_key_hash

    await session.flush()
    await session.refresh(tenant)

    logger.info(f"API key regenerated for tenant: {tenant.name}")

    return TenantAPIKeyResponse(
        tenant=TenantResponse.model_validate(tenant),
        api_key=api_key,
    )


@router.get("/{tenant_id}/stats")
async def get_tenant_stats(
    tenant_id: uuid.UUID,
    admin: AdminAccess,
    session: DBSession,
) -> dict[str, Any]:
    """Get tenant usage statistics."""
    result = await session.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_deleted == False
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantNotFoundError(str(tenant_id))

    return {
        "tenant_id": str(tenant.id),
        "name": tenant.name,
        "current_documents": tenant.current_documents,
        "current_storage_mb": tenant.current_storage_mb,
        "max_documents": tenant.max_documents,
        "max_storage_mb": tenant.max_storage_mb,
        "documents_usage_percent": (tenant.current_documents / tenant.max_documents) * 100 if tenant.max_documents > 0 else 0,
        "storage_usage_percent": (tenant.current_storage_mb / tenant.max_storage_mb) * 100 if tenant.max_storage_mb > 0 else 0,
        "queries_today": tenant.queries_today,
        "max_queries_per_day": tenant.max_queries_per_day,
        "queries_usage_percent": (tenant.queries_today / tenant.max_queries_per_day) * 100 if tenant.max_queries_per_day > 0 else 0,
    }