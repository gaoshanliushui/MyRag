# MyRag - 项目文档

## 项目说明

MyRag 是一个分布式多租户混合检索企业级 RAG 系统，采用自设计的密集 + 稀疏 + 知识图谱混合检索架构。

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
├── doc/                    # 文档目录
│   ├── README.md
│   ├── DEVELOPMENT_CN.md
│   ├── API_DOCUMENTATION_CN.md
│   ├── FAQ_CN.md
│   └── ...
├── app/                    # 核心应用代码
├── tests/                  # 测试文件
├── docker/                 # Docker 配置
├── alembic/               # 数据库迁移
├── dev.py                 # 开发脚本
├── test_system.py         # 系统测试
├── requirements.txt       # 生产依赖
├── requirements-dev.txt   # 开发依赖
└── pyproject.toml         # 项目配置
```

---

## 技术栈

- Python 3.11+
- FastAPI
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