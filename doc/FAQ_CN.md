# MyRag 中文常见问题解答（FAQ）

## 1. 安装和配置问题

### Q1: 如何安装 MyRag？

**A:** MyRag 支持两种安装方式：

**推荐方式 - 使用 UV：**
```bash
# 安装 UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
cd F:\Project\Python\AI\rag\MyRag

# 安装依赖
uv sync

# 启动服务
cd docker && docker compose up -d
uv run migrate
uv run dev
```

**传统方式 - 使用 pip：**
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 启动服务
cd docker && docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

### Q2: 环境变量如何配置？

**A:** 复制示例配置并编辑：

```bash
cp docker/.env.example .env
```

关键配置项：
- `LLM_PROVIDER`: LLM 提供者（ollama/vllm/openai/mock）
- `LLM_MODEL`: 模型名称
- `LLM_API_URL`: API 地址
- `EMBEDDING_DEVICE`: 嵌入设备（cuda/cpu/mps）
- `DATABASE_URL`: 数据库连接

### Q3: UV 和 pip 有什么区别？为什么推荐使用 UV？

**A:** UV 是更快的 Python 包管理器：
- **速度**: 比 pip 快 10-100 倍
- **内存**: 更低的内存占用
- **功能**: 内置虚拟环境管理
- **易用**: 统一的命令行界面

详情请查看 [UV_GUIDE.md](UV_GUIDE.md)。

---

## 2. 使用问题

### Q4: 如何创建租户？

**A:** 使用管理员 API 密钥创建：

```bash
curl -X POST "http://localhost:8000/api/v1/admin/tenants" \
  -H "X-API-Key: admin_secret_key_123456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的公司",
    "description": "公司知识库",
    "max_documents": 1000,
    "max_storage_mb": 1024
  }'
```

响应中会包含 `api_key`，请妥善保存。

### Q5: 如何上传文档？

**A:** 使用租户的 API 密钥上传：

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/documents/upload" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {tenant_api_key}" \
  -F "file=@document.pdf"
```

文档会自动异步处理。

### Q6: 如何执行搜索？

**A:** 支持多种检索模式：

```bash
# 混合检索（推荐）
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/search" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {api_key}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MyRag 的功能有哪些？",
    "mode": "hybrid",
    "top_k": 10
  }'

# 仅密集检索
mode: "dense"

# 仅稀疏检索
mode: "sparse"

# 仅图谱检索
mode: "graph"
```

### Q7: 如何使用问答功能？

**A:** 

```bash
curl -X POST "http://localhost:8000/api/v1/{tenant_id}/retrieval/qa" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-API-Key: {api_key}" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "如何配置系统？",
    "top_k": 5,
    "mode": "hybrid"
  }'
```

---

## 3. 性能问题

### Q8: 检索速度慢怎么办？

**A:** 优化建议：

1. **检查索引配置**
   ```bash
   # 检查 Milvus 索引
   docker compose exec milvus-standalone milvus index info
   
   # 优化 HNSW 参数
   efConstruction: 256  # 索引时
   ef: 100              # 查询时
   ```

2. **启用缓存**
   - 查询缓存：`QUERY_CACHE_TTL=300`
   - 向量缓存：`VECTOR_CACHE_TTL=1800`

3. **减少 top_k**
   - 降低检索候选数

4. **使用过滤器**
   ```json
   {
     "filters": {
       "document_ids": ["doc1", "doc2"]
     }
   }
   ```

### Q9: 如何监控系统性能？

**A:** 

1. **访问 Prometheus**
   - http://localhost:9090

2. **查看 Grafana 仪表板**
   - http://localhost:3000 (admin/admin)
   - 导入 `docker/grafana/dashboards/myrag-dashboard.json`

3. **查看 API 指标**
   ```bash
   curl http://localhost:8000/api/v1/admin/metrics
   ```

---

## 4. 故障排除

### Q10: Milvus 无法连接

**A:** 

```bash
# 检查服务状态
docker compose ps milvus-standalone

# 查看日志
docker compose logs -f milvus-standalone

# 重启服务
docker compose restart milvus-standalone
```

### Q11: Elasticsearch 连接失败

**A:**

```bash
# 检查健康状态
curl http://localhost:9200/_cluster/health

# 查看日志
docker compose logs -f elasticsearch

# 可能是内存不足，增加资源
# 编辑 docker/docker-compose.yml
```

### Q12: Redis 连接错误

**A:**

```bash
# 测试连接
redis-cli ping

# 检查服务
docker compose ps redis

# 查看日志
docker compose logs redis
```

### Q13: Neo4j 连接问题

**A:**

```bash
# 访问浏览器界面
# http://localhost:7474 (neo4j/neo4j123)

# 检查服务
docker compose ps neo4j

# 查看日志
docker compose logs -f neo4j
```

### Q14: Celery worker 不工作

**A:**

```bash
# 查看 worker 状态
uv run worker --loglevel=debug

# 检查任务队列
uv run celery -A app.tasks.celery_app inspect active

