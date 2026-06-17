# MyRag 中文 API 文档

## 概述

MyRag 提供了一套完整的 RESTful API，支持租户管理、文档处理、混合检索和问答功能。所有 API 端点都支持 JSON 格式的请求和响应。

## 认证

### 租户请求认证

所有租户相关的请求必须包含以下头部：

```http
X-Tenant-ID: {tenant_id}
X-API-Key: {tenant_api_key}
```

**示例：**

```bash
curl -H "X-Tenant-ID: abc123-def456" \
     -H "X-API-Key: tk_abc123def456ghi789jkl" \
     http://localhost:8000/api/v1/{tenant_id}/documents
```

### 管理员请求认证

管理员操作需要管理员 API 密钥：

```http
X-API-Key: {admin_api_key}
```

**示例：**

```bash
curl -H "X-API-Key: admin_secret_key_123456" \
     http://localhost:8000/api/v1/admin/tenants
```

## API 端点

### 一、管理端点 `/api/v1/admin/`

#### 1.1 系统健康检查

**GET** `/api/v1/admin/health`

检查所有服务的健康状态。

**请求：**
```http
GET /api/v1/admin/health
```

**响应：**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 1234.5,
  "services": {
    "database": "ok",
    "redis": "ok",
    "milvus": "ok",
    "elasticsearch": "ok",
    "neo4j": "ok"
  },
  "details": {}
}
```

#### 1.2 系统统计信息

**GET** `/api/v1/admin/stats`

获取系统级统计数据。

**请求：**
```http
GET /api/v1/admin/stats
X-API-Key: admin_api_key
```

**响应：**
```json
{
  "total_tenants": 10,
  "total_documents": 500,
  "total_chunks": 50000,
  "total_queries_today": 1250,
  "average_latency_ms": 150.5,
  "cache_hit_rate": 0.85,
  "storage_used_mb": 1024,
  "storage_available_mb": 9216,
  "active_tasks": 5,
  "queued_tasks": 10
}
```

#### 1.3 Prometheus 指标

**GET** `/api/v1/admin/metrics`

获取 Prometheus 格式的监控指标。

**请求：**
```http
GET /api/v1/admin/metrics
X-API-Key: admin_api_key
```

**响应：**（Prometheus 格式文本）

```
# HELP myrag_requests_total Total request count
# TYPE myrag_requests_total counter
myrag_requests_total{method="GET",endpoint="/health",tenant_id="anonymous",status="200"} 123
# HELP myrag_request_latency_seconds Request latency
# TYPE myrag_request_latency_seconds histogram
myrag_request_latency_seconds_bucket{method="GET",endpoint="/health",tenant_id="anonymous",le="0.01"} 100
...
```

#### 1.4 创建租户

**POST** `/api/v1/admin/tenants`

创建新的租户。

**请求：**
```http
POST /api/v1/admin/tenants
X-API-Key: admin_api_key
Content-Type: application/json

