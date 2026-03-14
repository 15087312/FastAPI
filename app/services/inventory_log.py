"""库存日志服务"""

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from typing import Dict, Optional, Any
from datetime import datetime
import logging

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType
from app.services.inventory_cache import InventoryCacheService
from app.core.aspects import (
    CacheInvalidationAspect,
    LoggingAspect
)

logger = logging.getLogger(__name__)


class InventoryLogService:
    """库存日志服务
    
    Redis 是主库存，数据库只做对账和审计。
    """

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None
    ):
        self.db = db
        self.cache_service = cache_service
        # 使用统一的缓存失效切面
        self.cache_aspect = CacheInvalidationAspect(cache_service)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存（使用统一切面）"""
        self.cache_aspect.invalidate_single(warehouse_id, product_id)

    def get_inventory_logs(
        self,
        warehouse_id: Optional[str] = None,
        product_id: Optional[int] = None,
        order_id: Optional[str] = None,
        change_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """查询库存流水日志（支持分页）"""
        stmt = select(InventoryLog)

        if warehouse_id:
            stmt = stmt.where(InventoryLog.warehouse_id == warehouse_id)
        if product_id:
            stmt = stmt.where(InventoryLog.product_id == product_id)
        if order_id:
            stmt = stmt.where(InventoryLog.order_id == order_id)
        if change_type:
            stmt = stmt.where(InventoryLog.change_type == change_type)
        if start_date:
            stmt = stmt.where(InventoryLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(InventoryLog.created_at <= end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar()

        stmt = stmt.order_by(InventoryLog.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = self.db.execute(stmt)
        logs = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "data": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }

    def cleanup_expired_reservations(self, batch_size: int = 500) -> int:
        """清理过期的库存预占记录（对账操作）
        
        注意：Redis 是主库存，数据库只做对账和审计。
        此方法仅用于修复 Redis 和数据库的不一致。
        """
        total_cleaned = 0

        while True:
            try:
                # 查询过期预占记录（不带锁，直接读取）
                expired_reservations = self.db.execute(
                    select(InventoryReservation)
                    .where(
                        InventoryReservation.status == ReservationStatus.RESERVED,
                        InventoryReservation.expired_at <= datetime.utcnow()
                    )
                    .limit(batch_size)
                ).scalars().all()

                if not expired_reservations:
                    break

                logger.info(f"发现 {len(expired_reservations)} 条过期预占记录")
                
                for reservation in expired_reservations:
                    try:
                        # 检查 Redis 中是否已释放（以 Redis 为准）
                        if self.cache_service:
                            reservation_set = self.cache_service.redis.smembers(
                                f'reservation:{reservation.warehouse_id}:{reservation.product_id}'
                            )
                            if reservation.order_id not in reservation_set:
                                # Redis 中已释放，更新数据库状态
                                reservation.status = ReservationStatus.RELEASED
                                logger.debug(f"Redis 已释放，同步数据库：{reservation.order_id}")
                                continue
                        
                        # 如果 Redis 中还存在，说明需要释放
                        # 获取库存记录（不带锁）
                        product_stock = self.db.execute(
                            select(ProductStock)
                            .where(
                                ProductStock.warehouse_id == reservation.warehouse_id,
                                ProductStock.product_id == reservation.product_id
                            )
                        ).scalar_one_or_none()
                
                        if product_stock:
                            # 归还库存
                            product_stock.available_stock += reservation.quantity
                            product_stock.reserved_stock -= reservation.quantity
                        
                            # 更新预占状态
                            reservation.status = ReservationStatus.RELEASED
                        
                            # 记录日志
                            if product_stock:
                                log = InventoryLog(
                                    warehouse_id=reservation.warehouse_id,
                                    product_id=reservation.product_id,
                                    order_id=reservation.order_id,
                                    change_type=ChangeType.RELEASE,
                                    quantity=reservation.quantity,
                                    before_available=product_stock.available_stock - reservation.quantity,
                                    after_available=product_stock.available_stock,
                                    before_reserved=product_stock.reserved_stock + reservation.quantity,
                                    after_reserved=product_stock.reserved_stock,
                                    before_frozen=product_stock.frozen_stock,
                                    after_frozen=product_stock.frozen_stock,
                                    operator="system_cleanup",
                                    source="cleanup_job"
                                )
                                self.db.add(log)
                        
                        total_cleaned += 1
                
                    except Exception as e:
                        logger.error(f"清理单条预占记录失败：order_id={reservation.order_id}, error={str(e)}")
                        continue
                
                self.db.commit()
                
                logger.info(f"已完成批次清理，累计清理 {total_cleaned} 条记录")

                if len(expired_reservations) < batch_size:
                    break
        
            except Exception as e:
                logger.error(f"批处理清理过程中发生错误：{str(e)}")
                self.db.rollback()
                break
        
        LoggingAspect.log_operation_success("cleanup_expired_reservations", extra_data={'total_cleaned': total_cleaned})

        return total_cleaned