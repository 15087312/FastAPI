# app/schemas/order.py
from pydantic import BaseModel
from typing import List
from decimal import Decimal
from datetime import datetime
from app.schemas.product import ProductSchema

class OrderItemSchema(BaseModel):
    product_id: int
    product_name_snapshot: str
    quantity: int
    unit_price: Decimal

    class Config:
        orm_mode = True

class OrderSchema(BaseModel):
    id: int
    order_no: str
    user_id: int
    total_amount: Decimal
    status: str  # 可考虑 Enum
    address_snapshot: dict
    paid_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    items: List[OrderItemSchema] = []

    class Config:
        orm_mode = True

# 创建订单请求
class CreateOrderRequest(BaseModel):
    user_id: int
    address_snapshot: dict
    items: List[ReserveStockRequest]  # 复用库存扣减请求

# 创建订单响应
class CreateOrderResponse(BaseModel):
    order_no: str
    total_amount: Decimal
    status: str








