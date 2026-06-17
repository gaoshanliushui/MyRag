# MyRag 中文开发文档索引

本项目提供了丰富的中文文档，帮助开发者快速上手和深入理解系统。

## 📖 文档导航

### 1. 快速开始

- **[README.md](README.md)** - 项目概述、快速开始、安装指南
- **[FAQ_CN.md](FAQ_CN.md)** - 常见问题解答，快速解决常见问题

### 2. 开发指南

- **[DEVELOPMENT_CN.md](DEVELOPMENT_CN.md)** - 完整的开发指南
  - 项目结构说明
  - 开发环境搭建
  - 代码规范
  - 测试策略
  - 部署建议

### 3. API 文档

- **[API_DOCUMENTATION_CN.md](API_DOCUMENTATION_CN.md)** - 详细的 API 参考
  - 管理端点（租户管理、系统监控）
  - 文档端点（上传、查询、删除）
  - 检索端点（搜索、问答）
  - 错误处理
  - 代码示例（Python、JavaScript）

### 4. 依赖管理

- **[UV_GUIDE.md](UV_GUIDE.md)** - UV 包管理器使用指南
  - UV 安装和配置
  - 常用命令
  - 项目脚本
  - 从 pip 迁移到 UV

### 5. 架构设计

- **[CLAUDE.md](CLAUDE.md)** - 项目架构和设计决策
  - 适应性语义预处理
  - 三路混合检索
  - 两级分阶段重排序
  - 分布式多租户隔离

### 6. 测试指南

- **[tests/](tests/)** - 测试代码示例
  - 单元测试
  - 集成测试
  - 如何编写测试

### 7. 数据库迁移

- **[alembic/versions/](alembic/versions/)** - 数据库迁移历史
  - 001_initial: 初始迁移
  - 002_add_api_key_hash: API 密钥哈希

---

## 🚀 快速查找

### 我想...

