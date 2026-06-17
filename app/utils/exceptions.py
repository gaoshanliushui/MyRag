"""
Custom Exceptions

Hierarchical exception system for the MyRag application.
All exceptions inherit from MyRagException for consistent handling.
"""

from typing import Any


class MyRagException(Exception):
    """Base exception for all MyRag errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


# Configuration Errors
class ConfigurationError(MyRagException):
    """Configuration-related errors."""
    pass


class MissingConfigurationError(ConfigurationError):
    """Required configuration is missing."""

    def __init__(self, key: str):
        super().__init__(f"Missing required configuration: {key}", {"key": key})


# Tenant Errors
class TenantError(MyRagException):
    """Tenant-related errors."""
    pass


class TenantNotFoundError(TenantError):
    """Tenant does not exist."""

    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant not found: {tenant_id}", {"tenant_id": tenant_id})


class TenantAccessDeniedError(TenantError):
    """Access denied for tenant operation."""

    def __init__(self, tenant_id: str, operation: str):
        super().__init__(
            f"Access denied for tenant {tenant_id} to perform {operation}",
            {"tenant_id": tenant_id, "operation": operation}
        )


class TenantQuotaExceededError(TenantError):
    """Tenant quota exceeded."""

    def __init__(self, tenant_id: str, quota_type: str, current: int, limit: int):
        super().__init__(
            f"Tenant {tenant_id} exceeded {quota_type} quota: {current}/{limit}",
            {"tenant_id": tenant_id, "quota_type": quota_type, "current": current, "limit": limit}
        )


class TenantAlreadyExistsError(TenantError):
    """Tenant already exists."""

    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant already exists: {tenant_id}", {"tenant_id": tenant_id})


# Document Errors
class DocumentError(MyRagException):
    """Document-related errors."""
    pass


class DocumentNotFoundError(DocumentError):
    """Document does not exist."""

    def __init__(self, document_id: str, tenant_id: str):
        super().__init__(
            f"Document not found: {document_id} in tenant {tenant_id}",
            {"document_id": document_id, "tenant_id": tenant_id}
        )


class DocumentProcessingError(DocumentError):
    """Error during document processing."""

    def __init__(self, document_id: str, stage: str, reason: str):
        super().__init__(
            f"Document processing failed at {stage}: {reason}",
            {"document_id": document_id, "stage": stage, "reason": reason}
        )


class DocumentUploadError(DocumentError):
    """Error during document upload."""

    def __init__(self, filename: str, reason: str):
        super().__init__(
            f"Document upload failed for {filename}: {reason}",
            {"filename": filename, "reason": reason}
        )


class InvalidFileTypeError(DocumentUploadError):
    """Invalid file type for upload."""

    def __init__(self, filename: str, extension: str, allowed: list[str]):
        super().__init__(
            filename,
            f"Invalid file type: {extension}. Allowed: {allowed}"
        )
        self.details["allowed_extensions"] = allowed


class FileTooLargeError(DocumentUploadError):
    """File exceeds size limit."""

    def __init__(self, filename: str, size: int, max_size: int):
        super().__init__(
            filename,
            f"File size {size} exceeds limit {max_size}"
        )
        self.details["size"] = size
        self.details["max_size"] = max_size


# Retrieval Errors
class RetrievalError(MyRagException):
    """Retrieval-related errors."""
    pass


class IndexNotFoundError(RetrievalError):
    """Index/collection not found for tenant."""

    def __init__(self, tenant_id: str, index_type: str):
        super().__init__(
            f"Index not found for tenant {tenant_id}: {index_type}",
            {"tenant_id": tenant_id, "index_type": index_type}
        )


class EmbeddingError(RetrievalError):
    """Error during embedding generation."""

    def __init__(self, text: str, reason: str):
        super().__init__(
            f"Embedding generation failed: {reason}",
            {"text_preview": text[:100] if len(text) > 100 else text, "reason": reason}
        )


class SearchError(RetrievalError):
    """Error during search operation."""

    def __init__(self, query: str, retriever: str, reason: str):
        super().__init__(
            f"Search failed in {retriever}: {reason}",
            {"query_preview": query[:100] if len(query) > 100 else query, "retriever": retriever}
        )


# Database Errors
class DatabaseError(MyRagException):
    """Database connection/operation errors."""
    pass


class MilvusError(DatabaseError):
    """Milvus operation error."""

    def __init__(self, operation: str, collection: str, reason: str):
        super().__init__(
            f"Milvus {operation} failed on {collection}: {reason}",
            {"operation": operation, "collection": collection}
        )


class ElasticsearchError(DatabaseError):
    """Elasticsearch operation error."""

    def __init__(self, operation: str, index: str, reason: str):
        super().__init__(
            f"Elasticsearch {operation} failed on {index}: {reason}",
            {"operation": operation, "index": index}
        )


class Neo4jError(DatabaseError):
    """Neo4j operation error."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"Neo4j {operation} failed: {reason}",
            {"operation": operation}
        )


class RedisError(DatabaseError):
    """Redis operation error."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"Redis {operation} failed: {reason}",
            {"operation": operation}
        )


# Task Errors
class TaskError(MyRagException):
    """Celery task-related errors."""
    pass


class TaskTimeoutError(TaskError):
    """Task exceeded time limit."""

    def __init__(self, task_id: str, task_name: str):
        super().__init__(
            f"Task {task_name} ({task_id}) exceeded time limit",
            {"task_id": task_id, "task_name": task_name}
        )


class TaskRetryExceededError(TaskError):
    """Task exceeded max retries."""

    def __init__(self, task_id: str, task_name: str, retries: int):
        super().__init__(
            f"Task {task_name} ({task_id}) exceeded max retries: {retries}",
            {"task_id": task_id, "task_name": task_name, "retries": retries}
        )


# LLM Errors
class LLMError(MyRagException):
    """LLM-related errors."""
    pass


class LLMConnectionError(LLMError):
    """Cannot connect to LLM service."""

    def __init__(self, provider: str, url: str):
        super().__init__(
            f"Cannot connect to LLM service: {provider} at {url}",
            {"provider": provider, "url": url}
        )


class LLMResponseError(LLMError):
    """Error in LLM response."""

    def __init__(self, provider: str, reason: str):
        super().__init__(
            f"LLM response error from {provider}: {reason}",
            {"provider": provider}
        )


# API Errors (for HTTP responses)
class APIError(MyRagException):
    """API-level errors with HTTP status codes."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None
    ):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message, details)


class NotFoundError(APIError):
    """Resource not found (404)."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            f"{resource} not found: {identifier}",
            status_code=404,
            error_code="NOT_FOUND",
            details={"resource": resource, "identifier": identifier}
        )


class UnauthorizedError(APIError):
    """Unauthorized access (401)."""

    def __init__(self, reason: str = "Invalid or missing API key"):
        super().__init__(
            reason,
            status_code=401,
            error_code="UNAUTHORIZED"
        )


class ForbiddenError(APIError):
    """Forbidden access (403)."""

    def __init__(self, reason: str = "Access denied"):
        super().__init__(
            reason,
            status_code=403,
            error_code="FORBIDDEN"
        )


class ValidationError(APIError):
    """Validation error (400)."""

    def __init__(self, field: str, reason: str):
        super().__init__(
            f"Validation error for {field}: {reason}",
            status_code=400,
            error_code="VALIDATION_ERROR",
            details={"field": field, "reason": reason}
        )


class RateLimitError(APIError):
    """Rate limit exceeded (429)."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after} seconds.",
            status_code=429,
            error_code="RATE_LIMIT",
            details={"retry_after": retry_after}
        )