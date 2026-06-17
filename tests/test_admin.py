"""
Test Suite for Admin Functionality

Tests for tenant management, system configuration, and administrative operations.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.v1.admin import TenantCreate, SystemConfigUpdate
from app.main import app


@pytest.fixture
def test_client():
    """Create a test client for the API."""
    return TestClient(app)


@pytest.fixture
def mock_tenant_data():
    """Sample tenant data for testing."""
    return {
        "name": "Test Tenant",
        "description": "A test tenant for unit testing",
        "max_documents": 1000,
        "max_storage_mb": 1024,
        "max_users": 10
    }


class TestAdminTenants:
    """Test tenant management endpoints."""

    def test_create_tenant(self, test_client, mock_tenant_data):
        """Test creating a new tenant."""
        # Mock admin authentication
        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            # Mock database session
            with patch("app.api.v1.admin.DBSession") as mock_session:
                mock_session_instance = AsyncMock()

                # Mock tenant creation
                mock_tenant = MagicMock()
                mock_tenant.id = str(uuid.uuid4())
                mock_tenant.api_key = "test_api_key_1234567890abcdef"

                for attr, value in mock_tenant_data.items():
                    setattr(mock_tenant, attr, value)

                # Mock the add operation
                mock_session_instance.add = MagicMock()
                mock_session_instance.commit = AsyncMock()
                mock_session_instance.refresh = AsyncMock()

                # Mock the select operation
                with patch("app.api.v1.admin.select") as mock_select:
                    mock_result = AsyncMock()
                    mock_result.scalar_one_or_none.return_value = None
                    mock_session_instance.execute.return_value = mock_result

                # Call the endpoint
                response = test_client.post(
                    "/api/v1/admin/tenants",
                    json=mock_tenant_data,
                    headers={"X-API-Key": "admin-key-test"}
                )

                assert response.status_code == 201
                response_data = response.json()

                # Verify the response contains expected fields
                assert "id" in response_data
                assert "name" in response_data
                assert "api_key" in response_data
                assert response_data["name"] == mock_tenant_data["name"]

    def test_get_tenant(self, test_client):
        """Test getting a tenant by ID."""
        tenant_id = str(uuid.uuid4())

        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            with patch("app.api.v1.admin.DBSession") as mock_session:
                mock_tenant = MagicMock()
                mock_tenant.id = tenant_id
                mock_tenant.name = "Test Tenant"
                mock_tenant.status = "ACTIVE"

                mock_result = AsyncMock()
                mock_result.scalar_one_or_none.return_value = mock_tenant
                mock_session_instance = AsyncMock()
                mock_session_instance.execute.return_value = mock_result

                response = test_client.get(
                    f"/api/v1/admin/tenants/{tenant_id}",
                    headers={"X-API-Key": "admin-key-test"}
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["id"] == tenant_id
                assert response_data["name"] == "Test Tenant"

    def test_update_tenant(self, test_client, mock_tenant_data):
        """Test updating tenant information."""
        tenant_id = str(uuid.uuid4())
        update_data = {"name": "Updated Tenant Name"}

        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            with patch("app.api.v1.admin.DBSession") as mock_session:
                # Create a mock tenant
                mock_tenant = MagicMock()
                mock_tenant.id = tenant_id
                mock_tenant.name = mock_tenant_data["name"]
                mock_tenant.status = "ACTIVE"

                for attr, value in mock_tenant_data.items():
                    setattr(mock_tenant, attr, value)

                mock_result = AsyncMock()
                mock_result.scalar_one_or_none.return_value = mock_tenant
                mock_session_instance = AsyncMock()
                mock_session_instance.execute.return_value = mock_result
                mock_session_instance.commit = AsyncMock()

                response = test_client.put(
                    f"/api/v1/admin/tenants/{tenant_id}",
                    json=update_data,
                    headers={"X-API-Key": "admin-key-test"}
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["name"] == "Updated Tenant Name"

    def test_delete_tenant(self, test_client):
        """Test deleting a tenant."""
        tenant_id = str(uuid.uuid4())

        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            with patch("app.api.v1.admin.DBSession") as mock_session:
                # Create a mock tenant
                mock_tenant = MagicMock()
                mock_tenant.id = tenant_id
                mock_tenant.is_deleted = False

                mock_result = AsyncMock()
                mock_result.scalar_one_or_none.return_value = mock_tenant
                mock_session_instance = AsyncMock()
                mock_session_instance.execute.return_value = mock_result
                mock_session_instance.commit = AsyncMock()

                # Mock the cleanup task
                with patch("app.tasks.admin.cleanup_tenant_task") as mock_task:
                    mock_task.delay = MagicMock()

                    response = test_client.delete(
                        f"/api/v1/admin/tenants/{tenant_id}",
                        headers={"X-API-Key": "admin-key-test"}
                    )

                    assert response.status_code == 204  # No content
                    mock_task.delay.assert_called_once_with(tenant_id)


class TestAdminSystem:
    """Test system-level admin operations."""

    def test_get_system_config(self, test_client):
        """Test getting system configuration."""
        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            response = test_client.get(
                "/api/v1/admin/config",
                headers={"X-API-Key": "admin-key-test"}
            )

            assert response.status_code == 200
            config = response.json()

            # Verify expected config values are present
            assert "retrieval_top_k" in config
            assert "confidence_threshold" in config
            assert "max_retrieval_latency_ms" in config
            assert "query_cache_ttl" in config

    def test_health_check(self, test_client):
        """Test system health check."""
        with patch("app.api.v1.admin.DBSession"):
            # Mock all service connections
            with patch("app.db.milvus.MilvusClient.check_connection", return_value=True), \
                 patch("app.db.elasticsearch.ESClient.ping", return_value=True), \
                 patch("app.db.neo4j.Neo4jClient.check_connection", return_value=True), \
                 patch("app.db.redis.RedisClient.ping", return_value=True):

                response = test_client.get("/api/v1/admin/health")

                assert response.status_code == 200
                health = response.json()

                assert health["status"] in ["healthy", "degraded"]
                assert "services" in health
                assert health["version"] is not None


class TestAdminStats:
    """Test system statistics."""

    def test_get_system_stats(self, test_client):
        """Test getting system statistics."""
        with patch("app.api.deps.get_admin_access") as mock_admin:
            mock_admin.return_value = True

            with patch("app.api.v1.admin.DBSession") as mock_session:
                # Mock the database queries for stats
                mock_result = AsyncMock()
                mock_result.scalar.return_value = 10  # count of items

                # Set up multiple scalar returns for different stats
                async def mock_scalar(query):
                    if "SELECT count()" in str(query):
                        return 10
                    elif "SUM" in str(query):
                        return 50
                    else:
                        return 0

                mock_session_instance = AsyncMock()
                mock_session_instance.scalar = mock_scalar
                mock_session_instance.execute.return_value = mock_result

                # Mock Celery inspection
                with patch("app.tasks.celery_app.celery_app") as mock_celery:
                    mock_control = MagicMock()
                    mock_inspect = MagicMock()
                    mock_inspect.active.return_value = {"worker1": ["task1"]}
                    mock_inspect.reserved.return_value = {"worker1": ["task2"]}
                    mock_control.inspect.return_value = mock_inspect
                    mock_celery.control = mock_control

                response = test_client.get(
                    "/api/v1/admin/stats",
                    headers={"X-API-Key": "admin-key-test"}
                )

                assert response.status_code == 200
                stats = response.json()

                assert "total_tenants" in stats
                assert "total_documents" in stats
                assert "active_tasks" in stats
                assert "queued_tasks" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])