#### **安装和配置**
- [安装项目](README.md#快速开始)
- [配置环境变量](README.md#4-配置环境变量)
- [启动服务](README.md#5-运行数据库迁移)

#### **使用 API**
- [创建租户](API_DOCUMENTATION_CN.md#14-创建租户)
- [上传文档](API_DOCUMENTATION_CN.md#21-上传文档)
- [执行搜索](API_DOCUMENTATION_CN.md#31-混合搜索)
- [问答功能](API_DOCUMENTATION_CN.md#32-问答)

#### **开发新功能**
- [项目结构](DEVELOPMENT_CN.md#项目结构)
- [代码规范](DEVELOPMENT_CN.md#代码风格规范)
- [添加新功能流程](DEVELOPMENT_CN.md#添加新功能流程)

#### **运行测试**
- [运行测试](DEVELOPMENT_CN.md#运行测试)
- [编写测试](DEVELOPMENT_CN.md#测试策略)
- [测试示例](tests/test_core.py)

#### **性能优化**
- [优化检索速度](FAQ_CN.md#q8-检索速度慢怎么办)
- [监控性能](FAQ_CN.md#q9-如何监控系统性能)
- [性能目标](README.md#性能目标)

#### **故障排除**
- [Milvus 连接问题](FAQ_CN.md#q10-milvus-无法连接)
- [Elasticsearch 连接失败](FAQ_CN.md#q11-elasticsearch-连接失败)
- [数据库迁移失败](FAQ_CN.md#q15-数据库迁移失败)

#### **依赖管理**
- [使用 UV](UV_GUIDE.md#快速开始)
- [添加新依赖](UV_GUIDE.md#依赖管理)
- [运行命令](UV_GUIDE.md#运行命令)

---

## 📁 核心目录结构

```
F:\Project\Python\AI\rag\MyRag/
├── 📖 文档
│   ├── README.md                      # 项目主文档（中文）
│   ├── DEVELOPMENT_CN.md              # 开发指南（中文）
│   ├── API_DOCUMENTATION_CN.md        # API 文档（中文）
│   ├── FAQ_CN.md                      # 常见问题（中文）
│   ├── UV_GUIDE.md                    # UV 使用指南
│   ├── CLAUDE.md                      # 架构设计文档
│   └── IMPLEMENTATION_SUMMARY.md       # 实现总结
│
├── 🔧 核心代码
│   └── app/
│       ├── api/v1/                    # API 端点
│       ├── core/                      # 核心业务逻辑
│       │   ├── llm/                   # LLM 集成
│       │   ├── preprocessing/         # 预处理
│       │   ├── retrieval/             # 检索
│       │   ├── ranking/               # 排序
│       │   ├── tenant/                # 租户管理
│       │   └── monitoring/            # 监控
│       ├── db/                        # 数据库客户端
│       ├── models/                    # 数据模型
│       ├── tasks/                     # Celery 任务
│       └── utils/                     # 工具类
│
├── 🧪 测试
│   └── tests/
│       ├── test_core.py
│       ├── test_admin.py
│       ├── test_preprocessing.py
│       ├── test_hybrid_retrieval.py
│       ├── test_llm_provider.py
│       └── test_integration.py
│
├── 🐳 Docker 配置
│   └── docker/
│       ├── docker-compose.yml         # 服务编排
│       ├── prometheus.yml             # 监控配置
│       └── grafana/                   # 仪表板
│
├── 📦 依赖管理
│   ├── requirements.txt               # 生产依赖
│   ├── requirements-dev.txt           # 开发依赖
│   ├── pyproject.toml                 # 项目配置（支持 uv）
│   └── uv.lock                        # UV 锁定文件
│
└── 🗄️  数据库
    └── alembic/
        └── versions/
            ├── 001_initial.py
            └── 002_add_api_key_hash.py
```

---

## 🎯 推荐阅读顺序

### 新手开发者

1. 📖 [README.md](README.md) - 了解项目整体
2. 📖 [DEVELOPMENT_CN.md](DEVELOPMENT_CN.md) - 学习开发环境
3. 📖 [FAQ_CN.md](FAQ_CN.md) - 查看常见问题
4. 🧪 运行测试：`uv run test`
5. 🔧 开始开发第一个功能

### 有经验的开发者

1. 📖 [CLAUDE.md](CLAUDE.md) - 深入理解架构设计
2. 📖 [API_DOCUMENTATION_CN.md](API_DOCUMENTATION_CN.md) - API 参考
3. 🔍 浏览代码：`app/core/retrieval/` - 核心检索逻辑
4. 🧪 运行特定测试：`uv run pytest tests/test_hybrid_retrieval.py -v`
5. 🚀 开始优化或扩展功能

### 系统管理员

1. 📖 [README.md](README.md#部署) - 部署指南
2. 📖 [FAQ_CN.md](FAQ_CN.md#部署问题) - 部署故障排除
3. 🐳 查看 Docker 配置：`docker/docker-compose.yml`
4. 📊 配置监控：Prometheus + Grafana
5. 🔐 配置安全：环境变量、密钥管理

---

## 📚 术语表

| 英文 | 中文 | 说明 |
|------|------|------|
| Tenant | 租户 | 数据隔离的基本单位 |
| Chunk | 块 | 文档的分块单元 |
| Embedding | 嵌入 | 文本的向量表示 |
| Dense Retrieval | 密集检索 | 基于向量相似度的检索 |
| Sparse Retrieval | 稀疏检索 | 基于关键词的检索 |
| Graph Retrieval | 知识图谱检索 | 基于图谱的多跳检索 |
| Reranking | 重排序 | 对候选结果进行精细排序 |
| Fusion | 融合 | 多路检索结果的合并 |
| Multi-tenant | 多租户 | 支持多个独立租户 |

---

## 📞 获取帮助

- 📖 阅读文档
- 🐛 提交 Issue
- 💬 联系开发团队
- 🤝 参与开源贡献

---

## 📝 文档更新

本文档最后更新于：2025-06-17

如有任何建议或发现错误，请提交 Issue 或 Pull Request。
