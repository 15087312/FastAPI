"""库存查询 API 路由 - 纯 Redis 查询，零数据库访问"""

from fastapi import APIRouter, HTTPException, Query, Body, Path, Depends
import logging

from app.core.dependencies import get_redis
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import (
    StockResponse,
    BatchStockResponse,
    BatchStockQueryRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["库存管理"])


@router.get(
    "/stock/{product_id}",
    response_model=StockResponse,
    summary="查询商品库存",
    description="""查询指定商品的库存信息。
    
    **缓存策略：**
    - 首先查询本地内存缓存（零延迟）
    - 未命中则查询 Redis
    - 再未命中查询数据库并回写缓存
    - 查询结果缓存 5 分钟
    
    **多仓支持：**
    - 需要提供 warehouse_id 参数
    - 返回完整库存信息（可用、预占、冻结、安全库存）
    """,
    responses={
        200: {
            "description": "查询成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "warehouse_id": "WH01",
                        "product_id": 1,
                        "available_stock": 100,
                        "reserved_stock": 10,
                        "frozen_stock": 5,
                        "safety_stock": 10,
                        "total_stock": 115
                    }
                }
            }
        }
    }
)
async def get_stock(
    product_id: int = Path(
        ..., 
        gt=0,
        description="商品 ID",
        examples=[1]
    ),
    warehouse_id: str | None = Query(
        default=None,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    ),
    redis = Depends(get_redis)
):
    """查询商品库存（支持多仓库）- 纯 Redis 查询"""
    # 如果未提供 warehouse_id，使用默认值
    if not warehouse_id:
        warehouse_id = "WH01"
    
    try:
        service = InventoryService(redis)
        stock_info = service.get_full_stock_info(warehouse_id, product_id)
        if not stock_info:
            return StockResponse(
                success=True,
                warehouse_id=warehouse_id,
                product_id=product_id,
                available_stock=0,
                reserved_stock=0,
                frozen_stock=0,
                safety_stock=0,
                total_stock=0
            )
        return StockResponse(
            success=True,
            **stock_info
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/stock/batch",
    response_model=BatchStockResponse,
    summary="批量查询商品库存",
    description="""批量查询多个商品的库存数量。
    
    **优势：**
    - 单次请求查询多个商品
    - Redis 管道优化批量操作
    - 减少网络往返次数
    
    **限制：**
    - 单次最多查询 100 个商品
    - 建议按业务场景合理分批
    
    **多仓支持：**
    - 需要提供 warehouse_id 参数
    """,
    responses={
        200: {
            "description": "批量查询成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "1": 100,
                            "2": 50,
                            "3": 0
                        }
                    }
                }
            }
        }
    }
)
async def batch_get_stocks(
    warehouse_id: str | None = Query(
        default=None,
        max_length=32,
        description="仓库 ID",
        examples=["WH01"]
    ),
    request: BatchStockQueryRequest = Body(
        ..., 
        description="批量查询请求参数"
    ),
    redis = Depends(get_redis)
):
    """批量查询商品库存（支持多仓库）- 纯 Redis 查询"""
    # 如果未提供 warehouse_id，使用默认值
    if not warehouse_id:
        warehouse_id = "WH01"
    
    try:
        service = InventoryService(None, redis)
        stocks = service.batch_get_stocks(warehouse_id, request.product_ids)
        return BatchStockResponse(
            success=True,
            data=stocks
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量查询库存失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
