"""库存API专用的Pydantic模型和响应格式"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union
from enum import Enum


class ReservationStatus(str, Enum):
    """预占状态枚举"""
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    RELEASED = "released"


class InventoryOperationType(str, Enum):
    """库存操作类型枚举"""
    RESERVE = "reserve"
    CONFIRM = "confirm"
    RELEASE = "release"


# ==================== 请求模型 ====================

class ReserveStockRequest(BaseModel):
    """预占库存请求"""
    product_id: int = Field(
        ..., 
        gt=0, 
        description="商品ID",
        example=1
    )
    quantity: int = Field(
        ..., 
        gt=0, 
        description="预占数量",
        example=2
    )
    order_id: str = Field(
        ..., 
        min_length=1,
        max_length=64,
        description="订单ID",
        example="ORD202401010001"
    )


class BatchStockQueryRequest(BaseModel):
    """批量查询库存请求"""
    product_ids: List[int] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="商品ID列表",
        example=[1, 2, 3]
    )


class CleanupRequest(BaseModel):
    """清理任务请求"""
    batch_size: int = Field(
        500,
        ge=1,
        le=10000,
        description="批处理大小",
        example=500
    )


# ==================== 响应模型 ====================

class BaseResponse(BaseModel):
    """基础响应模型"""
    success: bool = Field(
        ...,
        description="请求是否成功"
    )
    message: Optional[str] = Field(
        None,
        description="响应消息"
    )


class StockResponse(BaseResponse):
    """单个商品库存响应"""
    product_id: int = Field(
        ...,
        description="商品ID"
    )
    available_stock: int = Field(
        ...,
        ge=0,
        description="可用库存数量"
    )


class BatchStockResponse(BaseResponse):
    """批量库存查询响应"""
    data: Dict[int, int] = Field(
        ...,
        description="商品ID到库存数量的映射"
    )


class OperationResponse(BaseResponse):
    """操作响应（预占、确认、释放）"""
    data: Optional[bool] = Field(
        None,
        description="操作结果"
    )


class CleanupResponse(BaseResponse):
    """清理任务响应"""
    cleaned_count: Optional[int] = Field(
        None,
        ge=0,
        description="清理的记录数量"
    )


class CeleryTaskResponse(BaseResponse):
    """Celery任务响应"""
    task_id: Optional[str] = Field(
        None,
        description="任务ID"
    )


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str = Field(
        ...,
        description="任务ID"
    )
    status: str = Field(
        ...,
        description="任务状态描述"
    )
    state: str = Field(
        ...,
        description="任务状态码"
    )


# ==================== 详细信息模型 ====================

class InventoryLogDetail(BaseModel):
    """库存变更日志详情"""
    id: int
    product_id: int
    order_id: Optional[str]
    change_type: str
    quantity: int
    before_available: int
    after_available: int
    created_at: str
    operator: Optional[str]
    source: Optional[str]


class ReservationDetail(BaseModel):
    """预占记录详情"""
    id: int
    order_id: str
    product_id: int
    quantity: int
    status: str
    expired_at: str
    created_at: str


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(
        "healthy",
        description="服务状态"
    )
    service: str = Field(
        "inventory-microservice",
        description="服务名称"
    )
    version: str = Field(
        "1.0.0",
        description="服务版本"
    )


class APIInfoResponse(BaseModel):
    """API信息响应"""
    message: str = Field(
        "欢迎使用库存微服务",
        description="欢迎信息"
    )
    docs: str = Field(
        "/docs",
        description="API文档路径"
    )
    health: str = Field(
        "/health",
        description="健康检查路径"
    )