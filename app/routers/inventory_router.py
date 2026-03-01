"""库存管理 API 路由（展示三种调用方式）"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query, Path, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging

from app.core.dependencies import (
    get_db, 
    get_redis, 
    get_redlock, 
    get_inventory_service,
    InventoryServiceDep
)
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import (
    ReserveStockRequest,
    BatchStockQueryRequest,
    CleanupRequest,
    StockResponse,
    BatchStockResponse,
    OperationResponse,
    CleanupResponse,
    CeleryTaskResponse,
    TaskStatusResponse,
    HealthCheckResponse,
    APIInfoResponse
)
from tasks.inventory_tasks import cleanup_expired_reservations as celery_cleanup_task

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/inventory",
    tags=["库存管理"],
    responses={
        400: {"description": "请求参数错误"},
        404: {"description": "资源未找到"},
        422: {"description": "请求验证失败"},
        429: {"description": "请求过于频繁"},
        500: {"description": "服务器内部错误"}
    }
)

@router.post(
    "/reserve",
    response_model=OperationResponse,
    summary="预占库存",
    description="""预占指定商品的库存数量，防止超卖。
    
    **特点：**
    - 使用数据库行级锁确保原子性
    - 支持分布式锁防止并发冲突
    - 15分钟后自动过期
    - 幂等性保证
    
    **使用场景：**
    - 用户下单时预占库存
    - 购物车结算时锁定商品
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
    product_id: int = Query(
        ..., 
        gt=0,
        description="商品ID",
        example=1
    ),
    quantity: int = Query(
        ..., 
        gt=0,
        description="预占数量",
        example=2
    ),
    order_id: str = Query(
        ..., 
        min_length=1,
        max_length=64,
        description="订单ID",
        example="ORD202401010001"
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """预占库存（防超卖核心接口）
    
    通过数据库行级锁和Redis分布式锁双重保护，
    确保在高并发环境下不会出现超卖问题。
    """
    try:
        service = InventoryService(db, redis, rlock)
        result = service.reserve_stock(product_id, quantity, order_id)
        return {"success": True, "message": "预占成功", "data": result}
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"预占库存失败: {str(e)}")
        # 未知异常统一抛 500
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
    - 只能确认状态为RESERVED的预占记录
    - 确认后预占状态变为CONFIRMED
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
        description="订单ID",
        example="ORD202401010001"
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """确认库存扣减（支付成功后调用）
    
    将预占状态的库存正式扣减，
    更新预占记录状态为CONFIRMED。
    """
    try:
        service = InventoryService(db, redis, rlock)
        result = service.confirm_stock(order_id)
        return {"success": True, "message": "确认成功", "data": result}
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"确认库存失败: {str(e)}")
        # 未知异常统一抛 500
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
    - 更新预占状态为RELEASED
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
        description="订单ID",
        example="ORD202401010001"
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """释放预占库存（归还给可用库存）
    
    当订单取消或超时时，
    调用此接口释放之前预占的库存。
    """
    try:
        service = InventoryService(db, redis, rlock)
        result = service.release_stock(order_id)
        return {"success": True, "message": "释放成功", "data": result}
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"释放库存失败: {str(e)}")
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup/manual")
async def manual_cleanup(
    batch_size: int = 500,
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """手动触发清理任务（方式二：API 直接调用 Service）"""
    try:
        service = InventoryService(db, redis, rlock)
        count = service.cleanup_expired_reservations(batch_size)
        db.commit()
        return {
            "success": True, 
            "message": f"手动清理完成", 
            "cleaned_count": count
        }
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"手动清理失败: {str(e)}")
        db.rollback()
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup/celery")
async def celery_cleanup(batch_size: int = 500):
    """触发 Celery 异步清理任务（方式三：Celery 调用）"""
    try:
        # 异步触发 Celery 任务
        task = celery_cleanup_task.delay(batch_size)
        return {
            "success": True,
            "message": "已提交异步清理任务",
            "task_id": task.id
        }
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"Celery 任务提交失败: {str(e)}")
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cleanup/status/{task_id}")
async def get_cleanup_status(task_id: str):
    """查询 Celery 任务执行状态"""
    try:
        from celery_app import app
        task = app.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            status = "任务等待中"
        elif task.state == 'SUCCESS':
            status = f"任务完成: {task.result}"
        elif task.state == 'FAILURE':
            status = f"任务失败: {str(task.info)}"
        else:
            status = f"任务状态: {task.state}"
            
        return {
            "task_id": task_id,
            "status": status,
            "state": task.state
        }
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/stock/{product_id}",
    response_model=StockResponse,
    summary="查询商品库存",
    description="""查询指定商品的可用库存数量。
    
    **缓存策略：**
    - 首先查询Redis缓存
    - 缓存未命中则查询数据库
    - 查询结果缓存5分钟
    
    **性能优化：**
    - 90%+的请求可直接从缓存获取
    - 响应时间通常小于50ms
    """,
    responses={
        200: {
            "description": "查询成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "product_id": 1,
                        "available_stock": 100
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
        description="商品ID",
        example=1
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """查询商品可用库存（带缓存优化）
    
    支持Redis缓存加速，
    提供毫秒级响应性能。
    """
    try:
        service = InventoryService(db, redis, rlock)
        stock = service.get_product_stock(product_id)
        return {
            "success": True,
            "product_id": product_id,
            "available_stock": stock
        }
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"查询库存失败: {str(e)}")
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/stock/batch",
    response_model=BatchStockResponse,
    summary="批量查询商品库存",
    description="""批量查询多个商品的库存数量。
    
    **优势：**
    - 单次请求查询多个商品
    - Redis管道优化批量操作
    - 减少网络往返次数
    
    **限制：**
    - 单次最多查询100个商品
    - 建议按业务场景合理分批
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
    request: BatchStockQueryRequest = Body(
        ..., 
        description="批量查询请求参数"
    ),
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """批量查询商品库存（高性能版本）
    
    使用Redis mget 命令和数据库 in 查询优化，
    支持高并发批量库存查询场景。
    """
    try:
        service = InventoryService(db, redis, rlock)
        stocks = service.batch_get_stocks(request.product_ids)
        return BatchStockResponse(
            success=True,
            data=stocks
        )
    except HTTPException:
        # 透传 HTTPException
        raise
    except Exception as e:
        logger.error(f"批量查询库存失败: {str(e)}")
        # 未知异常统一抛 500
        raise HTTPException(status_code=500, detail=str(e))