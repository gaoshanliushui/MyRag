# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

分布式多租户混合检索企业级RAG系统 — a private, enterprise-grade RAG platform using a self-designed dense + sparse + knowledge-graph hybrid retrieval architecture. Targets government and finance intranet deployment scenarios requiring auditability, high concurrency, low hallucination, and strong compliance.

## Tech Stack

Python, FastAPI, Milvus (distributed cluster), Elasticsearch, Neo4j, BGE-M3, Jina-Rerank, Redis, Celery, Docker, Prometheus

## Architecture (Key Design Decisions)

### 1. Adaptive Semantic Preprocessing Pipeline
- Document hierarchy parsing with semantic boundary detection for chunking (not fixed-window)
- Chunk size and overlap adapt dynamically based on heading levels, paragraph integrity, and semantic coherence
- Structural noise reduction for tables, formulas, headers/footers

### 2. Three-Way Hybrid Retrieval (Core Innovation)
- **Dense vector retrieval** (semantic) via Milvus + BGE-M3 embeddings
- **BM25 sparse retrieval** (keyword) via Elasticsearch
- **Knowledge graph multi-hop retrieval** via Neo4j
- **Dynamic weight fusion** algorithm: auto-detects short-entity queries vs. long-semantic-reasoning scenarios and adjusts weights accordingly, replacing static RRF weighting

### 3. Two-Level Staged Reranking & Hallucination Suppression
- **Coarse ranker** (lightweight) → **Fine ranker** (high-precision, Jina-Rerank) on Top-50 candidates
- Retrieval confidence scoring + cross-evidence conflict detection
- All answers support source page-number traceability for compliance audits

### 4. Distributed Multi-Tenant Isolation & Data Governance
- Milvus sharded cluster with horizontal scaling; physical Collection isolation per tenant
- Cold/hot tiered storage: hot documents in memory index, cold/archived documents on disk mapping
- Incremental indexing, fragment merging, checkpoint resume (no full rebuilds)

### 5. Production-Grade High Availability
- Celery for async large-file parsing with circuit breaking, retry, and dead-letter queues
- Redis multi-level cache: query cache, vector result cache, session cache
- Prometheus-based full-link monitoring: retrieval latency, token consumption, recall rate, error rate

## Development Commands

> Codebase is in planning phase. Commands below are the expected structure based on the tech stack.

```bash
# Start all services
docker compose up -d

# Start FastAPI dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker
celery -A app.tasks worker --loglevel=info --concurrency=4

# Run tests
pytest

# Run a single test
pytest tests/test_retrieval.py::test_hybrid_search -v

# Lint
ruff check .
```

## Key Constraints

- **Private deployment**: all components must run offline without external API calls
- **Multi-tenant**: every operation is scoped to a tenant; physical isolation at the Milvus Collection level
- **Auditability**: every answer links back to source document pages
- **Performance target**: <300ms retrieval latency at million-document scale
- **Concurrency**: 50+ simultaneous enterprise users