"""库存API专用的Pydantic模型和响应格式"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
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
        description="商品 ID",
        examples=[1]
    )
    quantity: int = Field(
        ..., 
        gt=0, 
        description="预占数量",
        examples=[2]
    )
    order_id: str = Field(
        ..., 
        min_length=1,
        max_length=64,
        description="订单 ID",
        examples=["ORD202401010001"]
    )


class BatchStockQueryRequest(BaseModel):
    """批量查询库存请求"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="商品 ID 列表",
        examples=[[1, 2, 3]]
    )


class CleanupRequest(BaseModel):
    """清理任务请求"""
    batch_size: int = Field(
        500,
        ge=1,
        le=10000,
        description="批处理大小",
        examples=[500]
    )


class IncreaseStockRequest(BaseModel):
    """入库/补货请求"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_id: int = Field(
        ...,
        gt=0,
        description="商品 ID",
        examples=[1]
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="入库数量",
        examples=[100]
    )
    order_id: Optional[str] = Field(
        None,
        max_length=64,
        description="入库单号（可选）",
        examples=["RK202401010001"]
    )
    operator: Optional[str] = Field(
        None,
        max_length=64,
        description="操作人",
        examples=["admin"]
    )
    remark: Optional[str] = Field(
        None,
        max_length=255,
        description="备注",
        examples=["常规补货"]
    )


class AdjustStockRequest(BaseModel):
    """库存调整请求"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_id: int = Field(
        ...,
        gt=0,
        description="商品 ID",
        examples=[1]
    )
    adjust_type: str = Field(
        ...,
        description="调整类型：increase(增加) / decrease(减少) / set(设置为)",
        examples=["increase"]
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="调整数量",
        examples=[10]
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="调整原因",
        examples=["盘点修正"]
    )
    operator: Optional[str] = Field(
        None,
        max_length=64,
        description="操作人",
        examples=["admin"]
    )


class FreezeStockRequest(BaseModel):
    """冻结库存请求"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_id: int = Field(
        ...,
        gt=0,
        description="商品 ID",
        examples=[1]
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="冻结数量",
        examples=[5]
    )
    reason: Optional[str] = Field(
        None,
        max_length=255,
        description="冻结原因",
        examples=["待检品"]
    )
    operator: Optional[str] = Field(
        None,
        max_length=64,
        description="操作人",
        examples=["admin"]
    )


class UnfreezeStockRequest(BaseModel):
    """解冻库存请求"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_id: int = Field(
        ...,
        gt=0,
        description="商品 ID",
        examples=[1]
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="解冻数量",
        examples=[5]
    )
    reason: Optional[str] = Field(
        None,
        max_length=255,
        description="解冻原因",
        examples=["检验通过"]
    )
    operator: Optional[str] = Field(
        None,
        max_length=64,
        description="操作人",
        examples=["admin"]
    )


class BatchReserveItem(BaseModel):
    """批量预占单项"""
    warehouse_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    )
    product_id: int = Field(
        ...,
        gt=0,
        description="商品 ID",
        examples=[1]
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="预占数量",
        examples=[2]
    )


class BatchReserveRequest(BaseModel):
    """批量预占请求"""
    order_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="订单 ID",
        examples=["ORD202401010001"]
    )
    items: List[BatchReserveItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="预占商品列表",
        examples=[
            [{"warehouse_id": "WH01", "product_id": 1, "quantity": 2},
            {"warehouse_id": "WH01", "product_id": 2, "quantity": 3}]
        ]
    )


