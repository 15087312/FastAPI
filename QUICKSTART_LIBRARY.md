# 将库存微服务作为库使用的快速指南

## 🎯 目标

将当前 FastAPI 项目改造成可复用的 Python 包，供其他项目调用。

---

## 📦 步骤 1: 安装必要工具

```bash
# 安装打包工具
pip install build twine wheel setuptools
```

---

## 🔨 步骤 2: 构建包

```bash
# 方式 1: 使用现代构建工具（推荐）
python -m build

# 方式 2: 使用 setup.py
python setup.py sdist bdist_wheel
```

成功后会在 `dist/` 目录生成：
- `inventory_service-1.0.0.tar.gz` (源码分发包)
- `inventory_service-1.0.0-py3-none-any.whl` (wheel 包)

---

## 🧪 步骤 3: 本地测试安装

```bash
# 安装到本地虚拟环境
pip install -e .

# 验证安装
python -c "import app; print('✅ 安装成功')"
```

---

## 🚀 步骤 4: 在其他项目中使用

### 方式 A: 直接引用本地包

```bash
# 在你的项目 requirements.txt 中添加
-e /path/to/inventory-service
```

### 方式 B: 安装到系统

```bash
pip install /path/to/inventory-service/dist/inventory_service-1.0.0-py3-none-any.whl
```

### 方式 C: 上传到 PyPI（可选）

```bash
# 上传到 TestPyPI（测试）
twine upload --repository testpypi dist/*

# 上传到正式 PyPI
twine upload dist/*
```

然后在你的项目中：
```bash
pip install inventory-service
```

---

## 💡 步骤 5: 集成到你的项目

### 场景 1: 作为独立服务运行

```bash
# 启动库存服务
inventory-server --host 0.0.0.0 --port 8000

# 或使用 Gunicorn 生产部署
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
```

### 场景 2: 在现有 FastAPI 项目中导入

```python
# your_project/main.py
from fastapi import FastAPI
from app.routers import inventory_router

app = FastAPI()

# 注册库存路由
app.include_router(inventory_router.router, prefix="/api/v1/inventory")
```

### 场景 3: 通过 HTTP 调用

```python
# your_project/services/order_service.py
import httpx

class OrderService:
    def __init__(self, inventory_url: str):
        self.inventory_url = inventory_url
    
    async def create_order(self, order_data):
        # 1. 创建订单
        # ...
        
        # 2. 预占库存
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.inventory_url}/api/v1/inventory/reserve",
                json={
                    "warehouse_id": "WH001",
                    "product_id": order_data.product_id,
                    "quantity": order_data.quantity,
                    "order_id": order_data.id
                }
            )
            inventory_result = response.json()
        
        # 3. 处理结果
        return inventory_result
```

### 场景 4: Docker Compose 集成

```yaml
# docker-compose.yml
version: '3.8'

services:
  # 库存服务
  inventory:
    image: your-registry/inventory-service:latest
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_HOST=db
      - REDIS_HOST=redis
    depends_on:
      - db
      - redis
  
  # 你的主应用
  web:
    build: ./your-web-app
    ports:
      - "3000:3000"
    environment:
      - INVENTORY_SERVICE_URL=http://inventory:8000
    depends_on:
      - inventory
  
  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD=secret
  
  redis:
    image: redis:7-alpine
```

---

## 📋 配置文件说明

### 环境变量 (.env)

```bash
# 必须配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=inventory_db

REDIS_HOST=localhost
REDIS_PORT=6379

# 可选配置
KAFKA_ENABLED=false
DEBUG=true
PORT=8000
```

### Alembic 数据库迁移

```bash
# 初始化迁移（如果是新数据库）
alembic init alembic

# 创建新迁移
alembic revision -m "create_inventory_tables"

# 应用迁移
alembic upgrade head
```

---

## 🧩 核心模块说明

### 可直接调用的模块

```python
# 服务层
from app.services.inventory_service import InventoryService
from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_reservation import ReservationService

# 数据模型
from app.models.product_stocks import ProductStock
from app.models.inventory_logs import InventoryLog
from app.models.inventory_reservations import InventoryReservation

# Schema
from app.schemas.inventory import (
    InventoryReserveSchema,
    InventoryConfirmSchema,
    InventoryQuerySchema
)

# 工具类
from app.core.kafka_producer import send_inventory_event
from app.core.redis import redis_client, async_redis
```

### 使用示例

```python
from app.services.inventory_service import InventoryService
from app.db.session import SessionLocal

# 创建数据库会话
db = SessionLocal()

# 创建服务实例
service = InventoryService(db)

# 调用方法
async def reserve():
    result = await service.reserve_inventory(
        warehouse_id="WH001",
        product_id=980,
        quantity=10,
        order_id="TEST-001"
    )
    db.commit()
    return result
```

---

## 📊 API 端点总览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/inventory/reserve` | POST | 预占库存 |
| `/api/v1/inventory/confirm` | POST | 确认库存 |
| `/api/v1/inventory/release` | POST | 释放库存 |
| `/api/v1/inventory/stock/{warehouse_id}/{product_id}` | GET | 查询库存 |
| `/api/v1/inventory/batch/reserve` | POST | 批量预占 |
| `/health` | GET | 健康检查 |

完整文档：http://localhost:8000/docs

---

## ⚠️ 注意事项

1. **数据库依赖**: 需要 PostgreSQL 15+
2. **缓存依赖**: 需要 Redis 7+
3. **消息队列**: Kafka 是可选的（可通过 `KAFKA_ENABLED=false` 禁用）
4. **Python 版本**: 需要 3.9+

---

## 🐛 常见问题

### Q: 如何在已有数据库的项目中使用？

A: 修改 `.env` 中的数据库配置，指向你的现有数据库，然后运行 `alembic upgrade head` 创建表。

### Q: 可以只用部分功能吗？

A: 可以！只导入你需要的模块即可。例如只用服务层而不使用 API。

### Q: 如何自定义业务逻辑？

A: 继承 `InventoryService` 类并重写相应方法。

### Q: 支持多仓库吗？

A: 支持！所有操作都通过 `warehouse_id` 和 `product_id` 来区分。

---

## 📖 更多文档

- 详细使用：参见 `LIBRARY_USAGE.md`
- 示例代码：参见 `examples/library_usage_examples.py`
- API 文档：运行后访问 http://localhost:8000/docs

---

## ✅ 检查清单

- [ ] 已安装构建工具
- [ ] 已构建包（`dist/` 目录有文件）
- [ ] 已本地测试安装
- [ ] 已在目标项目中引用
- [ ] 已配置环境变量
- [ ] 已运行数据库迁移
- [ ] 服务可以正常启动
- [ ] API 可以正常调用

---

**完成！** 🎉 现在你可以在其他项目中使用这个库存微服务库了！
