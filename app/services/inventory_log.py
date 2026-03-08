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

logger = logging.getLogger(__name__)


class InventoryLogService:
    """库存日志服务"""

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None,
        rlock: Any = None
    ):
        self.db = db
        self.cache_service = cache_service
        self.rlock = rlock

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)

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
        """清理过期的库存预占记录（企业级实现）"""
        total_cleaned = 0

        while True:
            try:
                expired_reservations = self.db.execute(
                    select(InventoryReservation)
                    .where(
                        InventoryReservation.status == ReservationStatus.RESERVED,
                        InventoryReservation.expired_at <= datetime.utcnow()
                    )
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                ).scalars().all()

                if not expired_reservations:
                    break

                logger.info(f"本次清理 {len(expired_reservations)} 条过期预占记录")

                locks = []
                if self.rlock:
                    for r in expired_reservations:
                        lock_key = f"lock:inventory:{r.warehouse_id}:{r.product_id}"
                        lock = self.rlock.lock(lock_key, ttl=5000)
                        if lock:
                            locks.append((lock, r.warehouse_id, r.product_id))

                try:
                    for reservation in expired_reservations:
                        try:
                            product_stock = self.db.execute(
                                select(ProductStock)
                                .where(
                                    ProductStock.warehouse_id == reservation.warehouse_id,
                                    ProductStock.product_id == reservation.product_id
                                )
                                .with_for_update()
                            ).scalar_one_or_none()

                            if product_stock:
                                product_stock.available_stock += reservation.quantity
                                product_stock.reserved_stock -= reservation.quantity

                            reservation.status = ReservationStatus.RELEASED

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
                            logger.error(f"清理单条预占记录失败: order_id={reservation.order_id}, error={str(e)}")
                            continue

                    self.db.commit()

                    for r in expired_reservations:
                        self._invalidate_cache(r.warehouse_id, r.product_id)

                    logger.info(f"已完成批次清理，累计清理 {total_cleaned} 条记录")

                    if len(expired_reservations) < batch_size:
                        break

                finally:
                    if self.rlock and locks:
                        for lock, _, _ in locks:
                            self.rlock.unlock(lock)

            except Exception as e:
                logger.error(f"批处理清理过程中发生错误: {str(e)}")
                self.db.rollback()
                break

        logger.info(f"清理任务完成，总共清理 {total_cleaned} 条过期预占记录")

        return total_cleaned
