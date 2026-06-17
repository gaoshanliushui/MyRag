# MyRag Docker Compose 配置说明

## 项目概述

本 Docker Compose 配置文件定义了 MyRag 系统运行所需的所有服务。采用分布式架构，支持水平扩展和高可用性。

## 服务列表

### 1. PostgreSQL (postgresql/pgvector:pg16)

**用途**: 主数据库，存储租户信息、文档元数据和分块数据

**配置**:
- 端口: 5432 (映射到主机 5432)
- 卷: `postgres_data` - 持久化数据
- 环境变量:
  - `POSTGRES_DB`: myrag
  - `POSTGRES_USER`: myrag
  - `POSTGRES_PASSWORD`: myrag
- 健康检查: 使用 `pg_isready` 检查连接状态

**资源限制** (生产环境建议):
```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 512M
```

---

### 2. Etcd (quay.io/coreos/etcd:v3.5.5)

**用途**: Milvus 的元数据存储，协调分布式集群

**配置**:
- 端口: 2379 (内部)
- 卷: `etcd_data` - 持久化数据
- 环境变量:
  - `ETCD_AUTO_COMPACTION_MODE`: revision
  - `ETCD_AUTO_COMPACTION_RETENTION`: 1000
  - `ETCD_QUOTA_BACKEND_BYTES`: 4294967296 (4GB)
- 命令: 运行单节点 etcd

**注意**: 生产环境应使用 3 节点 etcd 集群

---

### 3. MinIO (minio/minio:RELEASE.2023-03-20T20-16-18Z)

**用途**: 对象存储，存储 Milvus 的二进制数据和快照

**配置**:
- 端口: 9000 (内部)
- 卷: `minio_data` - 持久化数据
- 环境变量:
  - `MINIO_ACCESS_KEY`: minioadmin
  - `MINIO_SECRET_KEY`: minioadmin
- 命令: `minio server /minio_data`
- 健康检查: 通过 HTTP 检查 `/minio/health/live`

**管理界面**: 通过 Milvus 或直接访问 MinIO Web UI

---

### 4. Milvus Standalone (milvusdb/milvus:v2.5.0)

**用途**: 向量数据库，存储和检索文档嵌入向量

**配置**:
- 端口: 
  - 19530: gRPC (客户端连接)
  - 9091: Prometheus 指标
- 卷: `milvus_data` - 持久化数据
- 依赖: `etcd`, `minio`
- 环境变量:
  - `ETCD_ENDPOINTS`: etcd:2379
  - `MINIO_ADDRESS`: minio:9000
- 命令: `milvus run standalone`

**索引类型**: HNSW (Hierarchical Navigable Small World)
- `efConstruction`: 256 (索引构建)
- `ef`: 100 (搜索)

**性能调优** (生产环境):
```yaml
environment:
  - MILVUS_CACHE_SIZE=4GB
  - MILVUS_INSERT_BUFFER_SIZE=1GB
  - MILVUS_TIME_TICK_SYNC_PERIOD=200ms
```

---

### 5. Elasticsearch (docker.elastic.co/elasticsearch/elasticsearch:8.17.0)

**用途**: 搜索引擎，提供 BM25 稀疏检索能力

**配置**:
- 端口:
  - 9200: HTTP API
  - 9300: 节点间通信
- 卷: `es_data` - 持久化数据
- 环境变量:
  - `discovery.type`: single-node
  - `xpack.security.enabled`: false (开发环境，生产环境应启用)
  - `ES_JAVA_OPTS`: "-Xms1g -Xmx1g" (JVM 堆内存)
- 健康检查: HTTP GET `/cluster/health`

**分片策略**:
- 单租户: 1 主分片 + 0 副本 (开发)
- 多租户: 3 主分片 + 1 副本 (生产)

**IK Analyzer**: 支持中文分词
```json
"analyzer": {
  "chinese_analyzer": {
    "type": "ik_max_word"
  }
}
```

---

### 6. Neo4j (neo4j:5.28.0)

**用途**: 知识图谱数据库，存储实体关系和多跳检索

