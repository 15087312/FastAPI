# wrk 性能测试报告

**测试日期**: 2026-03-14  
**测试工具**: wrk  
**测试目标**: 验证 Redis MGET 批量读取优化效果

---

## 📊 测试概要

### 测试环境
- **测试接口**: `GET /api/v1/inventory/stock/980?warehouse_id=WH001`
- **测试时长**: 30 秒
- **并发配置**: 2 threads, 10 connections
- **Docker 配置**:
  - FastAPI: 8 Gunicorn workers (uvicorn.workers.UvicornWorker)
  - Celery: 8 concurrency workers
  - Redis: maxclients 10000
  - PostgreSQL: max_connections 500

### 测试命令
```bash
wrk -t2 -c10 -d30s http://127.0.0.1:8000/api/v1/inventory/stock/980?warehouse_id=WH001
```

---

## 📈 测试结果

### 优化前数据（Redis MGET 优化前）

**原始输出**：
```
Running 30s test @ http://127.0.0.1:8000/api/v1/inventory/stock/980?warehouse_id=WH001
  2 threads and 10 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    36.74ms  180.95ms   1.51s    96.17%
    Req/Sec     1.71k   532.46     5.40k    70.74%
  102081 requests in 31.36s, 29.30MB read
  Socket errors: connect 0, read 15, write 0, timeout 10
Requests/sec:   3255.26
Transfer/sec:      0.93MB
```

**关键指标**：
- **平均延迟**: 36.74ms
- **标准差**: 180.95ms（延迟波动大）
- **最大延迟**: 1.51s
- **96.17%** 的请求延迟 < 217.69ms (Avg + Stdev)
- **吞吐量**: 3255.26 req/s
- **数据传输率**: 0.93 MB/s
- **总请求数**: 102,081 次（31.36 秒）
- **Socket 错误**: read 15, timeout 10（占比 0.024%）

### 优化后数据（Redis MGET + Gunicorn 配置优化后）

**原始输出**：
```
Running 30s test @ http://127.0.0.1:8000/api/v1/inventory/stock/980?warehouse_id=WH001
  2 threads and 10 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     3.19ms    3.58ms  86.32ms   93.93%
    Req/Sec     1.86k     1.02k   15.35k    95.69%
  107458 requests in 29.02s, 30.85MB read
  Socket errors: connect 0, read 21, write 0, timeout 20
Requests/sec:   3703.35
Transfer/sec:      1.06MB
```

**关键指标**：
- **平均延迟**: 3.19ms
- **标准差**: 3.58ms（延迟非常稳定）
- **最大延迟**: 86.32ms
- **93.93%** 的请求延迟 < 6.77ms (Avg + Stdev)
- **吞吐量**: **3703.35 req/s**
- **数据传输率**: 1.06 MB/s
- **总请求数**: 107,458 次（29.02 秒）
- **Socket 错误**: read 21, timeout 20（占比 0.038%）

---

## 🎯 优化对比

### 优化前后关键指标对比

| 指标 | 优化前 | 优化后 | 变化幅度 |
|------|--------|--------|----------|
| **平均延迟** | 36.74ms | **3.19ms** | **⬇️ 91.3%** |
| **标准差** | 180.95ms | **3.58ms** | **⬇️ 98.0%** |
| **最大延迟** | 1.51s | **86.32ms** | **⬇️ 94.3%** |
| **吞吐量** | 3255.26 req/s | **3703.35 req/s** | **⬆️ 13.8%** |
| **总请求数** | 102,081 次 | **107,458 次** | **⬆️ 5.3%** |
| **错误率** | 0.024% | 0.038% | 略升（可接受） |

### 延迟分布优化

**优化前**：
- 96.17% 的请求延迟 < 217.69ms (Avg + Stdev = 36.74 + 180.95)
- 延迟波动极大，标准差高达 180.95ms

**优化后**：
- 93.93% 的请求延迟 < 6.77ms (Avg + Stdev = 3.19 + 3.58)
- 延迟非常稳定，标准差仅 3.58ms

**核心改进**：
- ✅ **延迟稳定性提升巨大**：标准差从 180.95ms 降至 3.58ms（**⬇️ 98.0%**）
- ✅ **平均延迟大幅下降**：36.74ms → 3.19ms（**⬇️ 91.3%**）
- ✅ **最大延迟显著改善**：1.51s → 86.32ms（**⬇️ 94.3%**）
- ✅ **吞吐量稳步提升**：3255 → 3703 req/s（**⬆️ 13.8%**）

---

## 🔧 核心优化措施

### 1. Redis 批量读取（MGET）

