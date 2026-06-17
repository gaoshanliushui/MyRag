# MyRag - Distributed Multi-Tenant Hybrid Retrieval Enterprise RAG System

A private, enterprise-grade RAG platform using a self-designed dense + sparse + knowledge-graph hybrid retrieval architecture. Targets government and finance intranet deployment scenarios requiring auditability, high concurrency, low hallucination, and strong compliance.

## Features

### Core Architecture

- **Adaptive Semantic Preprocessing Pipeline**: Document hierarchy parsing with semantic boundary detection for chunking (not fixed-window). Chunk size and overlap adapt dynamically based on heading levels, paragraph integrity, and semantic coherence.

- **Three-Way Hybrid Retrieval**:
  - Dense vector retrieval (semantic) via Milvus + BGE-M3 embeddings
  - BM25 sparse retrieval (keyword) via Elasticsearch
  - Knowledge graph multi-hop retrieval via Neo4j
  - Dynamic weight fusion algorithm that auto-detects short-entity queries vs long-semantic-reasoning scenarios

- **Two-Level Staged Reranking & Hallucination Suppression**:
  - Coarse ranker (lightweight) → Fine ranker (high-precision, Jina-Rerank) on Top-50 candidates
  - Retrieval confidence scoring + cross-evidence conflict detection
  - All answers support source page-number traceability for compliance audits

- **Distributed Multi-Tenant Isolation & Data Governance**:
  - Milvus sharded cluster with horizontal scaling
  - Physical Collection isolation per tenant
  - Cold/hot tiered storage: hot documents in memory index, cold/archived documents on disk mapping
  - Incremental indexing, fragment merging, checkpoint resume (no full rebuilds)

- **Production-Grade High Availability**:
  - Celery for async large-file parsing with circuit breaking, retry, and dead-letter queues
  - Redis multi-level cache: query cache, vector result cache, session cache
  - Prometheus-based full-link monitoring: retrieval latency, token consumption, recall rate, error rate

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **Vector Database**: Milvus 2.5+ (distributed cluster)
- **Search Engine**: Elasticsearch 8.17+
- **Knowledge Graph**: Neo4j 5.28+
- **Cache**: Redis 7.4+
- **Task Queue**: Celery 5.4+
- **Embeddings**: BGE-M3 (via sentence-transformers)
- **Reranking**: Jina-Rerank V2
- **LLM**: Ollama / vLLM / OpenAI-compatible APIs
- **Monitoring**: Prometheus + Grafana
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- (Optional) CUDA GPU for embeddings and reranking

### 1. Clone and Setup

```bash
cd F:\Project\Python\AI\rag\MyRag
```

### 2. Start All Services

```bash
cd docker
docker compose up -d
```

This will start:
- PostgreSQL (with pgvector)
- Milvus (with etcd and MinIO)
- Elasticsearch
- Neo4j
- Redis
- Prometheus
- Grafana

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the environment template and customize:

```bash
cp docker/.env.example .env
```

Edit `.env` to configure your settings. Key settings:

```bash
# LLM Provider (options: ollama, vllm, openai, mock)
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b
LLM_API_URL=http://localhost:11434

# Embedding device (options: cuda, cpu, mps)
EMBEDDING_DEVICE=cuda
```

### 5. Run Database Migrations

```bash
alembic upgrade head
```

### 6. Start the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Start Celery Worker (for async document processing)

```bash
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

### 8. Access the Application

- **API Documentation**: http://localhost:8000/docs (when DEBUG=true)
- **Health Check**: http://localhost:8000/health
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Redis Insight**: http://localhost:8001
- **Neo4j Browser**: http://localhost:7474 (neo4j/neo4j123)

## API Usage

### Create a Tenant

```bash
curl -X POST "http://localhost:8000/api/v1/admin/tenants" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Company",
    "description": "Company documents"
  }'
```

### Upload a Document

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/documents/upload" \
  -F "file=@document.pdf" \
  -H "X-Tenant-ID: {tenant_id}"
```

