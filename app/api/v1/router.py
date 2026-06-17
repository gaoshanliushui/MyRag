"""
API V1 Router - Aggregates all endpoint routers
"""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.documents import router as documents_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.tenants import router as tenants_router

# Main API router
api_router = APIRouter()

# Include sub-routers with their prefixes
api_router.include_router(
    tenants_router,
    prefix="/admin/tenants",
    tags=["Tenants"],
)

api_router.include_router(
    documents_router,
    prefix="/{tenant_id}/documents",
    tags=["Documents"],
)

api_router.include_router(
    retrieval_router,
    prefix="/{tenant_id}/retrieval",
    tags=["Retrieval"],
)

api_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin"],
)