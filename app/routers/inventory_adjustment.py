"""库存调整 API 路由（入库、调整、冻结）"""

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import logging

from app.core.dependencies import get_db, get_redis, get_redlock
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import (
    IncreaseStockResponse,
    AdjustStockResponse,
    FreezeStockResponse,
    IncreaseStockRequest,
    AdjustStockRequest,
    FreezeStockRequest,
    UnfreezeStockRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["库存管理"])


@router.post(
    "/increase",
    response_model=IncreaseStockResponse,
    summary="入库/补货",
    description="""增加商品库存，用于入库、补货等场景。
    
    **使用场景：**
    - 采购入库
    - 退货入库
    - 调拨入库
    - 盘点盈亏调整
    
    **注意：**
    - 如果库存记录不存在，会自动创建
    - 会记录库存变更日志
    """,
    responses={
        200: {
            "description": "入库成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "入库成功",
                        "warehouse_id": "WH01",
                        "product_id": 1,
                        "before_stock": 100,
                        "after_stock": 200,
                        "quantity": 100
                    }
                }
            }
        }
    }
)
async def increase_stock(
    request: IncreaseStockRequest = Body(..., description="入库请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """入库/补货接口"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.increase_stock(
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            quantity=request.quantity,
            order_id=request.order_id,
            operator=request.operator,
            remark=request.remark,
            source="api"
        )
        return IncreaseStockResponse(
            success=True,
            message="入库成功",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"入库失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/adjust",
    response_model=AdjustStockResponse,
    summary="库存调整",
    description="""手动调整商品库存，支持增加、减少、设置为指定值。
    
    **调整类型：**
    - increase: 增加库存
    - decrease: 减少库存
    - set: 设置为指定值
    
    **使用场景：**
    - 盘点修正
    - 库存纠错
    - 人工干预
    """,
    responses={
        200: {
            "description": "调整成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "调整成功",
                        "warehouse_id": "WH01",
                        "product_id": 1,
                        "before_available": 100,
                        "after_available": 110,
                        "adjust_type": "increase",
                        "quantity": 10
                    }
                }
            }
        }
    }
)
async def adjust_stock(
    request: AdjustStockRequest = Body(..., description="调整请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """库存调整接口"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.adjust_stock(
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            adjust_type=request.adjust_type,
            quantity=request.quantity,
            reason=request.reason,
            operator=request.operator,
            source="api"
        )
        return AdjustStockResponse(
            success=True,
            message="调整成功",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"库存调整失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/freeze",
    response_model=FreezeStockResponse,
    summary="冻结库存",
    description="""冻结指定库存，冻结后不可用于预占和销售。
    
    **使用场景：**
    - 待检品
    - 待定分配
    - 临时锁定
    
    **注意：**
    - 只能冻结可用库存
    - 冻结后库存从可用转为冻结状态
    """,
    responses={
        200: {
            "description": "冻结成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "冻结成功",
                        "warehouse_id": "WH01",
                        "product_id": 1,
                        "before_frozen": 0,
                        "after_frozen": 5
                    }
                }
            }
        }
    }
)
async def freeze_stock(
    request: FreezeStockRequest = Body(..., description="冻结请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """冻结库存接口"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.freeze_stock(
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            quantity=request.quantity,
            reason=request.reason,
            operator=request.operator
        )
        return FreezeStockResponse(
            success=True,
            message="冻结成功",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"冻结库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/unfreeze",
    response_model=FreezeStockResponse,
    summary="解冻库存",
    description="""解冻指定库存，解冻后库存回到可用状态。
    
    **使用场景：**
    - 检验通过
    - 分配取消
    - 临时锁定释放
    """,
    responses={
        200: {
            "description": "解冻成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "解冻成功",
                        "warehouse_id": "WH01",
                        "product_id": 1,
                        "before_frozen": 5,
                        "after_frozen": 0
                    }
                }
            }
        }
    }
)
async def unfreeze_stock(
    request: UnfreezeStockRequest = Body(..., description="解冻请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """解冻库存接口"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.unfreeze_stock(
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            quantity=request.quantity,
            reason=request.reason,
            operator=request.operator
        )
        return FreezeStockResponse(
            success=True,
            message="解冻成功",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解冻库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
