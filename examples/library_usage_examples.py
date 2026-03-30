"""
库存微服务库 - 基础使用示例

本示例展示如何在其他项目中集成和使用 inventory-service 库
"""

# ============================================================
# 示例 1: 作为 FastAPI 应用直接运行
# ============================================================

"""
方式 1: 命令行启动
------------------
$ inventory-server --host 0.0.0.0 --port 8000

方式 2: 使用 Gunicorn 生产环境
-------------------------------
$ gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
"""


# ============================================================
# 示例 2: 在现有 FastAPI 项目中集成
# ============================================================

from fastapi import FastAPI
from app.routers import (
    inventory_router,      # 库存操作路由
    inventory_query,       # 库存查询路由
    inventory_batch,       # 批量操作路由
    system_monitor         # 系统监控路由
)

def create_inventory_app():
    """创建库存服务 FastAPI 应用"""
    
    app = FastAPI(
        title="库存微服务 API",
        description="专业的库存管理微服务",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # 注册库存相关路由
    app.include_router(inventory_router.router, prefix="/api/v1")
    app.include_router(inventory_query.router, prefix="/api/v1")
    app.include_router(inventory_batch.router, prefix="/api/v1")
    app.include_router(system_monitor.router, prefix="/api/v1")
    
    return app


# ============================================================
# 示例 3: 调用库存服务 API
# ============================================================

import httpx
import asyncio

class InventoryClient:
    """库存服务客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    async def reserve_stock(self, warehouse_id: str, product_id: int, 
                           quantity: int, order_id: str):
        """预占库存"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/inventory/reserve",
                json={
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "order_id": order_id
                }
            )
            return response.json()
    
    async def confirm_stock(self, warehouse_id: str, product_id: int, 
                           order_id: str):
        """确认库存"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/inventory/confirm",
                json={
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "order_id": order_id
                }
            )
            return response.json()
    
    async def query_stock(self, warehouse_id: str, product_id: int):
        """查询库存"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/inventory/stock/{warehouse_id}/{product_id}"
            )
            return response.json()


# 使用示例
async def main():
    client = InventoryClient()
    
    # 预占库存
    result = await client.reserve_stock(
        warehouse_id="WH001",
        product_id=980,
        quantity=5,
        order_id="ORDER-2024-001"
    )
    print(f"预占结果：{result}")
    
    # 查询库存
    stock = await client.query_stock("WH001", 980)
    print(f"当前库存：{stock}")
    
    # 确认库存
    confirm_result = await client.confirm_stock("WH001", 980, "ORDER-2024-001")
    print(f"确认结果：{confirm_result}")


if __name__ == "__main__":
    asyncio.run(main())


# ============================================================
# 示例 4: 直接使用服务层（不通过 API）
# ============================================================

"""
from app.services.inventory_service import InventoryService
from app.db.session import SessionLocal

# 初始化数据库会话
db = SessionLocal()

# 创建服务实例
service = InventoryService(db)

# 调用服务方法
async def direct_service_call():
    # 预占库存
    result = await service.reserve_inventory(
        warehouse_id="WH001",
        product_id=980,
        quantity=5,
        order_id="DIRECT-001"
    )
    
    # 提交数据库事务
    db.commit()
    
    return result
"""


# ============================================================
# 示例 5: Celery 异步任务集成
# ============================================================

"""
from celery_app import celery_app
from tasks.inventory_tasks import (
    cleanup_expired_reservations,  # 清理过期预占
    sync_inventory_to_db          # 同步库存到数据库
)

# 调用异步任务
@celery_app.task
def process_order_task(order_id: str):
    # 订单处理逻辑
    pass

# 触发任务
result = cleanup_expired_reservations.delay()
task_status = result.status
"""


# ============================================================
# 示例 6: 自定义配置
# ============================================================

"""
from app.core.config import Settings

class CustomSettings(Settings):
    """自定义配置"""
    
    # 修改数据库配置
    POSTGRES_HOST = "custom-db-host"
    POSTGRES_PORT = 5433
    
    # 修改 Redis 配置
    REDIS_HOST = "custom-redis-host"
    REDIS_PORT = 6380
    
    # 禁用 Kafka
    KAFKA_ENABLED = False
    
    # 自定义端口
    PORT = 9000

# 使用自定义配置
settings = CustomSettings()
"""


# ============================================================
# 示例 7: Docker Compose 集成到其他项目
# ============================================================

"""
在你的项目 docker-compose.yml 中添加：

version: '3.8'

services:
  inventory-service:
    image: your-registry/inventory-service:latest
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_HOST=db
      - REDIS_HOST=redis
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=inventory
  
  redis:
    image: redis:7-alpine
  
  # 你的主应用
  your-app:
    build: .
    depends_on:
      - inventory-service
    environment:
      - INVENTORY_SERVICE_URL=http://inventory-service:8000
"""
