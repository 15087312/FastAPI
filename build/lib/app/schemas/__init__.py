"""Schemas - 数据模型定义模块"""

from app.schemas.base import BaseSchema
from app.schemas.inventory import (
    ProductImageSchema,
    ProductSchema,
    ReserveStockRequest,
    StockStatusResponse,
    LockProductsRequest,
    LockProductsResponse,
    DeductStockRequest,
    DeductStockResponse,
)
from app.schemas.order import (
    OrderItemSchema,
    OrderSchema,
    CreateOrderRequest,
    CreateOrderResponse,
)
from app.schemas.system import (
    SystemMetricsResponse,
    CpuResponse,
    MemoryResponse,
    DiskResponse,
    NetworkResponse,
    DatabasePoolResponse,
    RedisConnectionResponse,
)

__all__ = [
    # Base
    "BaseSchema",
    
    # Inventory
    "ProductImageSchema",
    "ProductSchema",
    "ReserveStockRequest",
    "StockStatusResponse",
    "LockProductsRequest",
    "LockProductsResponse",
    "DeductStockRequest",
    "DeductStockResponse",
    
    # Order
    "OrderItemSchema",
    "OrderSchema",
    "CreateOrderRequest",
    "CreateOrderResponse",
    
    # System
    "SystemMetricsResponse",
    "CpuResponse",
    "MemoryResponse",
    "DiskResponse",
    "NetworkResponse",
    "DatabasePoolResponse",
    "RedisConnectionResponse",
]
