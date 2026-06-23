"""
Application Configuration - Pydantic Settings

All configuration is loaded from environment variables or .env file.
Supports both local development and Docker deployment.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(v: object) -> object:
    """BeforeValidator: turn a CSV string (or single string) into a list[str]."""
    if isinstance(v, str):
        if "," in v:
            return [item.strip() for item in v.split(",") if item.strip()]
        # Single value (no comma) — still wrap it in a list
        return [v.strip()] if v.strip() else []
    return v


CommaSeparated = Annotated[list[str], BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,  # let BeforeValidator handle CSV → list conversion
    )

    # Application
    APP_NAME: str = "MyRag"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = Field(default="change-this-in-production", min_length=32)

    # API
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: CommaSeparated = Field(default_factory=lambda: ["*"])
    API_KEY_HEADER: str = "X-API-Key"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+asyncpg://myrag:myrag@localhost:5432/myrag"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Milvus Vector Database
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_PREFIX: str = "myrag"
    MILVUS_ALIAS: str = "default"

    # Elasticsearch
    ES_HOSTS: CommaSeparated = Field(default_factory=lambda: ["http://localhost:9200"])
    ES_INDEX_PREFIX: str = "myrag"
    ES_USER: str = ""
    ES_PASSWORD: str = ""

    # Neo4j Knowledge Graph
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123"
    NEO4J_DATABASE: str = "neo4j"

    # Redis Cache
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_DB: int = 0
    REDIS_SESSION_DB: int = 1
    REDIS_CELERY_DB: int = 2

    # Celery Task Queue
    CELERY_BROKER_URL: str = "redis://localhost:6379/2"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: CommaSeparated = Field(default_factory=lambda: ["json"])
    CELERY_TASK_SOFT_TIME_LIMIT: int = 300  # 5 minutes
    CELERY_TASK_TIME_LIMIT: int = 600  # 10 minutes
    CELERY_MAX_RETRIES: int = 3
    CELERY_RETRY_DELAY: int = 5  # seconds

    # Embedding Model (BGE-M3)
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_MODEL_PATH: str = ""  # Local path if downloaded
    EMBEDDING_DEVICE: str = "cuda"  # cuda, cpu, mps
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DIMENSION: int = 1024  # BGE-M3 default dimension
    EMBEDDING_MAX_LENGTH: int = 8192

    # Reranker Model (Jina-Rerank)
    RERANKER_MODEL: str = "jinaai/jina-reranker-v2-base-multilingual"
    RERANKER_MODEL_PATH: str = ""  # Local path if downloaded
    RERANKER_DEVICE: str = "cuda"
    RERANKER_TOP_K: int = 5

    # LLM Provider
    LLM_PROVIDER: Literal["ollama", "vllm", "openai", "mock"] = "ollama"
    LLM_MODEL: str = "qwen2.5:14b"
    LLM_API_URL: str = "http://localhost:11434"
    LLM_API_KEY: str = ""
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7

    # Document Processing
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: CommaSeparated = Field(
        default_factory=lambda: ["pdf", "docx", "doc", "txt", "html", "md"]
    )

    # Semantic Chunking
    CHUNK_MIN_SIZE: int = 100  # tokens
    CHUNK_MAX_SIZE: int = 1000  # tokens
    CHUNK_OVERLAP_MIN: int = 10  # tokens
    CHUNK_OVERLAP_MAX: int = 250  # tokens
    SEMANTIC_BOUNDARY_THRESHOLD: float = 0.5  # similarity threshold for boundary detection

    # Retrieval
    RETRIEVAL_TOP_K: int = 50  # candidates from each retriever
    COARSE_RANK_TOP_K: int = 20  # after coarse ranking
    FINAL_TOP_K: int = 5  # after fine ranking

    # Fusion Algorithm
    FUSION_K: int = 60  # RRF parameter
    FUSION_ALPHA: float = 0.3  # weight for query length factor
    FUSION_BETA: float = 0.2  # weight for entity count factor

    # Confidence Scoring
    CONFIDENCE_THRESHOLD: float = 0.6  # minimum confidence to include answer
    LOW_CONFIDENCE_FALLBACK: bool = True  # fallback on low confidence

    # Tiered Storage
    HOT_TIER_DAYS: int = 30
    WARM_TIER_DAYS: int = 90
    TIER_PROMOTION_THRESHOLD: int = 10  # queries per day to promote to hot
    TIER_DEMOTION_THRESHOLD: int = 1  # queries per day to demote to cold

    # Caching
    QUERY_CACHE_TTL: int = 300  # 5 minutes
    VECTOR_CACHE_TTL: int = 1800  # 30 minutes
    SESSION_CACHE_TTL: int = 3600  # 1 hour
    CACHE_MAX_MEMORY: str = "512mb"

    # Monitoring
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090
    TRACING_ENABLED: bool = False
    TRACING_SAMPLE_RATE: float = 0.1

    # Admin
    ADMIN_API_KEY: str = Field(default="change-this-to-a-secure-random-string", min_length=32)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure async driver is used."""
        if "postgresql://" in v and "asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://")
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessor
settings = get_settings()