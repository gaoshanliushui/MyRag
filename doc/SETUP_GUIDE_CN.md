# MyRag 中文开发环境设置指南

本指南详细说明如何设置 MyRag 的本地开发环境。

## 系统要求

- **操作系统**: Windows 11、macOS、Linux
- **Python 版本**: 3.11 或更高
- **内存**: 16GB 或更高（推荐 32GB 用于开发和测试）
- **磁盘空间**: 50GB 以上（用于 Docker 镜像和数据）
- **Docker**: Docker Desktop 4.0+ 或 Docker Engine 20.10+

## 安装步骤

### 1. 安装 Python 3.11+

**Windows:**
```bash
# 使用官方安装程序
# 下载地址: https://www.python.org/downloads/release/python-31110/

# 或使用 Chocolatey
choco install python311

# 或使用 Scoop
scoop install python311
```

**macOS:**
```bash
# 使用 Homebrew
brew install python@3.11

# 验证
python3.11 --version
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev

# 验证
python3.11 --version
```

### 2. 安装 UV（推荐）

UV 是一个极速的 Python 包管理器。

**快速安装（推荐）:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# 验证
uv --version
```

**使用 pip 安装:**
```bash
pip install uv
```

### 3. 安装 Docker

**Windows:**
- 下载 Docker Desktop: https://www.docker.com/products/docker-desktop/
- 安装后启动 Docker Desktop
- 确保 WSL2 已启用

**macOS:**
```bash
# 使用 Homebrew
brew install --cask docker

# 或下载安装包
# https://www.docker.com/products/docker-desktop/
```

**Linux:**
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker
```

**验证 Docker:**
```bash
docker --version
docker compose version
docker ps
```

### 4. 克隆项目

```bash
cd F:\Project\Python\AI\rag
git clone https://github.com/myrag/myrag.git MyRag
cd MyRag
```

### 5. 配置 Python 版本

```bash
# 创建 .python-version 文件
echo "3.11" > .python-version

# 或使用 pyenv（如果安装了）
pyenv local 3.11.10
```

### 6. 创建虚拟环境并安装依赖

**方式一：使用 UV（推荐）:**
```bash
# 安装所有依赖（生产 + 开发）
uv sync

# 或只安装生产依赖
uv sync --no-dev

# 或只安装开发依赖
uv sync --dev-only
```

**方式二：使用 pip:**
```bash
# 创建虚拟环境
python3.11 -m venv .venv

# 激活虚拟环境
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 7. 配置环境变量

```bash
# 复制示例配置
cp docker/.env.example .env

# 编辑 .env 文件
# Windows (PowerShell)
notepad .env

# macOS/Linux
vi .env
```

**关键配置项:**

```bash
# 应用配置
DEBUG=true
SECRET_KEY=your-super-secret-key-change-this

# 数据库
DATABASE_URL=postgresql+asyncpg://myrag:myrag@localhost:5432/myrag

# LLM
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:14b
LLM_API_URL=http://localhost:11434

# 嵌入
EMBEDDING_DEVICE=cuda  # 或 cpu（如果没有 GPU）

# 缓存
REDIS_URL=redis://localhost:6379/0

# 监控
METRICS_ENABLED=true
```

### 8. 启动 Docker 服务

```bash
# 进入 docker 目录
cd docker

# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 如果首次启动，等待服务完全启动（约 2-5 分钟）
```

**服务列表:**
- `postgres`: PostgreSQL + pgvector（端口 5432）
- `milvus-standalone`: Milvus 向量数据库（端口 19530）
- `elasticsearch`: Elasticsearch 检索引擎（端口 9200）
- `neo4j`: Neo4j 知识图谱（端口 7474、7687）
- `redis`: Redis 缓存（端口 6379）
- `prometheus`: Prometheus 监控（端口 9090）
- `grafana`: Grafana 仪表板（端口 3000）

### 9. 初始化数据库

```bash
# 使用 UV
uv run migrate

# 或使用 alembic
alembic upgrade head
```

**预期输出:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial, Initial migration
INFO  [alembic.runtime.migration] Running upgrade 001_initial -> 002_add_api_key_hash, Add api_key_hash column to tenants table
```

### 10. 启动应用

**方式一：使用 UV（推荐）:**
```bash
# 启动开发服务器
uv run dev

# 启动 Celery worker（新终端）
uv run worker

# 启动 Celery beat（新终端）
uv run beat
```

