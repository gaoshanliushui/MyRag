# LangChain 集成说明

本文档记录 MyRag 项目对 LangChain 的集成方案。所有改动遵循 **薄包装（facade）** 原则：
保持原有 API 接口与配置不变，仅在内部使用 LangChain 标准抽象。

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                       API / Celery / Tasks                       │
│           (FastAPI routes + Celery — 调用签名 0 改动)             │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  LLMProvider         EmbeddingService       PreprocessingPipeline
   (facade)            (facade)                 (facade)
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌───────────────────┐    ┌─────────────────┐
│  factory.py  │    │  embeddings/      │    │ loaders.py      │
│  (init_chat_ │    │  bge_m3.py        │    │ (LangChain      │
│   model)     │    │ (HuggingFace      │    │  DocumentLoader)│
│              │    │  Embeddings)      │    │                 │
│              │    │                   │    │ semantic_       │
│              │    │                   │    │ splitter.py     │
│              │    │                   │    │ (TextSplitter   │
│              │    │                   │    │  subclass)      │
└──────────────┘    └───────────────────┘    └─────────────────┘
        │                                             │
        ▼                                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                          core/chains/                            │
│  ┌────────────────────┐         ┌──────────────────────┐         │
│  │ retrieval/         │         │ chains/qa_chain.py   │         │
│  │ langchain_         │◄────────│ (LCEL Runnable chain)│         │
│  │ retrievers.py      │         │                      │         │
│  │ (BaseRetriever     │         │ RunnableParallel     │         │
│  │  subclasses)       │         │  → RunnableLambda    │         │
│  │                    │         │  → ChatPromptTemplate│         │
│  │ ensemble.py        │         │  → ChatModel         │         │
│  │ (HybridEnsemble)   │         │  → StrOutputParser   │         │
│  └────────────────────┘         └──────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       DB Clients (Milvus / ES / Neo4j / Redis)
                       (保持自实现的 9 字段 schema、IK 分词、多跳 Cypher)
```

## 2. 模块清单

### 2.1 新增文件

| 文件 | 角色 |
|------|------|
| `app/core/llm/factory.py` | ChatModel 工厂（`init_chat_model`） |
| `app/core/embeddings/bge_m3.py` | BGE-M3 `Embeddings` 子类 |
| `app/core/preprocessing/loaders.py` | DocumentLoader 路由 |
| `app/core/preprocessing/semantic_splitter.py` | `TextSplitter` 子类（包装原 `SemanticChunker`） |
| `app/core/retrieval/langchain_retrievers.py` | 三个 `BaseRetriever` 子类 |
| `app/core/retrieval/ensemble.py` | `HybridEnsembleRetriever`（async 原生） |
| `app/core/chains/qa_chain.py` | LCEL QA Chain |
| `app/core/chains/prompts.py` | Prompt 模板集中管理 |
| `tests/test_chains_qa.py` | LCEL Chain 测试 |
| `tests/test_langchain_retrievers.py` | Retriever + Splitter + Loader 测试 |

### 2.2 重构文件（保留 facade）

| 文件 | 改动 |
|------|------|
| `app/core/llm/provider.py` | 改为薄包装，删除手写 HTTP 调用（约 350 行删除） |
| `app/core/llm/__init__.py` | 导出新工厂函数 |
| `app/utils/embeddings.py` | 委托 `BGE_M3_Embeddings`，保留 Redis 缓存 |
| `app/core/preprocessing/pipeline.py` | 新增 `_process_via_langchain`，自动 fallback |
| `app/core/retrieval/hybrid.py` | 委托 `HybridEnsembleRetriever.ainvoke` |
| `app/api/v1/retrieval.py` | `/qa` 端点改用 `build_qa_chain().ainvoke()` |
| `app/db/milvus.py` | 补充缺失的 `get_milvus_client()` 工厂函数 |
| `app/config.py` | 用 `BeforeValidator` 修复 list 解析 + 关闭 decoding |
| `pyproject.toml` | 添加 langchain-* 依赖 |
| `CLAUDE.md` | 添加 LangChain 集成说明 |

## 3. 设计要点

### 3.1 多租户隔离保留

- `Tenant.get_milvus_collection() / get_es_index() / get_neo4j_label()` 保持不变
- LangChain 组件通过 `collection_name / index_name / label` 参数接收租户命名
- `HybridRetriever` 通过 `_TenantShim` 暴露这三方法供 `build_ensemble_retriever` 使用

### 3.2 业务组件保留

- `DynamicWeightFusion` — 动态权重 RRF（query-aware）
- `CoarseRanker` / `ConfidenceScorer` / `ConflictDetector` — 业务定制组件
- `SemanticChunker` — 通过 `SemanticTextSplitter` 包装，保留语义边界算法

### 3.3 用 LCEL 编排 RAG 流程

`app/core/chains/qa_chain.py` 使用 LangChain Expression Language：

```python
retrieve = RunnableParallel({
    "docs": RunnableLambda(retrieve_docs),
    "question": RunnablePassthrough(),
})
inject_context = RunnableLambda(lambda p: {"context": format_docs(p["docs"]),
                                            "question": p["question"]})
chain = retrieve | inject_context | QA_PROMPT | llm | StrOutputParser()
```

业务后处理（置信度、冲突检测、metrics）仍在 API 端点层执行，LCEL 只接管"取 → 拼 → 问 → 解析"。

## 4. 兼容性

| 接口 | 兼容性 |
|------|--------|
| API 路由（`/search`, `/qa`, `/sources/{id}`） | ✅ 不变 |
| 配置（环境变量） | ✅ 不变（仅修复 list 解析） |
| 数据库 schema（PostgreSQL + Alembic） | ✅ 不变 |
| Celery 任务签名 | ✅ 不变 |
| 多租户资源命名 | ✅ 不变 |
| `LLMProvider.generate() / stream_generate()` | ✅ 签名不变 |
| `EmbeddingService.encode_*_async()` | ✅ 签名不变 |
| `HybridRetriever.retrieve()` | ✅ 签名不变 |

## 5. 测试

### 5.1 新增测试

```
tests/test_chains_qa.py               5 tests
tests/test_langchain_retrievers.py    10 tests
                                     ─────────
                                     15 tests, all passing
```

测试使用 LangChain 提供的 `FakeListChatModel`、`FakeEmbeddings`、`FakeRetriever` 进行 mock，避免依赖外部服务和模型下载。

### 5.2 运行

```bash
uv run python -m pytest tests/test_chains_qa.py tests/test_langchain_retrievers.py -v
```

## 6. 已知预存问题（未在本次集成中修复）

- `app/models/document.py` 在 `Document` ORM 中使用了 SQLAlchemy 2.0 保留属性名 `metadata`（应改为 `doc_metadata`），导致 `app.api.v1.retrieval` 等模块无法导入
- `app/db/neo4j.py` 中存在 `delete_tenant_data_async` 函数重复定义
- 这些问题不属于 LangChain 集成范围，建议单独 PR 修复

## 7. 未来可选优化（不在本次范围）

- 替换 `langchain_community.document_loaders` 为独立集成包（社区包已停止维护）
- 引入 `langchain.callbacks`（LangSmith / LangFuse）做 trace
- 用 `langchain.agents` 把 RAG 包成 tool
- 引入 `langchain.retrievers.multi_query` / `self_query` 增强检索
- 升级 `langchain-milvus` 后直接替换自实现的 `MilvusClient`