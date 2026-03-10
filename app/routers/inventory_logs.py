"""库存流水与清理 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime as dt
from typing import Optional
import logging

from app.core.dependencies import get_db, get_redis
from app.services.inventory_service import InventoryService
from app.schemas.inventory_api import (
    PaginatedLogsResponse,
    InventoryLogDetail,
    CleanupResponse,
    CeleryTaskResponse,
    TaskStatusResponse,
)
from tasks.inventory_tasks import cleanup_expired_reservations as celery_cleanup_task

logger = logging.getLogger(__name__)
router = APIRouter(tags=["库存管理"])


@router.get(
    "/logs",
    response_model=PaginatedLogsResponse,
    summary="查询库存流水",
    description="""查询库存变更流水日志，支持分页和多种筛选条件。
    
    **筛选条件：**
    - warehouse_id: 仓库 ID
    - product_id: 商品 ID
    - order_id: 订单 ID
    - change_type: 变更类型
    - start_date/end_date: 时间范围
    
    **返回字段：**
    - 变更前后库存（可用、预占、冻结）
    - 操作人、来源、备注
    """,
    responses={
        200: {
            "description": "查询成功",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": [
                            {
                                "id": 1,
                                "warehouse_id": "WH01",
                                "product_id": 1,
                                "order_id": "ORD202401010001",
                                "change_type": "RESERVE",
                                "quantity": -2,
                                "before_available": 100,
                                "after_available": 98,
                                "before_reserved": 0,
                                "after_reserved": 2,
                                "before_frozen": 0,
                                "after_frozen": 0,
                                "remark": None,
                                "created_at": "2024-01-01T10:00:00",
                                "operator": "order_service_ORD202401010001",
                                "source": "order_service"
                            }
                        ],
                        "total": 1,
                        "page": 1,
                        "page_size": 50,
                        "total_pages": 1
                    }
                }
            }
        }
    }
)
async def get_inventory_logs(
    warehouse_id: Optional[str] = Query(None, description="仓库 ID"),
    product_id: Optional[int] = Query(None, gt=0, description="商品 ID"),
    order_id: Optional[str] = Query(None, description="订单 ID"),
    change_type: Optional[str] = Query(None, description="变更类型"),
    start_date: Optional[str] = Query(None, description="开始时间 (ISO 格式)"),
    end_date: Optional[str] = Query(None, description="结束时间 (ISO 格式)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    redis = Depends(get_redis)
):
    """查询库存流水日志"""
    try:
        start_dt = dt.fromisoformat(start_date) if start_date else None
        end_dt = dt.fromisoformat(end_date) if end_date else None

        service = InventoryService(db, redis)
        result = service.get_inventory_logs(
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_id=order_id,
            change_type=change_type,
            start_date=start_dt,
            end_date=end_dt,
            page=page,
            page_size=page_size
        )

        logs = [
            InventoryLogDetail(
                id=log.id,
                warehouse_id=log.warehouse_id,
                product_id=log.product_id,
                order_id=log.order_id,
                change_type=log.change_type.value if hasattr(log.change_type, 'value') else log.change_type,
                quantity=log.quantity,
                before_available=log.before_available,
                after_available=log.after_available,
                before_reserved=log.before_reserved,
                after_reserved=log.after_reserved,
                before_frozen=log.before_frozen,
                after_frozen=log.after_frozen,
                remark=log.remark,
                created_at=log.created_at.isoformat() if log.created_at else None,
                operator=log.operator,
                source=log.source
            )
            for log in result["data"]
        ]

        return PaginatedLogsResponse(
            success=True,
            data=logs,
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询库存流水失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup/manual")
async def manual_cleanup(
    batch_size: int = 500,
    db: Session = Depends(get_db),
    redis = Depends(get_redis)
):
    """手动触发清理任务（方式二：API 直接调用 Service）"""
    try:
        service = InventoryService(db, redis)
        count = service.cleanup_expired_reservations(batch_size)
        db.commit()
        return {
            "success": True, 
            "message": f"手动清理完成", 
            "cleaned_count": count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动清理失败：{str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup/celery")
async def celery_cleanup(batch_size: int = 500):
    """触发 Celery 异步清理任务（方式三：Celery 调用）"""
    try:
        task = celery_cleanup_task.delay(batch_size)
        return {
            "success": True,
            "message": "已提交异步清理任务",
            "task_id": task.id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Celery 任务提交失败：{str(e)}")
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
            status = f"任务完成：{task.result}"
        elif task.state == 'FAILURE':
            status = f"任务失败：{str(task.info)}"
        else:
            status = f"任务状态：{task.state}"
            
        return {
            "task_id": task_id,
            "status": status,
            "state": task.state
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