{
  "name": "我的公司",
  "description": "公司内部知识库",
  "max_documents": 1000,
  "max_storage_mb": 1024,
  "max_users": 10,
  "settings": {
    "retrieval_top_k": 50,
    "confidence_threshold": 0.6
  }
}
```

**响应：**
```json
{
  "id": "abc123-def456-ghi789",
  "name": "我的公司",
  "description": "公司内部知识库",
  "status": "ACTIVE",
  "max_documents": 1000,
  "max_storage_mb": 1024,
  "max_users": 10,
  "current_documents": 0,
  "current_storage_mb": 0,
  "current_users": 0,
  "queries_today": 0,
  "last_query_date": null,
  "api_key": "tk_abc123def456ghi789jkl012345",
  "created_at": "2025-06-17T12:00:00Z",
  "updated_at": "2025-06-17T12:00:00Z"
}
```

#### 1.5 列出租户

**GET** `/api/v1/admin/tenants`

获取所有租户列表。

**请求：**
```http
GET /api/v1/admin/tenants?name=测试&limit=20&offset=0
X-API-Key: admin_api_key
```

**参数：**
- `name` (可选): 按名称筛选
- `limit` (可选): 每页数量，默认 20
- `offset` (可选): 偏移量，默认 0

**响应：**
```json
[
  {
    "id": "abc123-def456",
    "name": "我的公司",
    "status": "ACTIVE",
    ...
  }
]
```

#### 1.6 获取租户详情

**GET** `/api/v1/admin/tenants/{tenant_id}`

获取租户详细信息。

**请求：**
```http
GET /api/v1/admin/tenants/abc123-def456
X-API-Key: admin_api_key
```

**响应：**
```json
{
  "id": "abc123-def456",
  "name": "我的公司",
  ...
}
```

#### 1.7 更新租户

**PUT** `/api/v1/admin/tenants/{tenant_id}`

更新租户配置。

**请求：**
```http
PUT /api/v1/admin/tenants/abc123-def456
X-API-Key: admin_api_key
Content-Type: application/json

{
  "name": "我的公司（更新）",
  "max_documents": 2000,
  "settings": {
    "retrieval_top_k": 30
  }
}
```

#### 1.8 删除租户

**DELETE** `/api/v1/admin/tenants/{tenant_id}`

软删除租户（异步清理数据）。

**请求：**
```http
DELETE /api/v1/admin/tenants/abc123-def456
X-API-Key: admin_api_key
```

**响应：** 204 No Content

#### 1.9 重新生成 API 密钥

**POST** `/api/v1/admin/tenants/{tenant_id}/regenerate-api-key`

为租户重新生成 API 密钥。

**请求：**
```http
POST /api/v1/admin/tenants/abc123-def456/regenerate-api-key
X-API-Key: admin_api_key
```

**响应：**
```json
{
  "id": "abc123-def456",
  "api_key": "new_tk_xyz789abc456def012345",
  ...
}
```

#### 1.10 获取系统配置

**GET** `/api/v1/admin/config`

获取当前系统配置。

**请求：**
```http
GET /api/v1/admin/config
X-API-Key: admin_api_key
```

**响应：**
```json
{
  "retrieval_top_k": 50,
  "confidence_threshold": 0.6,
  "max_retrieval_latency_ms": 300,
  "query_cache_ttl": 300,
  "vector_cache_ttl": 1800,
  "session_cache_ttl": 3600
}
```

---

### 二、租户文档端点 `/api/v1/{tenant_id}/documents/`

#### 2.1 上传文档

**POST** `/api/v1/{tenant_id}/documents/upload`

上传文档文件。

**请求：**
```http
POST /api/v1/{tenant_id}/documents/upload
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
Content-Type: multipart/form-data

