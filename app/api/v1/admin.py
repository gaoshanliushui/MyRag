"""
Admin Endpoints - System Administration

Endpoints for system administrators to manage:
- Tenants
- Users
- System configuration
- Monitoring
"""

import asyncio
import time
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminAccess, DBSession
from app.config import settings
from app.core.monitoring.metrics import METRICS_REGISTRY
from app.db.session import check_db_connection
from app.models.document import Chunk, Document
from app.models.schemas import HealthResponse, StatsResponse
from app.models.tenant import Tenant
from app.utils.exceptions import AdminOperationError
from app.utils.logging import get_logger
from app.utils.security import generate_api_key, hash_api_key

logger = get_logger("api.admin")

router = APIRouter()


# Pydantic models for request/response
class TenantCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    max_documents: int = Field(1000, gt=0)
    max_storage_mb: int = Field(1024, gt=0)  # 1GB default
    max_users: int = Field(10, gt=0)
    settings: dict[str, Any] = {}


class TenantResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: str
    max_documents: int
    max_storage_mb: int
    max_users: int
    current_documents: int
    current_storage_mb: int
    current_users: int
    queries_today: int
    last_query_date: Optional[str]
    created_at: str
    updated_at: str


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    max_documents: Optional[int] = Field(None, gt=0)
    max_storage_mb: Optional[int] = Field(None, gt=0)
    max_users: Optional[int] = Field(None, gt=0)
    settings: Optional[dict[str, Any]] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    is_admin: bool = False


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: Optional[str]
    is_admin: bool
    is_active: bool
    last_login: Optional[str]
    created_at: str
    updated_at: str


class SystemConfigUpdate(BaseModel):
    retrieval_top_k: Optional[int] = Field(None, gt=0)
    confidence_threshold: Optional[float] = Field(None, ge=0, le=1)
    max_retrieval_latency_ms: Optional[int] = Field(None, gt=0)
    query_cache_ttl: Optional[int] = Field(None, gt=0)


# Health and monitoring endpoints (existing)
@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: DBSession,
) -> HealthResponse:
    """
    Comprehensive health check.
    """
    # ... (keep existing implementation)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    admin: AdminAccess,
    session: DBSession,
) -> StatsResponse:
    """
    System-wide statistics.
    """
    # ... (keep existing implementation)


@router.get("/metrics")
async def get_metrics(
    admin: AdminAccess,
) -> dict[str, Any]:
    """
    Prometheus metrics summary.
    """
    # ... (keep existing implementation)


@router.get("/tasks")
async def list_active_tasks(
    admin: AdminAccess,
) -> dict[str, Any]:
    """List active Celery tasks."""
    # ... (keep existing implementation)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    admin: AdminAccess,
) -> dict[str, Any]:
    """Cancel a Celery task."""
    # ... (keep existing implementation)


@router.get("/tenants/{tenant_id}/verify-isolation")
async def verify_tenant_isolation(
    tenant_id: str,
    admin: AdminAccess,
) -> dict[str, Any]:
    """Verify tenant data isolation across all stores."""
    # ... (keep existing implementation)


# New Tenant Management Endpoints
@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Create a new tenant."""
    # Check if tenant name already exists
    existing = await session.scalar(
        select(Tenant).where(Tenant.name == tenant_data.name)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with name '{tenant_data.name}' already exists"
        )

    # Generate API key for tenant
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    # Create tenant
    tenant = Tenant(
        name=tenant_data.name,
        description=tenant_data.description,
        max_documents=tenant_data.max_documents,
        max_storage_mb=tenant_data.max_storage_mb,
        max_users=tenant_data.max_users,
        settings=tenant_data.settings,
        api_key=api_key,
        api_key_hash=api_key_hash,
    )

    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    logger.info(f"Created new tenant: {tenant.name} ({tenant.id})")

    return TenantResponse.model_validate(tenant)


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    admin: AdminAccess,
    session: DBSession,
    page: int = 1,
    page_size: int = 20,
    name: Optional[str] = None,
) -> list[TenantResponse]:
    """List all tenants with pagination."""
    query = select(Tenant).where(Tenant.is_deleted == False)

    if name:
        query = query.where(Tenant.name.ilike(f"%{name}%"))

    query = query.order_by(Tenant.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    tenants = result.scalars().all()

    return [TenantResponse.model_validate(t) for t in tenants]


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Get tenant details."""
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_deleted == False)
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    return TenantResponse.model_validate(tenant)


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    update_data: TenantUpdate,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Update tenant configuration."""
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_deleted == False)
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    if update_data.name:
        # Check if name already exists
        existing = await session.scalar(
            select(Tenant).where(
                Tenant.name == update_data.name,
                Tenant.id != tenant_id
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant with name '{update_data.name}' already exists"
            )
        tenant.name = update_data.name

    if update_data.description is not None:
        tenant.description = update_data.description
    if update_data.max_documents is not None:
        tenant.max_documents = update_data.max_documents
    if update_data.max_storage_mb is not None:
        tenant.max_storage_mb = update_data.max_storage_mb
    if update_data.max_users is not None:
        tenant.max_users = update_data.max_users
    if update_data.settings is not None:
        tenant.settings = update_data.settings

    tenant.updated_at = func.now()
    await session.commit()
    await session.refresh(tenant)

    logger.info(f"Updated tenant: {tenant.id}")

    return TenantResponse.model_validate(tenant)


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    admin: AdminAccess,
    session: DBSession,
) -> None:
    """Soft delete a tenant."""
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_deleted == False)
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    tenant.is_deleted = True
    tenant.deleted_at = func.now()
    await session.commit()

    # Trigger async cleanup of tenant data
    from app.tasks.admin import cleanup_tenant_task
    cleanup_tenant_task.delay(str(tenant_id))

    logger.info(f"Deleted tenant: {tenant.id}")


@router.post("/tenants/{tenant_id}/regenerate-api-key", response_model=TenantResponse)
async def regenerate_api_key(
    tenant_id: UUID,
    admin: AdminAccess,
    session: DBSession,
) -> TenantResponse:
    """Regenerate tenant API key."""
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_deleted == False)
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    tenant.api_key = generate_api_key()
    tenant.updated_at = func.now()
    await session.commit()
    await session.refresh(tenant)

    logger.info(f"Regenerated API key for tenant: {tenant.id}")

    return TenantResponse.model_validate(tenant)


# User Management Endpoints
@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    admin: AdminAccess,
    session: DBSession,
) -> UserResponse:
    """Create a new system user."""
    # TODO: Implement user creation
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User creation not implemented yet"
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: AdminAccess,
    session: DBSession,
    page: int = 1,
    page_size: int = 20,
    username: Optional[str] = None,
) -> list[UserResponse]:
    """List all system users with pagination."""
    # TODO: Implement user listing
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User listing not implemented yet"
    )


# System Configuration Endpoints
@router.get("/config")
async def get_config(
    admin: AdminAccess,
) -> dict[str, Any]:
    """Get current system configuration."""
    return {
        "retrieval_top_k": settings.RETRIEVAL_TOP_K,
        "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
        "max_retrieval_latency_ms": settings.MAX_RETRIEVAL_LATENCY_MS,
        "query_cache_ttl": settings.QUERY_CACHE_TTL,
    }


@router.put("/config")
async def update_config(
    config_data: SystemConfigUpdate,
    admin: AdminAccess,
) -> dict[str, Any]:
    """Update system configuration."""
    # TODO: Implement config update with persistence
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Config update not implemented yet"
    )