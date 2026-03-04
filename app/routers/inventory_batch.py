"""批量操作 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import logging

from app.core.dependencies import get_db, get_redis, get_redlock
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import (
    BatchReserveResponse,
    BatchReserveRequest,
    BatchReleaseRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["库存管理"])


@router.post(
    "/reserve-batch",
    response_model=BatchReserveResponse,
    summary="批量预占库存",
    description="""批量预占多个商品库存，保证事务一致性。
    
    **特点：**
    - 全部成功或全部回滚
    - 支持多仓库
    - 使用分布式锁防止并发
    
    **限制：**
    - 单次最多 100 个商品
    - 预占有效期 15 分钟
    """,
    responses={
        200: {
            "description": "批量预占成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "批量预占成功",
                        "order_id": "ORD202401010001",
                        "total_items": 2,
                        "success_items": 2,
                        "failed_items": 0,
                        "details": [
                            {
                                "warehouse_id": "WH01",
                                "product_id": 1,
                                "success": True,
                                "message": "预占成功"
                            },
                            {
                                "warehouse_id": "WH01",
                                "product_id": 2,
                                "success": True,
                                "message": "预占成功"
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def batch_reserve_stock(
    request: BatchReserveRequest = Body(..., description="批量预占请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """批量预占库存接口"""
    try:
        service = InventoryService(db, redis, rlock)
        items = [
            {"warehouse_id": item.warehouse_id, "product_id": item.product_id, "quantity": item.quantity}
            for item in request.items
        ]
        result = service.reserve_batch(order_id=request.order_id, items=items)
        return BatchReserveResponse(
            success=True,
            message="批量预占完成",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量预占失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/release-batch",
    summary="批量释放预占",
    description="""批量释放同一订单的所有预占库存。
    
    **使用场景：**
    - 整单取消
    - 整单退货
    
    **特点：**
    - 一次性释放订单所有商品
    - 批量操作性能优化
    """,
    responses={
        200: {
            "description": "批量释放成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "批量释放成功",
                        "order_id": "ORD202401010001",
                        "released_count": 3
                    }
                }
            }
        }
    }
)
async def batch_release_stock(
    request: BatchReleaseRequest = Body(..., description="批量释放请求"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """批量释放预占库存接口"""
    try:
        service = InventoryService(db, redis, rlock)
        count = service.release_stock(request.order_id)
        return {
            "success": True,
            "message": "批量释放成功",
            "order_id": request.order_id,
            "released_count": count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量释放失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