file: @document.pdf
```

**响应：**
```json
{
  "id": "doc_abc123",
  "tenant_id": "tenant_123",
  "filename": "abc123def456.pdf",
  "original_filename": "document.pdf",
  "file_type": "pdf",
  "file_size": 1024576,
  "file_path": "./uploads/tenant_123/abc123def456.pdf",
  "status": "PENDING",
  "total_pages": 0,
  "total_chunks": 0,
  "total_tokens": 0,
  "processing_task_id": "task_123",
  "created_at": "2025-06-17T12:00:00Z"
}
```

#### 2.2 列出文档

**GET** `/api/v1/{tenant_id}/documents`

获取租户的文档列表。

**请求：**
```http
GET /api/v1/{tenant_id}/documents?status=COMPLETED&file_type=pdf&page=1&page_size=20
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
```

**响应：**
```json
{
  "documents": [
    {
      "id": "doc_abc123",
      "filename": "document.pdf",
      "status": "COMPLETED",
      ...
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

#### 2.3 获取文档详情

**GET** `/api/v1/{tenant_id}/documents/{document_id}`

获取文档详细信息。

**请求：**
```http
GET /api/v1/{tenant_id}/documents/doc_abc123
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
```

**响应：**
```json
{
  "id": "doc_abc123",
  "filename": "document.pdf",
  "status": "COMPLETED",
  "total_pages": 10,
  "total_chunks": 25,
  "total_tokens": 15000,
  "access_count": 5,
  "created_at": "2025-06-17T12:00:00Z",
  ...
}
```

#### 2.4 获取文档处理状态

**GET** `/api/v1/{tenant_id}/documents/{document_id}/status`

获取文档的处理进度。

**请求：**
```http
GET /api/v1/{tenant_id}/documents/doc_abc123/status
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
```

**响应：**
```json
{
  "id": "doc_abc123",
  "status": "PROCESSING",
  "total_pages": 10,
  "total_chunks": 0,
  "total_tokens": 0,
  "processing_progress": 0.5,
  "processing_error": null,
  "estimated_completion": null
}
```

#### 2.5 删除文档

**DELETE** `/api/v1/{tenant_id}/documents/{document_id}`

删除文档（软删除）。

**请求：**
```http
DELETE /api/v1/{tenant_id}/documents/doc_abc123
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
```

**响应：** 204 No Content

---

### 三、检索和问答端点 `/api/v1/{tenant_id}/retrieval/`

#### 3.1 混合搜索

**POST** `/api/v1/{tenant_id}/retrieval/search`

执行混合检索。

**请求：**
```http
POST /api/v1/{tenant_id}/retrieval/search
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
Content-Type: application/json

{
  "query": "MyRag 的主要功能有哪些？",
  "top_k": 10,
  "mode": "hybrid",
  "enable_reranking": true,
  "enable_confidence": true,
  "enable_conflict_detection": false,
  "filters": {
    "document_ids": ["doc_123", "doc_456"]
  }
}
```

**参数：**
- `query` (必需): 搜索查询
- `top_k` (可选): 返回结果数量，默认 5
- `mode` (可选): 检索模式，`hybrid`（默认）、`dense`、`sparse`、`graph`
- `enable_reranking` (可选): 是否启用重排序，默认 true
- `enable_confidence` (可选): 是否启用置信度评分，默认 true
- `enable_conflict_detection` (可选): 是否启用冲突检测，默认 false
- `filters` (可选): 过滤条件

**响应：**
```json
{
  "query": "MyRag 的主要功能有哪些？",
  "results": [
    {
      "chunk": {
        "chunk_id": "chunk_abc123",
        "document_id": "doc_123",
        "page_number": 5,
        "chunk_index": 3,
        "content": "MyRag 提供多种功能...",
        "confidence": 0.85,
        "final_rank": 1
      },
      "source": {
        "chunk_id": "chunk_abc123",
        "document_id": "doc_123",
        "document_name": "MyRag手册.pdf",
        "page_number": 5,
        "chunk_index": 3,
        "heading_text": "功能介绍",
        "excerpt": "MyRag 提供多种功能...",
        "score": 0.92
      }
    }
  ],
  "conflicts": [],
  "metrics": {
    "latency_ms": 150.5,
    "dense_latency_ms": 45.2,
    "sparse_latency_ms": 30.1,
    "graph_latency_ms": 50.3,
    "fusion_latency_ms": 20.0,
    "rerank_latency_ms": 15.0,
    "total_candidates": 50,
    "final_candidates": 10,
    "query_type": "SEMANTIC",
    "weights_used": {
      "dense": 0.6,
      "sparse": 0.2,
      "graph": 0.2
    }
  },
  "has_more": false,
  "page": 1
}
```

#### 3.2 问答

**POST** `/api/v1/{tenant_id}/retrieval/qa`

基于文档的问答。

**请求：**
```http
POST /api/v1/{tenant_id}/retrieval/qa
X-Tenant-ID: {tenant_id}
X-API-Key: {api_key}
Content-Type: application/json

{
  "question": "如何配置认证系统？",
  "top_k": 5,
  "mode": "hybrid",
  "enable_reranking": true,
  "enable_confidence": true,
  "enable_conflict_detection": true,
  "filters": {
    "document_ids": ["doc_123"]
  }
}
```

**响应：**
```json
{
  "question": "如何配置认证系统？",
  "answer": "配置认证系统需要以下几个步骤...\n1. 安装认证模块...\n2. 配置权限策略...",
  "sources": [
    {
      "document_id": "doc_123",
      "document_name": "配置指南.pdf",
      "page_number": 15,
      "chunk_id": "chunk_abc123",
      "excerpt": "认证系统配置步骤...",
      "relevance_score": 0.85
    }
  ],
  "confidence": 0.82,
  "conflicts": [],
  "metrics": {
    "latency_ms": 250.3,
    ...
  },
  "generated_at": "2025-06-17T12:30:00Z",
  "model_used": "qwen2.5:14b"
}
```

---

### 四、错误响应

所有错误响应都遵循以下格式：

```json
{
  "error": "错误详细信息",
  "error_code": "错误代码",
  "details": {
    "additional": "信息"
  },
  "request_id": "唯一请求ID"
}
```

**常见错误代码：**

| 状态码 | 错误代码 | 说明 |
|--------|----------|------|
| 400 | BAD_REQUEST | 请求参数错误 |
| 401 | UNAUTHORIZED | 认证失败 |
| 403 | FORBIDDEN | 权限不足 |
| 404 | NOT_FOUND | 资源不存在 |
| 500 | INTERNAL_ERROR | 服务器内部错误 |
| 503 | SERVICE_UNAVAILABLE | 服务暂时不可用 |

---

## 代码示例

### Python 示例

```python
import requests

# 租户搜索
def search_documents(tenant_id, api_key, query):
    url = f"http://localhost:8000/api/v1/{tenant_id}/retrieval/search"
    headers = {
        "X-Tenant-ID": tenant_id,
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "query": query,
        "top_k": 10,
        "mode": "hybrid",
        "enable_reranking": True
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()

# 问答
def ask_question(tenant_id, api_key, question):
    url = f"http://localhost:8000/api/v1/{tenant_id}/retrieval/qa"
    headers = {
        "X-Tenant-ID": tenant_id,
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "question": question,
        "top_k": 5,
        "mode": "hybrid"
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()
```

### JavaScript/Node.js 示例

```javascript
const axios = require('axios');

// 租户搜索
async function searchDocuments(tenantId, apiKey, query) {
    const response = await axios.post(
        `http://localhost:8000/api/v1/${tenantId}/retrieval/search`,
        {
            query: query,
            top_k: 10,
            mode: 'hybrid',
            enable_reranking: true
        },
        {
            headers: {
                'X-Tenant-ID': tenantId,
                'X-API-Key': apiKey
            }
        }
    );
    return response.data;
}

// 问答
async function askQuestion(tenantId, apiKey, question) {
    const response = await axios.post(
        `http://localhost:8000/api/v1/${tenantId}/retrieval/qa`,
        {
            question: question,
            top_k: 5,
            mode: 'hybrid'
        },
        {
            headers: {
                'X-Tenant-ID': tenantId,
                'X-API-Key': apiKey
            }
        }
    );
    return response.data;
}
```

---

## 最佳实践

1. **使用分页**: 列表接口使用分页避免返回过多数据
2. **合理设置 top_k**: 检索时合理设置 top_k 值，平衡准确性和性能
3. **启用缓存**: 利用缓存提高性能
4. **处理错误**: 正确处理各种错误情况
5. **使用过滤**: 使用 filters 参数缩小检索范围
6. **监控性能**: 关注 metrics 中的性能数据

---

如有问题，请参考 [开发文档](DEVELOPMENT_CN.md) 或联系支持团队。