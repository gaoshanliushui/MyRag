# MyRag 中文开发文档

## 项目概述

MyRag 是一个企业级的分布式多租户混合检索 RAG 系统。本项目采用先进的密集 + 稀疏 + 知识图谱三路混合检索架构，适用于需要高并发、低延迟、可审计的政府和金融场景。

## 架构设计

### 核心组件

1. **API 层** (`app/api/v1/`)
   - `tenants.py`: 租户管理端点
   - `documents.py`: 文档上传、查询、删除
   - `retrieval.py`: 混合搜索和问答
   - `admin.py`: 系统管理、监控、健康检查

2. **核心业务层** (`app/core/`)
   - `llm/provider.py`: LLM 集成（支持 Ollama/vLLM/OpenAI/Mock）
   - `preprocessing/`: 
     - `parser.py`: 文档解析（PDF/DOCX/TXT/HTML）
     - `chunker.py`: 语义分块
     - `cleaner.py`: 去噪清洗
     - `pipeline.py`: 完整预处理流水线
   - `retrieval/`:
     - `dense.py`: 密集向量检索（Milvus + BGE-M3）
     - `sparse.py`: 稀疏关键词检索（Elasticsearch + BM25）
     - `graph.py`: 知识图谱检索（Neo4j）
     - `fusion.py`: 动态权重融合（基于查询类型）
     - `hybrid.py`: 混合检索协调器
   - `ranking/`:
     - `coarse.py`: 粗排序
     - `fine.py`: 精排序（Jina-Rerank）
     - `confidence.py`: 置信度评分
     - `conflict.py`: 冲突检测
   - `tenant/isolation.py`: 租户隔离验证管理器
   - `monitoring/metrics.py`: Prometheus 指标收集

3. **数据库层** (`app/db/`)
   - `session.py`: PostgreSQL/SQLAlchemy 异步会话
   - `milvus.py`: Milvus 向量数据库客户端
   - `elasticsearch.py`: Elasticsearch 检索客户端
   - `neo4j.py`: Neo4j 知识图谱客户端
   - `redis.py`: Redis 缓存客户端

4. **模型层** (`app/models/`)
   - `base.py`: Base SQLAlchemy 模型
   - `tenant.py`: Tenant 模型
   - `document.py`: Document 和 Chunk 模型
   - `schemas.py`: Pydantic 模式定义

5. **任务层** (`app/tasks/`)
   - `celery_app.py`: Celery 应用配置
   - `documents.py`: 文档处理任务
   - `tenant.py`: 租户清理任务
   - `admin.py`: 管理任务

6. **工具层** (`app/utils/`)
   - `security.py`: API 密钥生成、验证、哈希
   - `exceptions.py`: 自定义异常
   - `logging.py`: 结构化日志
   - `embeddings.py`: 嵌入服务

## 快速开发指南

### 本地开发环境搭建

```bash
# 1. 安装 Python 3.11+
# 2. 安装 uv（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 克隆项目
cd F:\Project\Python\AI\rag\MyRag

# 4. 同步依赖
uv sync

# 5. 配置环境
cp docker/.env.example .env
# 编辑 .env 配置

# 6. 启动服务
cd docker
docker compose up -d

# 7. 运行迁移
uv run migrate

# 8. 启动应用
uv run dev
```

### 代码风格规范

1. **命名约定**
   - 类名：PascalCase
   - 变量和函数名：snake_case
   - 常量：UPPER_SNAKE_CASE

2. **注释规范**
   - 所有公共类、方法必须有 docstring
   - 复杂逻辑块必须有注释说明
   - 使用 Google 风格的 docstring

3. **类型提示**
   - 所有函数参数和返回值必须有类型提示
   - 使用 Pydantic 模型定义数据结构

### 添加新功能流程

1. **分析需求** → 在 CLAUDE.md 中记录
2. **设计接口** → 定义 API 端点和 Pydantic 模式
3. **实现核心逻辑** → 在 `app/core/` 中实现
4. **集成到 API** → 在 `app/api/v1/` 中添加端点
5. **添加数据库迁移** → 在 `alembic/versions/` 中创建迁移
6. **编写测试** → 在 `tests/` 中添加单元测试和集成测试
7. **代码检查** → 运行 `uv run lint` 和 `uv run format`
8. **提交代码** → 添加有意义的 commit message

### 常用开发命令

```bash
# 代码检查和格式化
uv run lint
uv run format

# 类型检查
uv run typecheck

# 运行测试
uv run test
uv run test-cov

# 数据库操作
uv run migrate
uv run migrate-revision "描述新迁移"

# 清理缓存
uv run clean-all
```

