"""库存操作 API 路由（预占、确认、释放）"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
import logging

from app.core.dependencies import get_db, get_redis
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import OperationResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["库存管理"])


@router.post(
    "/reserve",
    response_model=OperationResponse,
    summary="预占库存",
    description="""预占指定商品的库存数量，防止超卖。
    
    **特点：**
    - 使用数据库行级锁确保原子性
    - 支持分布式锁防止并发冲突
    - 15 分钟后自动过期
    - 幂等性保证
    
    **使用场景：**
    - 用户下单时预占库存
    - 购物车结算时锁定商品
    
    **多仓支持：**
    - 需要提供 warehouse_id 参数
    """,
    responses={
        200: {
            "description": "预占成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "预占成功",
                        "data": True
                    }
                }
            }
        },
        400: {
            "description": "库存不足或重复预占",
            "content": {
                "application/json": {
                    "examples": {
                        "insufficient_stock": {
                            "summary": "库存不足",
                            "value": {
                                "success": False,
                                "message": "库存不足"
                            }
                        },
                        "duplicate_reservation": {
                            "summary": "重复预占",
                            "value": {
                                "success": False,
                                "message": "该订单已预占此商品"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def reserve_stock(
    warehouse_id: str = Query(
        ...,
        min_length=1,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    ),
    product_id: int = Query(
        ..., 
        gt=0,
        description="商品 ID",
        examples=[1]
    ),
    quantity: int = Query(
        ..., 
        gt=0,
        description="预占数量",
        examples=[2]
    ),
    order_id: str = Query(
        ..., 
        min_length=1,
        max_length=64,
        description="订单 ID",
        examples=["ORD202401010001"]
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis)
):
    """预占库存（支持多仓库）"""
    try:
        service = InventoryService(db, redis)
        result = service.reserve_stock(warehouse_id, product_id, quantity, order_id)
        return {"success": True, "message": "预占成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预占库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/confirm/{order_id}",
    response_model=OperationResponse,
    summary="确认库存扣减",
    description="""确认预占的库存，实际扣减商品库存。
    
    **使用场景：**
    - 用户支付成功后确认订单
    - 系统自动确认超时订单
    
    **注意：**
    - 只能确认状态为 RESERVED 的预占记录
    - 确认后预占状态变为 CONFIRMED
    """,
    responses={
        200: {
            "description": "确认成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "确认成功",
                        "data": True
                    }
                }
            }
        },
        404: {
            "description": "未找到有效的预占记录",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "未找到有效的预占记录"
                    }
                }
            }
        }
    }
)
async def confirm_stock(
    order_id: str = Path(
        ..., 
        description="订单 ID",
        examples=["ORD202401010001"]
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis)
):
    """确认库存扣减（支付成功后调用）"""
    try:
        service = InventoryService(db, redis)
        result = service.confirm_stock(order_id)
        return {"success": True, "message": "确认成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"确认库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/release/{order_id}",
    response_model=OperationResponse,
    summary="释放预占库存",
    description="""释放预占的库存，归还给可用库存。
    
    **使用场景：**
    - 用户取消订单
    - 订单超时未支付
    - 系统自动释放过期预占
    
    **效果：**
    - 增加可用库存
    - 减少预占库存
    - 更新预占状态为 RELEASED
    """,
    responses={
        200: {
            "description": "释放成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "释放成功",
                        "data": True
                    }
                }
            }
        },
        404: {
            "description": "未找到有效的预占记录",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "未找到有效的预占记录"
                    }
                }
            }
        }
    }
)
async def release_stock(
    order_id: str = Path(
        ..., 
        description="订单 ID",
        examples=["ORD202401010001"]
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis)
):
    """释放预占库存（归还给可用库存）"""
    try:
        service = InventoryService(db, redis)
        result = service.release_stock(order_id)
        return {"success": True, "message": "释放成功", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"释放库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
