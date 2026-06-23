# MyRag - 项目文档

## 项目说明

MyRag 是一个分布式多租户混合检索企业级 RAG 系统，采用**自设计的密集 + 稀疏 + 知识图谱混合检索架构**，并以 [LangChain](https://python.langchain.com/) 作为标准抽象层（LLM / Embeddings / DocumentLoader / TextSplitter / Retriever / LCEL）。

### 🧱 LangChain 集成概览

- **LLM**：`app/core/llm/factory.py` 统一创建 `ChatOpenAI / ChatOllama / FakeListChatModel`；`app/core/llm/provider.py` 作为业务门面，保留原 `LLMProvider.generate/stream_generate` 签名。
- **Embeddings**：`app/core/embeddings/bge_m3.py` 通过 `HuggingFaceEmbeddings` 包装 BGE-M3；`app/utils/embeddings.py` 提供带 Redis 缓存的异步门面。
- **DocumentLoader**：`app/core/preprocessing/loaders.py` 统一 PDF/DOCX/TXT/HTML/MD 的 LangChain Loader 路由。
- **TextSplitter**：`app/core/preprocessing/semantic_splitter.py` 是 LangChain `TextSplitter` 子类，复用项目原有 `SemanticChunker` 语义边界算法。
- **Retriever**：`app/core/retrieval/langchain_retrievers.py` 实现 `BaseRetriever` 子类（MilvusTenantRetriever / ESTenantRetriever / Neo4jTenantRetriever），由 `app/core/retrieval/ensemble.py` 组合为 `EnsembleRetriever`。
- **LCEL Chain**：`app/core/chains/qa_chain.py` 使用 `RunnableParallel / RunnablePassthrough / RunnableLambda / ChatPromptTemplate / StrOutputParser` 编排 RAG 流程。

> 业务定制组件（多租户隔离、动态权重融合 `DynamicWeightFusion`、粗排、置信度、冲突检测）保留自实现，确保 LangChain 集成不破坏核心业务规则。

## 文档导航

所有项目文档都存储在 `doc/` 目录下：

### 📚 核心文档

| 文档 | 说明 |
|------|------|
| [README.md](doc/README.md) | 项目概述、快速开始、安装指南 |
| [PROJECT_SUMMARY.md](doc/PROJECT_SUMMARY.md) | 项目完成总结 |
| [DOCUMENTATION_INDEX_CN.md](doc/DOCUMENTATION_INDEX_CN.md) | 中文文档索引 |

### 🛠️ 开发文档

| 文档 | 说明 |
|------|------|
| [DEVELOPMENT_CN.md](doc/DEVELOPMENT_CN.md) | 开发指南（中文） |
| [SETUP_GUIDE_CN.md](doc/SETUP_GUIDE_CN.md) | 环境设置指南（中文） |
| [API_DOCUMENTATION_CN.md](doc/API_DOCUMENTATION_CN.md) | API 文档（中文） |

### 🐳 Docker 配置

| 文档 | 说明 |
|------|------|
| [Docker/README_CN.md](doc/Docker/README_CN.md) | Docker 服务配置说明 |

### ❓ 问题解答

| 文档 | 说明 |
|------|------|
| [FAQ_CN.md](doc/FAQ_CN.md) | 常见问题解答（中文） |

### 📦 依赖管理

| 文档 | 说明 |
|------|------|
| [UV_GUIDE.md](doc/UV_GUIDE.md) | UV 包管理器使用指南 |
| [pyproject.toml](doc/pyproject.toml) | 项目配置 |
| [requirements.txt](doc/requirements.txt) | 生产依赖 |
| [requirements-dev.txt](doc/requirements-dev.txt) | 开发依赖 |

### 🔧 实现详情

| 文档 | 说明 |
|------|------|
| [IMPLEMENTATION_SUMMARY.md](doc/IMPLEMENTATION_SUMMARY.md) | 实现总结 |

---

## 快速开始

1. 查看 [README.md](doc/README.md) 了解项目
2. 阅读 [SETUP_GUIDE_CN.md](doc/SETUP_GUIDE_CN.md) 设置开发环境
3. 查看 [API_DOCUMENTATION_CN.md](doc/API_DOCUMENTATION_CN.md) 了解 API 使用
4. 运行测试: `uv run test`

---

## 项目结构

```
MyRag/
├── doc/                              # 文档目录
│   ├── README.md
│   ├── DEVELOPMENT_CN.md
│   ├── API_DOCUMENTATION_CN.md
│   ├── FAQ_CN.md
│   └── ...
├── app/
│   ├── main.py                       # FastAPI 入口
│   ├── config.py                     # Pydantic Settings
│   ├── api/v1/                       # FastAPI 路由
│   ├── core/
│   │   ├── llm/
│   │   │   ├── factory.py            # LangChain ChatModel 工厂（新增）
│   │   │   └── provider.py           # LLMProvider 门面（基于 LangChain）
│   │   ├── embeddings/
│   │   │   └── bge_m3.py             # BGE-M3 LangChain Embeddings（新增）
│   │   ├── preprocessing/
│   │   │   ├── loaders.py            # LangChain DocumentLoader 路由（新增）
│   │   │   ├── semantic_splitter.py  # LangChain TextSplitter 包装（新增）
│   │   │   ├── parser.py / cleaner.py / chunker.py / pipeline.py
│   │   ├── retrieval/
│   │   │   ├── langchain_retrievers.py  # BaseRetriever 子类（新增）
│   │   │   ├── ensemble.py           # EnsembleRetriever 编排（新增）
│   │   │   ├── hybrid.py / fusion.py / dense.py / sparse.py / graph.py
│   │   ├── chains/                   # LCEL QA Chain（新增）
│   │   │   ├── qa_chain.py
│   │   │   └── prompts.py
│   │   ├── ranking/                  # 业务定制（粗排/精排/置信度/冲突）
│   │   ├── monitoring/
│   │   └── tenant/
│   ├── db/                           # Milvus/ES/Neo4j/Redis 客户端
│   ├── models/                       # SQLAlchemy ORM + Pydantic schemas
│   ├── tasks/                        # Celery 异步任务
│   └── utils/                        # embeddings / logging / security / exceptions
├── tests/                            # 单元 + 集成测试
├── docker/                           # Docker 配置
├── alembic/                          # 数据库迁移
├── dev.py
├── test_system.py
├── pyproject.toml                    # 项目配置 + 依赖
└── requirements*.txt
```

---

## 技术栈

- Python 3.11+
- FastAPI
- **LangChain** (`langchain-core` / `langchain` / `langchain-community` / `langchain-huggingface` / `langchain-openai` / `langchain-ollama` / `langchain-text-splitters`)
- Milvus (向量数据库)
- Elasticsearch (搜索引擎)
- Neo4j (知识图谱)
- Redis (缓存)
- Celery (任务队列)
- Prometheus + Grafana (监控)

---

## 许可证

本项目为专有软件，保留所有权利。

## 支持

如有问题，请查看文档或联系开发团队。