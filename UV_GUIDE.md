# UV 包管理工具使用指南

本项目使用 [uv](https://github.com/astral-sh/uv) 作为 Python 包管理器。uv 是一个极速的 Python 包管理器，由 Astral 开发（也是 Ruff 的开发者）。

## 为什么使用 UV？

| 特性 | UV | Pip |
|------|-----|-----|
| 安装速度 | ⚡ 极快（10-100x 提速） | 🐌 慢 |
| 内存占用 | 低 | 高 |
| 虚拟环境管理 | 内置 | 需要 virtualenv |
| 依赖解析 | 快速且准确 | 有时较慢 |
| 项目管理 | 内置 | 有限 |

## 快速开始

### 1. 安装 UV

**使用官方安装脚本（推荐）:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip 安装
pip install uv
```

**验证安装:**
```bash
uv --version
```

### 2. 设置项目环境

**创建虚拟环境并安装依赖:**
```bash
# 创建虚拟环境并安装所有依赖
uv sync

# 或者只安装生产依赖
uv sync --no-dev

# 安装开发依赖
uv sync --dev
```

### 3. 常用命令

#### 依赖管理
```bash
# 添加依赖
uv add fastapi uvicorn

# 添加开发依赖
uv add --dev pytest ruff mypy

# 移除依赖
uv remove package-name

# 更新依赖
uv lock --upgrade

# 更新特定依赖
uv lock --upgrade package-name
```

#### 运行命令
```bash
# 运行开发服务器（使用 pyproject.toml 中定义的脚本）
uv run dev

# 运行测试
uv run test

# 运行任意命令
uv run pytest tests/
uv run uvicorn app.main:app --reload

# 在虚拟环境中启动 Python
uv run python
```

#### 环境管理
```bash
# 查看环境信息
uv venv --version

# 创建虚拟环境
uv venv

# 激活虚拟环境
# macOS/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

## 项目预定义脚本

在 `pyproject.toml` 中已配置以下脚本:

| 命令 | 描述 |
|------|------|
| `uv run dev` | 启动开发服务器（带热重载） |
| `uv run server` | 启动生产服务器 |
| `uv run worker` | 启动 Celery worker |
| `uv run beat` | 启动 Celery beat |
| `uv run test` | 运行所有测试 |
| `uv run test-cov` | 运行测试并生成覆盖率报告 |
| `uv run lint` | 运行代码检查 |
| `uv run format` | 格式化代码 |
| `uv run typecheck` | 运行类型检查 |
| `uv run migrate` | 运行数据库迁移 |
| `uv run migrate-revision` | 创建新的迁移版本 |
| `uv run clean-all` | 清理缓存和临时文件 |

## 工作流示例

### 开发新特性
```bash
# 1. 同步依赖
uv sync

# 2. 创建新分支
git checkout -b feature/new-feature

# 3. 添加所需依赖
uv add new-package

# 4. 开发并运行测试
uv run test

# 5. 代码检查
uv run lint
uv run format

# 6. 提交
git add .
git commit -m "feat: add new feature"
```

### 添加新依赖
```bash
# 添加生产依赖
uv add some-package

# 添加开发依赖
uv add --dev some-dev-package

# 添加可选依赖
uv add --optional some-optional-package
```

### 更新依赖
```bash
# 更新所有依赖
uv lock --upgrade

# 更新特定依赖
uv lock --upgrade package-name

# 查看可更新的依赖
uv pip list --outdated
```

### 运行数据库迁移
```bash
# 应用所有迁移
uv run migrate

# 创建新迁移
uv run migrate-revision "add new column"

# 回滚一个迁移
uv run migrate-downgrade
```

## 故障排除

### 常见问题

**1. 依赖冲突**
```bash
# 清理缓存并重试
uv cache clean
uv sync
```

**2. 虚拟环境问题**
```bash
# 删除虚拟环境并重新创建
rm -rf .venv
uv sync
```

**3. Python 版本不匹配**
```bash
# 安装指定 Python 版本
uv python install 3.11

# 查看可用 Python 版本
uv python list
```

### 清理命令
```bash
# 清理 uv 缓存
uv cache clean

# 清理所有构建产物
uv run clean-all
```

## 高级用法

### 多 Python 版本支持
```bash
# 安装多个 Python 版本
uv python install 3.10
uv python install 3.11
uv python install 3.12

# 为项目指定 Python 版本
uv python pin 3.11
```

### 工作空间支持（Monorepo）
```bash
# 如果有多个子项目
uv sync --all-packages

# 只同步特定包
uv sync --package app
```

### 锁定文件管理
```bash
# 查看锁定文件状态
uv lock --check

# 重新生成锁定文件
uv lock --refresh
```

## 从 Pip 迁移到 UV

### 迁移步骤

1. **备份当前环境**
```bash
pip freeze > requirements-backup.txt
```

2. **安装 UV**
```bash
pip install uv
```

3. **删除旧的虚拟环境**
```bash
rm -rf .venv
```

4. **使用 UV 同步依赖**
```bash
uv sync
```

5. **验证**
```bash
uv run pytest tests/
```

## 最佳实践

1. ✅ 始终使用 `uv run` 执行命令，确保使用正确的虚拟环境
2. ✅ 提交 `uv.lock` 文件到版本控制，确保依赖一致性
3. ✅ 使用 `uv add` 而不是直接编辑 `pyproject.toml`
4. ✅ 定期运行 `uv lock --upgrade` 更新依赖
5. ✅ 使用预定义脚本简化常用操作

## 参考资源

- [UV 官方文档](https://docs.astral.sh/uv/)
- [UV GitHub 仓库](https://github.com/astral-sh/uv)
- [Pyproject.toml 规范](https://peps.python.org/pep-0621/)

---

**快速参考卡片**

```bash
# 安装依赖
uv sync

# 添加包
uv add <package>

# 运行命令
uv run <command>

# 运行测试
uv run test

# 格式化代码
uv run format

# 数据库迁移
uv run migrate
```