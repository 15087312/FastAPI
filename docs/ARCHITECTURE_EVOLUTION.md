# 库存服务架构演进说明

## 📋 版本历史

### v3.0 - 纯 Redis 架构（当前版本）

**核心特点**：
- ✅ **Redis 作为主存储**：所有库存操作都在 Redis 中完成
- ✅ **Lua 脚本原子操作**：预占、确认、释放全部原子执行
- ✅ **Kafka 异步同步数据库**：不阻塞 API，最终一致性
- ✅ **数据永不过期**：Redis 数据持久化策略
- ✅ **高性能**：QPS 1000+，P99 < 100ms

**技术栈**：
```
API (FastAPI) → Service (纯 Redis) → Kafka → PostgreSQL (异步写入)
```

**关键文件**：
- `app/services/inventory_reservation.py` - Lua 脚本实现
- `app/services/inventory_operation.py` - Redis 操作实现
- `app/services/kafka_consumer.py` - 数据库异步同步
- `app/services/inventory_cache.py` - 缓存服务

---

### v2.0 - 混合架构（已弃用）

**核心特点**：
- ⚠️ **Redis 作为缓存层**：数据库为唯一数据源
- ⚠️ **行级锁保证并发**：`SELECT FOR UPDATE`
- ⚠️ **同步写数据库**：API 响应慢
- ⚠️ **性能瓶颈**：QPS ~500，P99 ~200ms

**技术栈**：
```
API → Service → Redis (缓存) + PostgreSQL (行级锁，主存储)
```

**问题**：
1. 行级锁导致并发请求串行化
2. 数据库连接池易耗尽
3. 响应时间受数据库性能影响大
4. 高并发下数据库压力大

---

### v1.0 - 分布式锁架构（已弃用）

**核心特点**：
- ❌ **Redis Redlock 分布式锁**：保证互斥访问
- ❌ **数据库读写**：传统 ORM 操作
- ❌ **性能最差**：QPS ~200，P99 > 500ms

**技术栈**：
```
API → Service → Redlock → Redis/PostgreSQL
```

**问题**：
1. 抢锁开销大（2 次 Redis 往返）
2. 客户端崩溃可能导致死锁
3. Redis 主从切换可能丢锁
4. 锁竞争激烈时性能急剧下降

---

## 🔄 架构演进原因

### 为什么从 v2.0 升级到 v3.0？

#### 1. 性能瓶颈
```
v2.0 行级锁模式：
并发 100 请求 → 数据库排队 → P99 = 200ms

v3.0 Redis 模式：
并发 100 请求 → Redis 内存操作 → P99 = 30ms
性能提升：**6.7 倍**
```

#### 2. 数据库压力
```
v2.0:
每个请求都需要数据库连接
1000 QPS → 需要 100+ 连接池大小

v3.0:
只有 Kafka 消费者需要数据库连接
1000 QPS → 只需 10-20 连接池大小（批量写入）
```

#### 3. 可用性
```
v2.0:
数据库故障 → 服务完全不可用

v3.0:
数据库故障 → API 仍可正常读写（Kafka 堆积消息）
数据库恢复后自动追平数据
```

#### 4. 扩展性
```
v2.0:
数据库连接数限制 → 难以水平扩展

v3.0:
Redis Cluster 可水平扩展
Kafka Partition 可并行消费
```

---

## 📊 性能对比

| 指标 | v1.0 (Redlock) | v2.0 (行级锁) | v3.0 (纯 Redis) |
|------|---------------|--------------|----------------|
| **QPS** | ~200 | ~500 | **1000+** |
| **P50** | 100ms | 50ms | **7ms** |
| **P90** | 300ms | 150ms | **12ms** |
| **P95** | 400ms | 200ms | **14ms** |
| **P99** | 500ms+ | 200ms | **33ms** |
| **成功率** | 95% | 98% | **100%** |

---

## 🎯 当前架构优势

### 1. 原子性保证
```python
# Lua 脚本原子执行（不可分割）
local current = redis.call('GET', key)
if current < quantity then return {0, "库存不足"} end
redis.call('DECRBY', key, quantity)
redis.call('SADD', reservation_key, order_id)
return {1, "成功"}
```

### 2. 幂等性保证
```python
# Redis 记录操作结果（24 小时有效）
def check_idempotent(operation, order_id):
    key = f"idempotent:{operation}:{order_id}"
    if redis.exists(key):
        return True, redis.get(key)  # 返回之前结果
    return False, None
```

### 3. 最终一致性
```
API 请求 → Redis 操作（立即返回）→ Kafka 消息 → 数据库（异步写入）
                                          ↓
                                    即使数据库故障
                                    也不影响 API
```

### 4. 优雅降级
```
Redis 正常 → 100% 功能可用
Redis 故障 → 只读模式（返回固定值或错误）
数据库故障 → API 正常，Kafka 堆积，恢复后追平
```

---

## 📝 文档更新清单

以下文档需要同步更新（反映 v3.0 架构）：

### ✅ 已更新
- [x] `README.md` - 核心特性、技术栈、架构图
- [x] `app/main.py` - API 描述
- [x] `docs/技术文档.md` - 架构说明

### ⚠️ 待更新（保留历史参考）
- [ ] `docs/api总览.md` - 移除行级锁描述
- [ ] `docs/库存服务性能优化技术文档.md` - 添加 v3.0 性能数据
- [ ] `docs/行级锁与分布式锁选择说明.md` - 标记为历史文档

### 📚 新增文档
- [x] `docs/ARCHITECTURE_EVOLUTION.md` - 本文档（架构演进说明）

---

## 🔧 代码清理清单

### ✅ 已删除
- [x] `app/services/inventory_sync.py` - 未使用

### 📦 保留文件（历史参考）
- [ ] `docs/行级锁与分布式锁选择说明.md` - 标记"此文档描述 v2.0 架构，已弃用"

---

## 💡 最佳实践建议

### 何时使用 Redis？
- ✅ 高频读写操作（库存预占、确认、释放）
- ✅ 需要原子性的场景（Lua 脚本）
- ✅ 低延迟要求（P99 < 50ms）

### 何时使用数据库？
- ✅ 审计日志持久化
- ✅ 财务报表生成
- ✅ 数据备份和恢复
- ✅ 历史数据分析

### 何时使用 Kafka？
- ✅ 异步解耦（订单 → 库存）
- ✅ 事件溯源（库存变更历史）
- ✅ 削峰填谷（大促期间缓冲）

---

*文档更新时间：2026-03-23*