## API 设计规范

### 端点命名

```
GET    /api/v1/{tenant_id}/documents          # 列出文档
POST   /api/v1/{tenant_id}/documents          # 创建文档
GET    /api/v1/{tenant_id}/documents/{id}     # 获取文档详情
PUT    /api/v1/{tenant_id}/documents/{id}     # 更新文档
DELETE /api/v1/{tenant_id}/documents/{id}     # 删除文档
POST   /api/v1/{tenant_id}/documents/upload   # 上传文件
```

### 响应格式

```json
// 成功响应
{
  "status": "success",
  "data": { ... }
}

// 错误响应
{
  "error": "详细错误信息",
  "error_code": "错误代码",
  "details": { "额外信息": "值" },
  "request_id": "请求唯一ID"
}
```

### 认证机制

- **租户请求**: `X-Tenant-ID` + `X-API-Key` 头部
- **管理员请求**: `X-API-Key` 头部（使用管理员密钥）

## 测试策略

### 单元测试

```python
# tests/test_module.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_function():
    # 测试逻辑
    pass
```

### 集成测试

```python
# tests/test_integration.py
from fastapi.testclient import TestClient
from app.main import app

def test_api_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/admin/health")
    assert response.status_code == 200
```

### 测试运行

```bash
# 运行所有测试
uv run test

# 运行带覆盖率的测试
uv run test-cov

# 查看覆盖率报告
# 打开 htmlcov/index.html
```

## 性能优化建议

1. **数据库查询优化**
   - 使用异步查询
   - 避免 N+1 问题
   - 使用索引

2. **缓存策略**
   - 查询缓存（Redis）
   - 向量结果缓存
   - 会话缓存

3. **异步处理**
   - 大文件处理使用 Celery
   - 长耗时操作使用异步

4. **连接池管理**
   - 合理配置数据库连接池
   - 复用数据库连接

## 部署建议

### 生产环境配置

1. **Docker Compose 生产模式**
   - 使用 `docker compose.prod.yml`
   - 配置副本数量和资源限制

2. **环境变量**
   - 从 secret 管理系统读取敏感信息
   - 使用环境变量替代硬编码

3. **监控告警**
   - 配置 Prometheus 告警规则
   - 设置性能阈值告警

4. **日志管理**
   - 集中日志收集（ELK/Grafana Loki）
   - 日志轮转和清理

### 扩展性考虑

1. **水平扩展**
   - API 服务器无状态，可水平扩展
   - 使用负载均衡器

2. **垂直扩展**
   - 升级 Milvus 集群配置
   - 增加 Celery worker 数量

3. **数据分片**
   - 按租户分片数据库
   - 按时间范围分片向量索引

## 常见问题

### Q1: 如何添加新的文档类型支持？

**步骤：**
1. 在 `app/core/preprocessing/parser.py` 中添加新的解析方法
2. 在 `DocumentParser.parse()` 中注册新的文件类型
3. 编写单元测试验证解析功能

### Q2: 如何自定义检索策略？

**步骤：**
1. 实现新的检索器类（继承或扩展现有检索器）
2. 在 `app/core/retrieval/fusion.py` 中添加权重计算逻辑
3. 在 `app/core/retrieval/hybrid.py` 中集成新的检索器

### Q3: 如何添加新的 LLM 提供者？

**步骤：**
1. 在 `app/core/llm/provider.py` 中添加新的 `generate_*` 方法
2. 在 `LLMProvider.generate()` 中注册新的提供者类型
3. 添加相应的配置选项到 `.env`

### Q4: 如何优化检索延迟？

**建议：**
1. 检查 Milvus 索引类型和参数（HNSW 的 efConstruction 和 ef）
2. 增加 Elasticsearch 副本数
3. 优化 Neo4j 查询
4. 使用更小的 top_k
5. 启用缓存

## 资源链接

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/)
- [Milvus 文档](https://milvus.io/docs/)
- [Elasticsearch 文档](https://www.elastic.co/guide/)
- [Neo4j 文档](https://neo4j.com/docs/)
- [Celery 文档](https://docs.celeryq.dev/)
- [Prometheus 文档](https://prometheus.io/docs/)

## 贡献指南

### 代码提交规范

```
feat: 添加新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 添加测试
chore: 构建/工具变更
```

### 代码审查要点

1. ✅ 代码风格符合规范
2. ✅ 类型提示完整
3. ✅ 单元测试覆盖
4. ✅ 错误处理完善
5. ✅ 性能考虑合理
6. ✅ 文档注释清晰

---

如有任何问题，请联系开发团队。