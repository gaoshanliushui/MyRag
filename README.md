# MyRag - 分布式多租户混合检索企业级 RAG 系统

一个私有化的、企业级的 RAG 平台，采用自设计的密集 + 稀疏 + 知识图谱混合检索架构。面向政府和金融内网部署场景，支持可审计性、高并发、低幻觉和强合规性。

## 项目特点

### 核心架构

- **自适应语义预处理管道**：文档层次解析与语义边界检测进行分块（非固定窗口）。分块大小和重叠根据标题层级、段落完整性和语义连贯性动态调整。

- **三路混合检索**：
  - 密集向量检索（语义）- 通过 Milvus + BGE-M3 嵌入
  - 稀疏关键词检索（BM25）- 通过 Elasticsearch
  - 知识图谱多跳检索 - 通过 Neo4j
  - 动态权重融合算法 - 自动检测短实体查询与长语义推理场景并调整权重

- **两级分阶段重排序与幻觉抑制**：
  - 粗排序（轻量级）→ 精排序（高精度，Jina-Rerank）处理前 50 个候选
  - 检索置信度评分 + 交叉证据冲突检测
  - 所有答案支持源页码追溯，符合审计要求

- **分布式多租户隔离与数据治理**：
  - Milvus 分片集群，支持水平扩展
  - 租户级物理 Collection 隔离
  - 冷/热分层存储：热文档在内存索引中，冷/归档文档在磁盘映射
  - 增量索引、分片合并、检查点恢复（无需完整重建）

- **生产级高可用性**：
  - Celery 用于异步大文件处理，支持断路器、重试和死信队列
  - Redis 多级缓存：查询缓存、向量结果缓存、会话缓存
  - 基于 Prometheus 的全链路监控：检索延迟、令牌消耗、召回率、错误率

## 技术栈

- **后端**：Python 3.11+、FastAPI
- **向量数据库**：Milvus 2.5+（分布式集群）
- **搜索引擎**：Elasticsearch 8.17+
- **知识图谱**：Neo4j 5.28+
- **缓存**：Redis 7.4+
- **任务队列**：Celery 5.4+
- **嵌入模型**：BGE-M3（通过 sentence-transformers）
- **重排序模型**：Jina-Rerank V2
- **大语言模型**：Ollama / vLLM / OpenAI 兼容 API
- **监控**：Prometheus + Grafana
- **容器化**：Docker & Docker Compose

## 快速开始

### 前置要求

- Docker 和 Docker Compose
- Python 3.11+
- （可选）CUDA GPU 用于嵌入和重排序

### 1. 克隆项目并设置

```bash
cd F:\Project\Python\AI\rag\MyRag
```

### 2. 启动所有服务

```bash
cd docker
docker compose up -d
```

这将启动：
- PostgreSQL（带 pgvector）
- Milvus（带 etcd 和 MinIO）
- Elasticsearch
- Neo4j
- Redis
- Prometheus
- Grafana

### 3. 安装 Python 依赖（推荐使用 uv）

**方式一：使用 UV（推荐）**
```bash
# 安装 UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv sync

# 运行测试
uv run test
```

**方式二：使用 pip**
```bash
pip install -r requirements.txt

# 开发依赖
pip install -r requirements-dev.txt
```

### 4. 配置环境变量

```bash
cp docker/.env.example .env
```

编辑 `.env` 配置你的设置。关键配置：

```bash
# LLM 提供者（选项：ollama, vllm, openai, mock）
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b
LLM_API_URL=http://localhost:11434

# 嵌入设备（选项：cuda, cpu, mps）
EMBEDDING_DEVICE=cuda
```

### 5. 运行数据库迁移

```bash
# 使用 uv
uv run migrate

# 或使用 alembic
alembic upgrade head
```

### 6. 启动应用

**方式一：使用 uv**
```bash
uv run dev
```

**方式二：直接运行**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. 启动 Celery Worker（用于异步文档处理）

```bash
# 使用 uv
uv run worker

# 或直接运行
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

### 8. 访问应用

- **API 文档**: http://localhost:8000/docs（当 DEBUG=true 时）
- **健康检查**: http://localhost:8000/health
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000（admin/admin）
- **Redis Insight**: http://localhost:8001
- **Neo4j 浏览器**: http://localhost:7474（neo4j/neo4j123）

## API 使用示例

### 创建租户

```bash
curl -X POST "http://localhost:8000/api/v1/admin/tenants" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: admin-api-key" \
  -d '{
    "name": "我的公司",
    "description": "公司文档",
    "max_documents": 1000,
    "max_storage_mb": 1024
  }'
```

### 上传文档

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/documents/upload" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {api_key}" \
  -F "file=@document.pdf"
```

### 文档搜索

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/search" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {api_key}" \
  -d '{
    "query": "MyRag 的主要功能有哪些？",
    "top_k": 10,
    "mode": "hybrid",
    "enable_reranking": true,
    "enable_confidence": true
  }'