**配置**:
- 端口:
  - 7474: HTTP (浏览器界面)
  - 7687: Bolt (客户端连接)
- 卷: 
  - `neo4j_data`: 数据
  - `neo4j_logs`: 日志
  - `neo4j_import`: 导入数据
  - `neo4j_plugins`: 插件
- 环境变量:
  - `NEO4J_AUTH`: neo4j/neo4j123
  - `NEO4J_dbms_memory_pagecache_size`: 1G
  - `NEO4J_dbms_memory_heap_initial_size`: 512m
  - `NEO4J_dbms_memory_heap_max_size`: 512m
- 健康检查: HTTP GET `/`

**浏览器访问**: http://localhost:7474 (账号: neo4j, 密码: neo4j123)

**性能调优** (生产环境):
```yaml
environment:
  - NEO4J_dbms_memory_pagecache_size=4G
  - NEO4J_dbms_memory_heap_initial_size=2G
  - NEO4J_dbms_memory_heap_max_size=2G
  - NEO4J_dbms_tx_log_rotation_size=500M
```

---

### 7. Redis (redis:7.4-alpine)

**用途**: 缓存层，提供查询缓存、向量缓存、会话管理

**配置**:
- 端口: 6379
- 卷: `redis_data` - 持久化数据
- 命令: `redis-server --appendonly yes` (AOF 持久化)
- 健康检查: `redis-cli ping`

**数据库分配**:
- DB 0: 查询缓存
- DB 1: 会话缓存
- DB 2: Celery 任务队列

**性能优化**:
```yaml
command:
  - redis-server
  - --appendonly yes
  - --appendfsync everysec
  - --maxmemory 512mb
  - --maxmemory-policy allkeys-lru
```

---

### 8. Redis Insight (redis/redisinsight:latest)

**用途**: Redis 可视化管理界面

**配置**:
- 端口: 8001 (映射到主机)
- 卷: `redis_insight_data` - 配置持久化
- 依赖: `redis`
- 访问: http://localhost:8001

**功能**:
- 查看所有键值
- 执行 Redis 命令
- 监控内存使用
- 分析慢查询

---

### 9. Prometheus (prom/prometheus:v2.55.0)

**用途**: 监控系统，收集和存储时间序列指标

**配置**:
- 端口: 9090
- 卷: `prometheus_data` - 指标数据持久化
- 配置文件: `./docker/prometheus.yml` (挂载)
- 命令:
  - `--config.file=/etc/prometheus/prometheus.yml`
  - `--storage.tsdb.path=/prometheus`
  - `--web.enable-lifecycle` (支持热重载)

**监控目标**:
- MyRag API 应用 (`http://host.docker.internal:8000/metrics`)
- Prometheus 自身
- (可选) PostgreSQL、Elasticsearch、Redis 的导出器

**配置示例** (prometheus.yml):
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'myrag'
    static_configs:
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

---

### 10. Grafana (grafana/grafana:11.3.0)

**用途**: 可视化仪表板，展示监控数据

**配置**:
- 端口: 3000 (映射到主机)
- 卷: `grafana_data` - 仪表板和配置持久化
- 环境变量:
  - `GF_SECURITY_ADMIN_USER`: admin
  - `GF_SECURITY_ADMIN_PASSWORD`: admin
  - `GF_USERS_ALLOW_SIGN_UP`: false (禁用注册)
- 依赖: `prometheus`

**访问**: http://localhost:3000 (账号: admin, 密码: admin)

**预配置**:
- 数据源: Prometheus
- 仪表板: 从 `docker/grafana/dashboards/` 加载

**仪表板位置**:
```
docker/grafana/
├── provisioning/
│   ├── datasources/
│   │   └── prometheus.yml  # 数据源配置
│   └── dashboards/
│       └── default.yml     # 仪表板配置
└── dashboards/
    └── myrag-dashboard.json # MyRag 仪表板
```

---

## 网络配置

**自定义网络**: `myrag-network`