# 清理死信队列
# 手动清理 Redis 中的队列
```

### Q15: 数据库迁移失败

**A:**

```bash
# 检查数据库连接
uv run python -c "from app.db.session import check_db_connection; import asyncio; print(asyncio.run(check_db_connection()))"

# 查看迁移历史
alembic history

# 回滚迁移
alembic downgrade -1

# 强制迁移
alembic upgrade head --sql
```

---

## 5. 开发问题

### Q16: 如何添加新的文档类型？

**A:** 修改 `app/core/preprocessing/parser.py`：

1. 添加解析方法
2. 在 `DocumentParser.parse()` 中注册
3. 编写测试用例

### Q17: 如何自定义检索策略？

**A:** 

1. 实现新的检索器
2. 修改 `app/core/retrieval/fusion.py` 的权重计算
3. 在 `HybridRetriever` 中集成

### Q18: 如何添加新的 LLM 模型？

**A:** 修改 `app/core/llm/provider.py`：

1. 添加新的 `generate_*` 方法
2. 在 `generate()` 中注册
3. 添加配置选项到 `.env`

### Q19: 如何运行测试？

**A:** 

```bash
# 使用 uv
uv run test           # 运行所有测试
uv run test-cov       # 运行测试 + 覆盖率
uv run lint           # 代码检查
uv run format         # 代码格式化

# 或直接运行
pytest tests/
pytest tests/test_hybrid_retrieval.py -v
```

### Q20: 如何调试代码？

**A:** 

```bash
# 开启 DEBUG 模式
DEBUG=true uv run dev

# 使用 Python 调试器
uv run python -m pdb -m uvicorn app.main:app --reload

# 日志级别
LOG_LEVEL=debug uv run dev
```

---

## 6. 部署问题

### Q21: 如何部署到生产环境？

**A:** 

1. **准备配置**
   - 复制 `.env.example` 到 `.env.prod`
   - 设置安全的密钥
   - 配置生产数据库

2. **使用生产镜像**
   ```bash
   docker compose -f docker/docker-compose.prod.yml up -d
   ```

3. **配置反向代理**
   - Nginx / Traefik
   - HTTPS 证书

4. **监控和告警**
   - 配置 Prometheus 告警规则
   - 设置日志收集

### Q22: 如何备份数据？

**A:** 

1. **数据库备份**
   ```bash
   docker compose exec postgres pg_dump -U myrag myrag > backup.sql
   ```

2. **Milvus 备份**
   ```bash
   # 使用 Milvus Backup 工具
   ```

3. **Elasticsearch 备份**
   ```bash
   curl -X PUT "localhost:9200/_snapshot/my_backup"
   ```

4. **文件备份**
   ```bash
   tar -czf uploads_backup.tar.gz ./uploads
   ```

### Q23: 如何扩展系统？

**A:** 

1. **水平扩展**
   ```yaml
   # docker-compose.yml
   services:
     api:
       deploy:
         replicas: 3
   ```

2. **垂直扩展**
   - 增加 Milvus 节点
   - 增加 Celery worker
   - 升级 Redis 内存

3. **数据库优化**
   - 读写分离
   - 分库分表

---

## 7. 安全问题

### Q24: 如何保护 API 密钥？

**A:** 

1. **环境变量**
   - 不要硬编码在代码中
   - 使用环境变量管理

2. **密钥轮换**
   ```bash
   curl -X POST "/api/v1/admin/tenants/{id}/regenerate-api-key"
   ```

3. **访问控制**
   - 最小权限原则
   - 定期审计

### Q25: 数据如何加密？

**A:** 

1. **传输加密**
   - 使用 HTTPS
   - 配置 SSL/TLS 证书

2. **存储加密**
   - 数据库透明加密
   - 文件系统加密

3. **敏感数据**
   - API 密钥哈希存储
   - 使用加密密钥管理

---

## 8. 其他问题

### Q26: 支持哪些文档格式？

**A:** 当前支持：
- PDF（通过 PyMuPDF）
- DOCX（通过 python-docx）
- TXT（纯文本）
- HTML（通过 BeautifulSoup）
- MD（Markdown）

### Q27: 支持哪些语言？

**A:** 
- **检索**: 中英文混合支持
- **嵌入**: 中英文通用模型
- **界面**: 支持中文/英文

### Q28: 如何升级版本？

**A:** 

```bash
# 1. 备份数据
# 2. 拉取新代码
git pull

# 3. 运行迁移
uv run migrate

# 4. 重启服务
docker compose restart
uv run dev
```

### Q29: 如何获取技术支持？

**A:** 
- 查看文档：[README.md](README.md)、[DEVELOPMENT_CN.md](DEVELOPMENT_CN.md)
- GitHub Issues
- 联系开发团队

### Q30: 如何贡献代码？

**A:** 
- 阅读 [CONTRIBUTING.md](CONTRIBUTING.md)
- Fork 仓库
- 提交 Pull Request
- 通过测试

---

## 更多帮助

- 📚 [开发文档](DEVELOPMENT_CN.md)
- 📖 [API 文档](API_DOCUMENTATION_CN.md)
- 🔧 [UV 使用指南](UV_GUIDE.md)
- 💬 联系支持团队
