"""库存管理 API 路由总入口"""

from fastapi import APIRouter

# 导入各个模块的路由
from app.routers import (
    inventory_query,
    inventory_operations,
    inventory_adjustment,
    inventory_batch,
    inventory_logs,
)

# 创建主路由器
router = APIRouter(prefix="/inventory", tags=["库存管理"])

# 注册子路由
router.include_router(inventory_query.router)
router.include_router(inventory_operations.router)
router.include_router(inventory_adjustment.router)
router.include_router(inventory_batch.router)
router.include_router(inventory_logs.router)