**方式二：手动启动:**
```bash
# 终端 1: API 服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2: Celery worker
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

# 终端 3: Celery beat（可选）
celery -A app.tasks.celery_app beat --loglevel=info
```

### 11. 验证安装

```bash
# 1. 检查健康状态
curl http://localhost:8000/health

# 预期输出:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "services": {
#     "database": "ok",
#     "redis": "ok",
#     "milvus": "ok",
#     "elasticsearch": "ok",
#     "neo4j": "ok"
#   }
# }

# 2. 访问 API 文档
# 浏览器打开: http://localhost:8000/docs

# 3. 检查 Prometheus
# http://localhost:9090

# 4. 检查 Grafana
# http://localhost:3000 (admin/admin)
```

---

## 开发工作流

### 日常开发

```bash
# 1. 启动服务
docker compose up -d

# 2. 激活虚拟环境（如果使用 pip）
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate     # Windows

# 3. 运行应用
uv run dev

# 4. 运行测试
uv run test

# 5. 代码检查
uv run lint
uv run format
```

### 运行测试

```bash
# 运行所有测试
uv run test

# 运行特定测试文件
uv run pytest tests/test_hybrid_retrieval.py -v

# 运行带覆盖率的测试
uv run test-cov

# 查看覆盖率报告
open htmlcov/index.html  # macOS
# 或
start htmlcov/index.html  # Windows
```

### 代码检查和格式化

```bash
# 代码检查
uv run lint

# 自动修复问题
uv run lint --fix

# 格式化代码
uv run format

# 类型检查
uv run typecheck
```

### 数据库操作

```bash
# 创建新迁移
uv run migrate-revision "添加新字段"

# 应用迁移
uv run migrate

# 回滚迁移
uv run migrate-downgrade

# 查看迁移历史
alembic history
```

### 清理

```bash
# 清理缓存
uv run clean-all

# 清理 Docker
docker compose down
docker system prune -a

# 重建虚拟环境
rm -rf .venv
uv sync
```

---

## 常见问题

### Python 版本问题

**问题**: `python: command not found` 或版本不对

**解决**:
```bash
# 检查 Python 版本
python --version
python3 --version

# 创建符号链接（Linux/macOS）
sudo ln -s /usr/bin/python3.11 /usr/bin/python

# 或使用 pyenv 管理版本
pyenv install 3.11.10
pyenv global 3.11.10
```

### Docker 服务启动失败

**问题**: 某些服务无法启动

**解决**:
```bash
# 查看具体服务的日志
docker compose logs postgres
docker compose logs milvus-standalone

# 增加资源限制（docker-compose.yml）
# 内存不足可能导致服务启动失败

# 重启服务
docker compose restart

# 完全重建
docker compose down
docker compose up -d --build
```

### 依赖安装失败

**问题**: `uv sync` 或 `pip install` 失败

**解决**:
```bash
# 清理缓存
uv cache clean
pip cache purge

# 使用国内镜像（中国用户）
# 在 .env 中添加:
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 或直接使用
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 端口冲突

**问题**: 某些端口已被占用

**解决**:
```bash
# 查看端口占用
# Windows
netstat -ano | findstr :5432

# macOS/Linux
lsof -i :5432

# 修改 docker-compose.yml 中的端口映射
# 或停止占用端口的进程
```

---

## IDE 配置

### VS Code

1. 安装扩展:
   - Python
   - Pylance
   - Ruff
   - Docker
   - GitLens

2. 配置 `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "editor.formatOnSave": true,
  "python.analysis.typeCheckingMode": "basic"
}
```

### PyCharm

1. 打开项目
2. 设置 Python 解释器为 `.venv/bin/python`
3. 启用 Ruff 检查
4. 配置 pytest 作为测试运行器

---

## 下一步

- 📖 阅读 [DEVELOPMENT_CN.md](DEVELOPMENT_CN.md) 了解开发规范
- 📖 查看 [API_DOCUMENTATION_CN.md](API_DOCUMENTATION_CN.md) 了解 API 使用
- 🧪 运行测试：`uv run test`
- 🔍 浏览代码，理解架构

---

如有问题，请查看 [FAQ_CN.md](FAQ_CN.md) 或联系开发团队。