```

### 问答

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/qa" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {api_key}" \
  -d '{
    "question": "如何配置认证系统？",
    "top_k": 5,
    "mode": "hybrid",
    "enable_reranking": true
  }'
```

## 开发

### 项目结构

```
F:\Project\Python\AI\rag\MyRag/
├── app/
│   ├── api/              # API 端点
│   ├── core/             # 核心业务逻辑
│   │   ├── llm/          # LLM 集成
│   │   ├── preprocessing/ # 文档处理
│   │   ├── retrieval/    # 混合检索
│   │   └── ranking/      # 重排序和评分
│   ├── db/               # 数据库连接
│   ├── models/           # SQLAlchemy 模型
│   ├── tasks/            # Celery 任务
│   └── utils/            # 工具类
├── docker/               # Docker 配置
├── tests/                # 测试文件
├── alembic/              # 数据库迁移
└── requirements.txt      # Python 依赖
```

### 运行测试

```bash
# 使用 uv（推荐）
uv run test

# 或直接运行
pytest

# 带覆盖率
uv run test-cov
```

### 代码质量

```bash
# 使用 uv
uv run lint          # 代码检查
uv run format        # 代码格式化
uv run typecheck     # 类型检查

# 或直接运行
ruff check .
ruff format .
mypy app/
```

## 配置

`.env` 中的关键配置选项：

| 类别 | 配置项 | 描述 | 默认值 |
|------|--------|------|--------|
| **LLM** | LLM_PROVIDER | ollama, vllm, openai, mock | ollama |
| **LLM** | LLM_MODEL | 模型名称 | qwen2.5:14b |
| **嵌入** | EMBEDDING_DEVICE | cuda, cpu, mps | cuda |
| **检索** | RETRIEVAL_TOP_K | 每个检索器的候选数 | 50 |
| **检索** | FINAL_TOP_K | 重排序后的最终结果数 | 5 |
| **融合** | FUSION_K | RRF 参数 | 60 |
| **缓存** | QUERY_CACHE_TTL | 查询缓存 TTL（秒） | 300 |
| **性能** | MAX_RETRIEVAL_LATENCY_MS | 目标延迟 | 300 |

完整配置请查看 `docker/.env.example`。

## 监控

### Prometheus 指标

应用在 `/metrics` 端点暴露指标：

- `myrag_requests_total`: 总请求计数
- `myrag_request_latency_seconds`: 请求延迟直方图
- `myrag_dense_retrieval_latency_ms`: 密集检索延迟
- `myrag_sparse_retrieval_latency_ms`: 稀疏检索延迟
- `myrag_graph_retrieval_latency_ms`: 知识图谱检索延迟
- `myrag_rerank_confidence_avg`: 平均置信度评分

### Grafana 仪表板

从 `docker/grafana/dashboards/myrag-dashboard.json` 导入仪表板，监控：
- 请求率和延迟
- 检索方法性能
- 置信度评分
- 系统健康状态

## 性能目标

- **检索延迟**: <300 毫秒（百万级文档规模）
- **并发**: 50+ 同时企业用户
- **文档处理**: 异步处理，带进度追踪
- **可用性**: 分布式组件高可用

## 安全与合规

- **多租户隔离**: 数据库级别的物理隔离
- **可审计性**: 所有答案链接回源文档页码
- **私有部署**: 所有组件离线运行，无需外部 API 调用
- **数据治理**: 热/温/冷三级存储

## 故障排除

### Milvus 连接问题

```bash
# 检查 Milvus 状态
docker compose ps milvus-standalone

# 查看 Milvus 日志
docker compose logs -f milvus-standalone
```

### Elasticsearch 连接问题

```bash
# 检查 Elasticsearch 健康
curl http://localhost:9200/_cluster/health

# 查看 Elasticsearch 日志
docker compose logs -f elasticsearch
```

### Redis 连接问题

```bash
# 检查 Redis 状态
docker compose ps redis

# 测试 Redis 连接
redis-cli ping
```

### Neo4j 连接问题

```bash
# 检查 Neo4j 状态
docker compose ps neo4j

# 查看 Neo4j 日志
docker compose logs -f neo4j
```

## 使用 UV 管理依赖

本项目支持 [uv](https://github.com/astral-sh/uv) 包管理器，提供更快的依赖安装和管理。

### 安装 UV

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 常用 UV 命令

```bash
# 安装所有依赖
uv sync

# 添加新包
uv add new-package
uv add --dev new-dev-package

# 运行命令
uv run dev         # 启动开发服务器
uv run test        # 运行测试
uv run format      # 格式化代码
uv run migrate     # 数据库迁移

# 查看详细信息
uv --help
```

详细指南请查看 [UV_GUIDE.md](UV_GUIDE.md)。

## 贡献指南

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)（如果存在）了解如何贡献。

## 许可证

本项目为专有软件，保留所有权利。

## 支持

如有问题或疑问，请联系开发团队。