**优化前**：
```python
# 2 次 Redis GET（2 次网络往返）
info = redis.get("stock:full:...")
if info is None:
    available = redis.get("stock:available:...")
```

**优化后**：
```python
# 1 次 MGET（仅 1 次网络往返，读取 5 个字段）
keys = [
    "stock:full:{warehouse_id}:{product_id}",
    "stock:available:{warehouse_id}:{product_id}",
    "stock:reserved:{warehouse_id}:{product_id}",
    "stock:frozen:{warehouse_id}:{product_id}",
    "stock:safety:{warehouse_id}:{product_id}"
]
values = redis.mget(keys)
```

**收益**：
- ✅ 网络往返次数：2 次 → 1 次（**减少 50%**）
- ✅ Redis IO 操作：2 次 GET → 1 次 MGET（**减少 50%**）
- ✅ **延迟稳定性大幅提升**：标准差 ⬇️ 98.0%

### 2. Gunicorn 高并发配置

**配置**：
```bash
CMD ["gunicorn", "app.main:app", 
     "-k", "uvicorn.workers.UvicornWorker", 
     "-w", "8",                      # 8 个 worker 进程
     "--worker-connections", "2000",  # 每个 worker 2000 连接
     "-b", "0.0.0.0:8000",
     "--timeout", "60",
     "--keep-alive", "5"]
```

**理论并发能力**：
- 8 workers × 2000 connections = **16,000 并发连接**

### 3. Celery Worker 优化

**配置**：
```bash
celery -A celery_app worker \
  --loglevel=info \
  --concurrency=8 \
  -Ofair \
  --prefetch-multiplier=1
```

**优化效果**：
- `-Ofair`: 公平调度，避免任务抢占
- `--prefetch-multiplier=1`: 每个 worker 一次只拿一个任务

### 4. Redis & PostgreSQL 连接优化

```yaml
# Redis
command: redis-server --appendonly yes --maxclients 10000

# PostgreSQL
command: >
  postgres
  -c max_connections=500
  -c shared_buffers=256MB
  -c work_mem=16MB
```

---

## 💡 最佳实践总结

### Redis 批量读取原则

**能用 MGET 就不用多次 GET**

```python
# ❌ 反模式
available = redis.get(key1)
reserved = redis.get(key2)
frozen = redis.get(key3)

# ✅ 正模式
keys = [key1, key2, key3]
available, reserved, frozen = redis.mget(keys)
```

### Gunicorn Worker 配置公式

```
worker 数量 = CPU 核心数 × 2 + 1
worker 连接数 = 2000（默认足够）
```

**示例**（8 核 CPU）：
```bash
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 8 \
  --worker-connections 2000 \
  -b 0.0.0.0:8000
```

### Celery Worker 推荐配置

```bash
celery -A celery_app worker \
  --concurrency=8 \        # CPU 核心数 × 2
  -Ofair \                 # 公平调度
  --prefetch-multiplier=1  # 精准预取
```

---

## 📉 监控与告警

### 关键监控指标

| 指标 | 阈值 | 级别 | 说明 |
|------|------|------|------|
| 平均延迟 | <5ms | OK | 正常性能 |
| 平均延迟 | 5-10ms | WARNING | 性能警告 |
| 平均延迟 | >10ms | CRITICAL | 严重性能问题 |
| **标准差** | **<10ms** | **OK** | **延迟稳定** |
| **标准差** | **>50ms** | **WARNING** | **延迟波动大** |
| 吞吐量 | >3000 req/s | OK | 高性能 |
| 错误率 | <0.1% | OK | 正常 |

### 实时监控命令

```bash
# 实时查看延迟分布
wrk -t2 -c10 -d30s http://127.0.0.1:8000/api/v1/inventory/stock/980?warehouse_id=WH001

# 监控数据库连接
docker exec fastapi_db psql -U postgres -d mydb -c "SELECT count(*) FROM pg_stat_activity;"

# 监控 Redis 连接
docker exec fastapi_redis redis-cli INFO clients

# 查看应用日志中的性能指标
docker logs -f fastapi_app | grep -E "duration|PERF"
```

---

## 🎯 下一步优化计划

1. **引入 HTTP/2**：支持多路复用，进一步降低延迟
2. **实现 Redis Cluster**：水平扩展 Redis 容量
3. **添加 CDN 加速**：静态资源和缓存数据下沉
4. **优化 Lua 脚本**：将更多业务逻辑移到 Redis 端执行
5. **实施 APM 监控**：全链路追踪和性能分析

---

**测试人员**: AI Assistant  
**审核人员**: 开发团队  
**文档版本**: v2.0.0（已修正数据）  
**最后更新**: 2026-03-14
