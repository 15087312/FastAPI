# app/schemas/product.py
from pydantic import BaseModel, Field
from typing import List, Optional



class ProductImageSchema(BaseModel):
    id: int
    url: str
    is_main: bool
    sort_order: int

    class Config:
        orm_mode = True

class ProductSchema(BaseModel):
    id: int
    name: str
    sku: str
    description: Optional[str]
    price: float
    stock: int
    sales_count: int
    is_active: bool
    category_id: Optional[int]
    images: List[ProductImageSchema] = []

    class Config:
        orm_mode = True

# 请求扣减库存
class ReserveStockRequest(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)

# 响应库存状态
class StockStatusResponse(BaseModel):
    product_id: int
    stock: int

class LockProductsRequest(BaseModel):
    product_ids: List[int]

class LockProductsResponse(BaseModel):
    locked_product_ids: List[int]

class DeductStockRequest(BaseModel):
    items: List[ReserveStockRequest]

class DeductStockResponse(BaseModel):
    success: bool
    message: str
    remaining_stock: List[StockStatusResponse] = []










