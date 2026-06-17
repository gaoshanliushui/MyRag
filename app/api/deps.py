"""
API Dependencies - Dependency Injection for FastAPI

Provides dependencies for:
- Tenant authentication and context
- Database sessions
- External service clients (Milvus, ES, Neo4j, Redis)
"""

import hashlib
import uuid
from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.models.schemas import ErrorResponse
from app.models.tenant import Tenant
from app.utils.exceptions import TenantNotFoundError, UnauthorizedError
from app.utils.logging import get_logger, tenant_id_var
from app.utils.security import validate_api_key

logger = get_logger("api.deps")


# ============================================
# Tenant Authentication
# ============================================

async def get_tenant_by_api_key(
    api_key: Annotated[str, Header(alias=settings.API_KEY_HEADER)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Tenant:
    """
    Authenticate tenant by API key header.
    Returns tenant object or raises UnauthorizedError.
    """
    # Validate API key format first
    if not validate_api_key(api_key):
        raise UnauthorizedError("Invalid API key format")

    # Hash the API key for lookup
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Query tenant by API key hash
    result = await session.execute(
        select(Tenant).where(
            Tenant.api_key_hash == api_key_hash,
            Tenant.is_active == True,
            Tenant.is_deleted == False,
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise UnauthorizedError("Invalid API key")

    # Set tenant context for logging
    tenant_id_var.set(str(tenant.id))

    logger.debug(f"Tenant authenticated: {tenant.name} ({tenant.id})")

    return tenant


# Type alias for tenant dependency
CurrentTenant = Annotated[Tenant, Depends(get_tenant_by_api_key)]


# ============================================
# Admin Authentication (for tenant management)
# ============================================

async def get_admin_access(
    api_key: Annotated[str, Header(alias=settings.API_KEY_HEADER)],
) -> str:
    """
    Verify admin API key for tenant management endpoints.
    Admin API key is stored in settings.ADMIN_API_KEY or uses SECRET_KEY.
    """
    # Validate API key format first
    if not validate_api_key(api_key):
        raise UnauthorizedError("Invalid API key format")

    admin_key = getattr(settings, "ADMIN_API_KEY", settings.SECRET_KEY)

    if api_key != admin_key:
        raise UnauthorizedError("Admin access required")

    return api_key


AdminAccess = Annotated[str, Depends(get_admin_access)]


# ============================================
# Database Session
# ============================================

# Type alias for database session
DBSession = Annotated[AsyncSession, Depends(get_session)]


# ============================================
# Pagination
# ============================================

from app.models.schemas import PaginatedParams

Pagination = Annotated[PaginatedParams, Depends()]