class BatchReleaseRequest(BaseModel):
    """批量释放请求"""
    order_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="订单 ID",
        examples=["ORD202401010001"]
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
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID"
    )
    product_id: int = Field(
        ...,
        description="商品ID"
    )
    available_stock: int = Field(
        ...,
        ge=0,
        description="可用库存"
    )
    reserved_stock: int = Field(
        0,
        description="预占库存"
    )
    frozen_stock: int = Field(
        0,
        description="冻结库存"
    )
    in_transit_stock: int = Field(
        0,
        description="在途库存"
    )
    safety_stock: int = Field(
        0,
        description="安全库存"
    )
    total_stock: int = Field(
        0,
        description="总库存（可用+预占+冻结+在途）"
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


class IncreaseStockResponse(BaseResponse):
    """入库响应"""
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID"
    )
    product_id: Optional[int] = Field(
        None,
        description="商品ID"
    )
    before_stock: Optional[int] = Field(
        None,
        description="入库前库存"
    )
    after_stock: Optional[int] = Field(
        None,
        description="入库后库存"
    )


class AdjustStockResponse(BaseResponse):
    """库存调整响应"""
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID"
    )
    product_id: Optional[int] = Field(
        None,
        description="商品ID"
    )
    before_available: Optional[int] = Field(
        None,
        description="调整前可用库存"
    )
    after_available: Optional[int] = Field(
        None,
        description="调整后可用库存"
    )


class FreezeStockResponse(BaseResponse):
    """冻结/解冻响应"""
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID"
    )
    product_id: Optional[int] = Field(
        None,
        description="商品ID"
    )
    before_frozen: Optional[int] = Field(
        None,
        description="操作前冻结库存"
    )
    after_frozen: Optional[int] = Field(
        None,
        description="操作后冻结库存"
    )


class BatchReserveItemResponse(BaseModel):
    """批量预占单项响应"""
    warehouse_id: str
    product_id: int
    success: bool
    message: str


class BatchReserveResponse(BaseResponse):
    """批量预占响应"""
    order_id: Optional[str] = Field(
        None,
        description="订单ID"
    )
    total_items: Optional[int] = Field(
        None,
        description="总商品数"
    )
    success_items: Optional[int] = Field(
        None,
        description="成功商品数"
    )
    failed_items: Optional[int] = Field(
        None,
        description="失败商品数"
    )
    details: Optional[List[BatchReserveItemResponse]] = Field(
        None,
        description="详细结果"
    )


class InventoryLogsQueryRequest(BaseModel):
    """库存流水查询请求"""
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID（可选）"
    )
    product_id: Optional[int] = Field(
        None,
        gt=0,
        description="商品ID（可选）"
    )
    order_id: Optional[str] = Field(
        None,
        description="订单ID（可选）"
    )
    change_type: Optional[str] = Field(
        None,
        description="变更类型（可选）"
    )
    start_date: Optional[str] = Field(
        None,
        description="开始时间（ISO格式）"
    )
    end_date: Optional[str] = Field(
        None,
        description="结束时间（ISO格式）"
    )
    page: int = Field(
        1,
        ge=1,
        description="页码"
    )
    page_size: int = Field(
        50,
        ge=1,
        le=100,
        description="每页数量"
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
    warehouse_id: Optional[str] = Field(
        None,
        description="仓库ID"
    )
    product_id: int
    order_id: Optional[str]
    change_type: str
    quantity: int
    before_available: int
    after_available: int
    before_reserved: int = Field(
        0,
        description="变更前预占库存"
    )
    after_reserved: int = Field(
        0,
        description="变更后预占库存"
    )
    before_frozen: int = Field(
        0,
        description="变更前冻结库存"
    )
    after_frozen: int = Field(
        0,
        description="变更后冻结库存"
    )
    remark: Optional[str] = Field(
        None,
        description="备注"
    )
    created_at: str
    operator: Optional[str]
    source: Optional[str]


class PaginatedLogsResponse(BaseModel):
    """分页库存流水响应"""
    success: bool = True
    data: List[InventoryLogDetail] = Field(
        ...,
        description="日志列表"
    )
    total: int = Field(
        ...,
        description="总记录数"
    )
    page: int = Field(
        ...,
        description="当前页码"
    )
    page_size: int = Field(
        ...,
        description="每页数量"
    )
    total_pages: int = Field(
        ...,
        description="总页数"
    )


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