所有服务都在同一个 Docker 网络中，可以通过服务名互相访问：
- `postgres` → PostgreSQL
- `milvus-standalone` → Milvus
- `elasticsearch` → Elasticsearch
- `neo4j` → Neo4j
- `redis` → Redis
- `prometheus` → Prometheus
- `grafana` → Grafana

**网络模式**: `bridge` (桥接模式)

---

## 卷配置

所有数据卷都是命名卷，确保持久化存储:

| 卷名 | 用途 | 备份建议 |
|------|------|----------|
| `postgres_data` | PostgreSQL 数据 | 定期备份 |
| `etcd_data` | Etcd 元数据 | 定期备份 |
| `minio_data` | MinIO 对象存储 | 定期备份 |
| `milvus_data` | Milvus 向量数据 | 定期备份 + 快照 |
| `es_data` | Elasticsearch 索引 | 定期快照 |
| `neo4j_data` | Neo4j 图数据 | 定期备份 |
| `neo4j_logs` | Neo4j 日志 | 日志轮转 |
| `neo4j_import` | Neo4j 导入数据 | - |
| `neo4j_plugins` | Neo4j 插件 | - |
| `redis_data` | Redis 持久化 | 定期备份 |
| `redis_insight_data` | Redis Insight 配置 | - |
| `prometheus_data` | Prometheus 指标 | 根据保留策略 |
| `grafana_data` | Grafana 配置 | 定期备份 |

---

## 生产环境优化建议

### 1. 资源限制

为每个服务添加资源限制:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 512M
```

### 2. 高可用性

- **PostgreSQL**: 使用 Patroni + etcd 集群
- **Milvus**: 使用集群模式（standalone → cluster）
- **Elasticsearch**: 3 节点集群
- **Neo4j**: 使用因果集群
- **Redis**: 使用 Redis Sentinel 或 Redis Cluster
- **应用**: 多副本 + 负载均衡

### 3. 安全配置

- 启用 TLS/SSL 证书
- 配置防火墙规则
- 使用 secrets 管理敏感信息
- 启用身份验证和授权

### 4. 备份策略

```bash
# 定期备份脚本
#!/bin/bash
docker compose exec postgres pg_dump -U myrag myrag > backup_$(date +%Y%m%d).sql
docker compose exec redis redis-cli BGSAVE
# ... 其他服务的备份
```

### 5. 监控告警

在 Prometheus 中配置告警规则:

```yaml
groups:
  - name: myrag_alerts
    rules:
      - alert: HighLatency
        expr: myrag_request_latency_seconds > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "高延迟检测"
          description: "请求延迟超过 500ms"
      
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "服务不可用"
```

---

## 常用命令

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 重启特定服务
docker compose restart postgres

# 查看日志
docker compose logs -f milvus-standalone

# 进入容器
docker compose exec postgres psql -U myrag myrag

# 查看服务状态
docker compose ps

# 扩缩容
docker compose up -d --scale api=3

# 清理未使用的卷
docker volume prune

# 查看资源使用
docker stats
```

---

## 故障排除

### 服务启动失败

```bash
# 1. 检查日志
docker compose logs <service_name>

# 2. 检查资源限制
docker stats

# 3. 增加内存限制
# 修改 docker-compose.yml 中的 memory 限制

# 4. 检查端口冲突
netstat -tuln | grep <port>
```

### 网络连接问题

```bash
# 测试服务间连接
docker compose exec api curl http://postgres:5432

# 查看网络
docker network inspect myrag_myrag-network
```

### 数据持久化问题

```bash
# 检查卷
docker volume ls

# 检查卷使用情况
docker volume inspect myrag_postgres_data

# 备份卷
docker run --rm -v myrag_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz /data
```

---

## 参考资源

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Milvus 部署指南](https://milvus.io/docs/install_standalone-docker.md)
- [Elasticsearch Docker](https://www.elastic.co/guide/en/elasticsearch/reference/current/docker.html)
- [Neo4j Docker](https://neo4j.com/docs/operations-manual/current/docker/)
- [Prometheus Docker](https://prometheus.io/docs/prometheus/latest/installation/#docker)
- [Grafana Docker](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/)
