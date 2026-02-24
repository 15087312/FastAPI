"""库存管理 API 路由（展示三种调用方式）"""

from fastapi import APIRouter, Depends, BackgroundTasks
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
from tasks.inventory_tasks import cleanup_expired_reservations as celery_cleanup_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["库存管理"])

@router.post("/reserve")
async def reserve_stock(
    product_id: int,
    quantity: int,
    order_id: str,
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """API 调用库存预占（方式一：直接调用 Service）"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.reserve_stock(product_id, quantity, order_id)
        return {"success": True, "message": "预占成功", "data": result}
    except Exception as e:
        logger.error(f"预占库存失败: {str(e)}")
        return {"success": False, "message": str(e)}

@router.post("/confirm/{order_id}")
async def confirm_stock(
    order_id: str,
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """API 调用库存确认"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.confirm_stock(order_id)
        return {"success": True, "message": "确认成功", "data": result}
    except Exception as e:
        logger.error(f"确认库存失败: {str(e)}")
        return {"success": False, "message": str(e)}

@router.post("/release/{order_id}")
async def release_stock(
    order_id: str,
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """API 调用库存释放"""
    try:
        service = InventoryService(db, redis, rlock)
        result = service.release_stock(order_id)
        return {"success": True, "message": "释放成功", "data": result}
    except Exception as e:
        logger.error(f"释放库存失败: {str(e)}")
        return {"success": False, "message": str(e)}

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
    except Exception as e:
        logger.error(f"手动清理失败: {str(e)}")
        db.rollback()
        return {"success": False, "message": str(e)}

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
    except Exception as e:
        logger.error(f"Celery 任务提交失败: {str(e)}")
        return {"success": False, "message": str(e)}

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
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return {"success": False, "message": str(e)}

@router.get("/stock/{product_id}")
async def get_stock(
    product_id: int,
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """查询商品库存"""
    try:
        service = InventoryService(db, redis, rlock)
        stock = service.get_product_stock(product_id)
        return {
            "success": True,
            "product_id": product_id,
            "available_stock": stock
        }
    except Exception as e:
        logger.error(f"查询库存失败: {str(e)}")
        return {"success": False, "message": str(e)}

@router.post("/stock/batch")
async def batch_get_stocks(
    product_ids: List[int],
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
):
    """批量查询商品库存"""
    try:
        service = InventoryService(db, redis, rlock)
        stocks = service.batch_get_stocks(product_ids)
        return {
            "success": True,
            "data": stocks
        }
    except Exception as e:
        logger.error(f"批量查询库存失败: {str(e)}")
        return {"success": False, "message": str(e)}