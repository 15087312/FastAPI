# 库存服务 - 快速参考卡片

## 🚀 启动命令

```bash
# 开发环境（单进程，热重载）
uvicorn app.main:app --reload

# 生产环境（多进程）
python app\main.py

# Docker Compose 启动
docker compose up -d
```

---

## 📊 API 端点速查

### 核心接口
| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 无 |
| GET | `/api/v1/inventory/stock/{product_id}` | 查询库存 | product_id |
| POST | `/api/v1/inventory/reserve` | 预占库存 | warehouse_id, product_id, quantity, order_id |
| POST | `/api/v1/inventory/confirm/{order_id}` | 确认库存 | order_id |
| POST | `/api/v1/inventory/release/{order_id}` | 释放库存 | order_id |

### 监控接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/system/cpu` | CPU 使用率 |
| GET | `/api/v1/system/memory` | 内存使用率 |
| GET | `/api/v1/system/disk` | 磁盘使用率 |
| GET | `/api/v1/system/network` | 网络流量 |
| GET | `/api/v1/system/db-pool` | 数据库连接池 |
| GET | `/api/v1/system/redis` | Redis 状态 |
| GET | `/api/v1/system/metrics` | 所有指标 |

---

## 🧪 压力测试

```bash
# 简单测试（只查询）
python simple_stress_test.py

# 完整测试（混合场景）
python stress_test.py
```

**性能基准**:
- ✅ QPS: 1000+
- ✅ P99: < 100ms
- ✅ 成功率：100%

---

## 🔧 配置文件

### .env (本地环境)
```ini
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=YourStr0ngP@ssw0rd!2024
REDIS_HOST=localhost
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DEBUG=False
```

### .env.docker (Docker 环境)
```ini
POSTGRES_HOST=db
POSTGRES_PASSWORD=DockerStr0ngP@ss!2024
REDIS_HOST=redis
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DEBUG=False
```

---

## 🏥 健康检查

### 快速检查
```bash
curl http://localhost:8000/health
```

### Python 脚本
```python
import requests
r = requests.get('http://localhost:8000/health')
print(r.json())
```

### 检查项
- ✅ 数据库连接
- ✅ Redis 连接
- ✅ 连接池状态
- ✅ CPU/内存
- ✅ Kafka 消费者

---

## 📝 常见问题

### Q1: 端口被占用怎么办？
```bash
# 系统会自动尝试下一个可用端口
# 从 8000 开始，最多尝试 10 个端口
```

### Q2: 如何查看实时日志？
```bash
# 应用日志
docker compose logs -f app

# 数据库日志
docker compose logs -f db

# Redis 日志
docker compose logs -f redis
```

### Q3: 如何重置数据库？
```bash
# 删除所有数据
docker compose down -v

# 重新启动
docker compose up -d

# 运行迁移
python -c "from alembic.config import Config; from alembic import command; alembic_cfg = Config('alembic.ini'); command.upgrade(alembic_cfg, 'head')"
```

### Q4: 如何添加测试数据？
```bash
python app\init_data.py
```

---

## 📈 性能优化建议

### 连接池配置
```python
# 小型应用
DB_POOL_SIZE = 8
DB_MAX_OVERFLOW = 16

# 中型应用（当前配置）
DB_POOL_SIZE = 11
DB_MAX_OVERFLOW = 22

# 大型应用
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 40
```

### Worker 数量
```python
# 公式：min(CPU * 2 + 1, 8)
# 16 核 CPU → 8 workers
```

---

## 🔗 重要链接

- **API 文档**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- **pgAdmin**: http://localhost:5050

---

## 🎯 关键指标阈值

| 指标 | 正常 | 警告 | 危险 |
|------|------|------|------|
| CPU | < 70% | 70-90% | > 90% |
| 内存 | < 80% | 80-95% | > 95% |
| P95 响应时间 | < 100ms | 100-500ms | > 500ms |
| 错误率 | < 0.1% | 0.1-1% | > 1% |
| 连接池使用率 | < 70% | 70-90% | > 90% |

---

## 🛠️ 调试技巧

### 1. 启用详细日志
```ini
# .env
DEBUG=True
LOG_LEVEL=DEBUG
```

### 2. 查看 SQL 执行
```python
# 在代码中添加
import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### 3. 性能分析
```bash
# 安装 profiling 工具
pip install py-spy

# 分析进程
py-spy top --pid <process_id>

# 生成火焰图
py-spy record -o profile.svg --pid <process_id>
```

---

## 📦 Docker 常用命令

```bash
# 查看运行状态
docker compose ps

# 重启服务
docker compose restart <service_name>

# 进入容器
docker compose exec app bash

# 查看资源使用
docker stats

# 清理无用资源
docker compose down -v
docker system prune -a
```

---

## 🎓 学习资源

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Redis 文档](https://redis.io/documentation)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)

---

**版本**: v1.0  
**更新**: 2026-03-12  
**打印建议**: 此文档适合 A4 纸打印携带