### Search Documents

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/search" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: {tenant_id}" \
  -d '{
    "query": "What are the key features of our product?",
    "top_k": 10,
    "mode": "hybrid",
    "enable_reranking": true,
    "enable_confidence": true
  }'
```

### Question Answering

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/qa" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: {tenant_id}" \
  -d '{
    "question": "How do I configure the authentication system?",
    "top_k": 5,
    "mode": "hybrid",
    "enable_reranking": true
  }'
```

## Development

### Project Structure

```
F:\Project\Python\AI\rag\MyRag/
├── app/
│   ├── api/              # API endpoints
│   ├── core/             # Core business logic
│   │   ├── llm/          # LLM integration
│   │   ├── preprocessing/ # Document processing
│   │   ├── retrieval/    # Hybrid retrieval
│   │   └── ranking/      # Reranking and scoring
│   ├── db/               # Database connections
│   ├── models/           # SQLAlchemy models
│   ├── tasks/            # Celery tasks
│   └── utils/            # Utilities
├── docker/               # Docker configurations
├── tests/                # Test files
├── alembic/              # Database migrations
└── requirements.txt      # Python dependencies
```

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Lint
ruff check .

# Format
ruff format .

# Type checking
mypy app/
```

## Configuration

Key configuration options in `.env`:

| Category | Setting | Description | Default |
|----------|---------|-------------|---------|
| **LLM** | LLM_PROVIDER | ollama, vllm, openai, mock | ollama |
| **LLM** | LLM_MODEL | Model name | qwen2.5:14b |
| **Embeddings** | EMBEDDING_DEVICE | cuda, cpu, mps | cuda |
| **Retrieval** | RETRIEVAL_TOP_K | Candidates from each retriever | 50 |
| **Retrieval** | FINAL_TOP_K | Final results after reranking | 5 |
| **Fusion** | FUSION_K | RRF parameter | 60 |
| **Cache** | QUERY_CACHE_TTL | Query cache TTL (seconds) | 300 |
| **Performance** | MAX_RETRIEVAL_LATENCY_MS | Target latency | 300 |

See `docker/.env.example` for all available settings.

## Monitoring

### Prometheus Metrics

The application exposes metrics at `/metrics`:

- `myrag_requests_total`: Total request count
- `myrag_request_latency_seconds`: Request latency histogram
- `myrag_dense_retrieval_latency_ms`: Dense retrieval latency
- `myrag_sparse_retrieval_latency_ms`: Sparse retrieval latency
- `myrag_graph_retrieval_latency_ms`: Graph retrieval latency
- `myrag_rerank_confidence_avg`: Average confidence score

### Grafana Dashboards

Import the provided dashboard from `docker/grafana/dashboards/myrag-dashboard.json` to monitor:
- Request rate and latency
- Retrieval performance by method
- Confidence scores
- System health

## Performance Targets

- **Retrieval Latency**: <300ms at million-document scale
- **Concurrency**: 50+ simultaneous enterprise users
- **Document Processing**: Async with progress tracking
- **Availability**: High availability with distributed components

## Security & Compliance

- **Multi-tenant isolation**: Physical isolation at the database level
- **Auditability**: All answers link back to source document pages
- **Private deployment**: All components run offline without external API calls
- **Data governance**: Tiered storage with hot/warm/cold tiers

## Troubleshooting

### Milvus Connection Issues

```bash
# Check Milvus status
docker compose ps milvus-standalone

# View Milvus logs
docker compose logs -f milvus-standalone
```

### Elasticsearch Connection Issues

```bash
# Check Elasticsearch health
curl http://localhost:9200/_cluster/health

# View Elasticsearch logs
docker compose logs -f elasticsearch
```

### Redis Connection Issues

```bash
# Check Redis status
docker compose ps redis

# Test Redis connection
redis-cli ping
```

### Neo4j Connection Issues

```bash
# Check Neo4j status
docker compose ps neo4j

# View Neo4j logs
docker compose logs -f neo4j
```

## License

This project is proprietary and confidential. All rights reserved.

## Support

For issues and questions, please contact the development team.