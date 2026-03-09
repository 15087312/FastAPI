"""库存预占服务"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType
from app.services.inventory_cache import InventoryCacheService

logger = logging.getLogger(__name__)


class InventoryReservationService:
    """库存预占服务"""

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None,
        rlock: Any = None
    ):
        self.db = db
        self.cache_service = cache_service
        self.rlock = rlock

    def _acquire_lock(self, warehouse_id: str, product_id: int, ttl: int = 3000, max_retries: int = 3) -> Any:
        """获取分布式锁（带重试机制）"""
        if not self.rlock:
            return None

        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        
        # 重试机制：最多尝试 3 次
        for attempt in range(max_retries):
            lock = self.rlock.lock(lock_key, ttl=ttl)
            if lock:
                return lock
            
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5 * (attempt + 1))  # 递增等待时间
        
        raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

    def _release_lock(self, lock: Any):
        """释放分布式锁"""
        if self.rlock and lock:
            self.rlock.unlock(lock)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)

    def reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> bool:
        """预占库存（带分布式锁）"""
        lock = self._acquire_lock(warehouse_id, product_id)

        try:
            stock = self.db.execute(
                select(ProductStock)
                .where(
                    ProductStock.warehouse_id == warehouse_id,
                    ProductStock.product_id == product_id
                )
                .with_for_update()
            ).scalar_one_or_none()

            if not stock:
                raise HTTPException(status_code=404, detail="库存记录不存在")

            if stock.available_stock < quantity:
                raise HTTPException(status_code=400, detail="库存不足")

            existing_reservation = self.db.execute(
                select(InventoryReservation)
                .where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.warehouse_id == warehouse_id,
                    InventoryReservation.product_id == product_id
                )
            ).scalar_one_or_none()

            if existing_reservation:
                raise HTTPException(status_code=400, detail="该订单已预占此商品")

            stock.available_stock -= quantity
            stock.reserved_stock += quantity

            reservation = InventoryReservation(
                warehouse_id=warehouse_id,
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                status=ReservationStatus.RESERVED,
                expired_at=datetime.utcnow() + timedelta(minutes=15)
            )

            self.db.add(reservation)

            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.RESERVE,
                quantity=-quantity,
                before_available=stock.available_stock + quantity,
                after_available=stock.available_stock,
                before_reserved=stock.reserved_stock - quantity,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                operator=f"order_service_{order_id}",
                source="order_service"
            )
            self.db.add(log)

            self.db.commit()
            logger.info(f"预占库存成功: order_id={order_id}, warehouse={warehouse_id}, product={product_id}, quantity={quantity}")

            self._invalidate_cache(warehouse_id, product_id)

            return True

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"预占库存失败: {str(e)}")
            raise
        finally:
            self._release_lock(lock)

    def reserve_batch(
        self,
        order_id: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量预占库存（事务保证：全部成功或全部回滚）"""
        locks = []
        failed_items = []
        success_items = []

        try:
            if self.rlock:
                for item in items:
                    lock_key = f"lock:inventory:{item['warehouse_id']}:{item['product_id']}"
                    lock = self.rlock.lock(lock_key, ttl=10000)
                    if not lock:
                        raise HTTPException(
                            status_code=429,
                            detail=f"库存操作冲突，请稍后重试: warehouse={item['warehouse_id']}, product={item['product_id']}"
                        )
                    locks.append((lock, item))

            for item in items:
                warehouse_id = item["warehouse_id"]
                product_id = item["product_id"]
                quantity = item["quantity"]

                try:
                    stock = self.db.execute(
                        select(ProductStock)
                        .where(
                            ProductStock.warehouse_id == warehouse_id,
                            ProductStock.product_id == product_id
                        )
                        .with_for_update()
                    ).scalar_one_or_none()

                    if not stock:
                        failed_items.append({
                            "warehouse_id": warehouse_id,
                            "product_id": product_id,
                            "success": False,
                            "message": "库存记录不存在"
                        })
                        continue

                    if stock.available_stock < quantity:
                        failed_items.append({
                            "warehouse_id": warehouse_id,
                            "product_id": product_id,
                            "success": False,
                            "message": "库存不足"
                        })
                        continue

                    existing_reservation = self.db.execute(
                        select(InventoryReservation)
                        .where(
                            InventoryReservation.order_id == order_id,
                            InventoryReservation.warehouse_id == warehouse_id,
                            InventoryReservation.product_id == product_id
                        )
                    ).scalar_one_or_none()

                    if existing_reservation:
                        failed_items.append({
                            "warehouse_id": warehouse_id,
                            "product_id": product_id,
                            "success": False,
                            "message": "该订单已预占此商品"
                        })
                        continue

                    stock.available_stock -= quantity
                    stock.reserved_stock += quantity

                    reservation = InventoryReservation(
                        warehouse_id=warehouse_id,
                        order_id=order_id,
                        product_id=product_id,
                        quantity=quantity,
                        status=ReservationStatus.RESERVED,
                        expired_at=datetime.utcnow() + timedelta(minutes=15)
                    )
                    self.db.add(reservation)

                    log = InventoryLog(
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        order_id=order_id,
                        change_type=ChangeType.BATCH_RESERVE,
                        quantity=-quantity,
                        before_available=stock.available_stock + quantity,
                        after_available=stock.available_stock,
                        before_reserved=stock.reserved_stock - quantity,
                        after_reserved=stock.reserved_stock,
                        before_frozen=stock.frozen_stock,
                        after_frozen=stock.frozen_stock,
                        operator=f"order_service_{order_id}",
                        source="order_service"
                    )
                    self.db.add(log)

                    success_items.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "success": True,
                        "message": "预占成功"
                    })

                except Exception as e:
                    failed_items.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "success": False,
                        "message": str(e)
                    })

            if failed_items and success_items:
                raise HTTPException(
                    status_code=400,
                    detail="部分商品预占失败，已回滚",
                )

            if failed_items:
                raise HTTPException(
                    status_code=400,
                    detail="所有商品预占失败",
                )

            self.db.commit()
            logger.info(f"批量预占成功: order_id={order_id}, count={len(success_items)}")

            for item in items:
                self._invalidate_cache(item["warehouse_id"], item["product_id"])

            return {
                "order_id": order_id,
                "total_items": len(items),
                "success_items": len(success_items),
                "failed_items": len(failed_items),
                "details": success_items
            }

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量预占失败: {str(e)}")
            raise
        finally:
            if self.rlock and locks:
                for lock, _ in locks:
                    self.rlock.unlock(lock)

    def confirm_stock(self, order_id: str) -> bool:
        """确认库存（实际扣减，带分布式锁）"""
        reservations_check = self.db.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.RESERVED
            )
        ).scalars().all()

        locks = []

        if self.rlock and reservations_check:
            for r in reservations_check:
                lock_key = f"lock:inventory:{r.warehouse_id}:{r.product_id}"
                lock = self.rlock.lock(lock_key, ttl=10000)
                if not lock:
                    raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
                locks.append((lock, r.warehouse_id, r.product_id))

        try:
            reservations = self.db.execute(
                select(InventoryReservation)
                .where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.status == ReservationStatus.RESERVED
                )
            ).scalars().all()

            if not reservations:
                raise HTTPException(status_code=404, detail="未找到有效的预占记录")

            for reservation in reservations:
                product_stock = self.db.execute(
                    select(ProductStock)
                    .where(
                        ProductStock.warehouse_id == reservation.warehouse_id,
                        ProductStock.product_id == reservation.product_id
                    )
                    .with_for_update()
                ).scalar_one()

                product_stock.reserved_stock -= reservation.quantity

                reservation.status = ReservationStatus.CONFIRMED

                log = InventoryLog(
                    warehouse_id=reservation.warehouse_id,
                    product_id=reservation.product_id,
                    order_id=order_id,
                    change_type=ChangeType.CONFIRM,
                    quantity=0,
                    before_available=product_stock.available_stock,
                    after_available=product_stock.available_stock,
                    before_reserved=product_stock.reserved_stock + reservation.quantity,
                    after_reserved=product_stock.reserved_stock,
                    before_frozen=product_stock.frozen_stock,
                    after_frozen=product_stock.frozen_stock,
                    operator=f"order_service_{order_id}",
                    source="order_service"
                )
                self.db.add(log)

            self.db.commit()
            logger.info(f"确认库存成功: order_id={order_id}")

            for r in reservations:
                self._invalidate_cache(r.warehouse_id, r.product_id)

            return True

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"确认库存失败: {str(e)}")
            raise
        finally:
            if self.rlock and locks:
                for lock, _, _ in locks:
                    self.rlock.unlock(lock)

    def release_stock(self, order_id: str) -> bool:
        """释放库存（归还预占，带分布式锁）"""
        reservations_check = self.db.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.RESERVED
            )
        ).scalars().all()

        locks = []

        if self.rlock and reservations_check:
            for r in reservations_check:
                lock_key = f"lock:inventory:{r.warehouse_id}:{r.product_id}"
                lock = self.rlock.lock(lock_key, ttl=10000)
                if not lock:
                    raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
                locks.append((lock, r.warehouse_id, r.product_id))

        try:
            reservations = self.db.execute(
                select(InventoryReservation)
                .where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.status == ReservationStatus.RESERVED
                )
            ).scalars().all()

            if not reservations:
                raise HTTPException(status_code=404, detail="未找到有效的预占记录")

            for reservation in reservations:
                product_stock = self.db.execute(
                    select(ProductStock)
                    .where(
                        ProductStock.warehouse_id == reservation.warehouse_id,
                        ProductStock.product_id == reservation.product_id
                    )
                    .with_for_update()
                ).scalar_one()

                product_stock.available_stock += reservation.quantity
                product_stock.reserved_stock -= reservation.quantity

                reservation.status = ReservationStatus.RELEASED

                log = InventoryLog(
                    warehouse_id=reservation.warehouse_id,
                    product_id=reservation.product_id,
                    order_id=order_id,
                    change_type=ChangeType.RELEASE,
                    quantity=reservation.quantity,
                    before_available=product_stock.available_stock - reservation.quantity,
                    after_available=product_stock.available_stock,
                    before_reserved=product_stock.reserved_stock + reservation.quantity,
                    after_reserved=product_stock.reserved_stock,
                    before_frozen=product_stock.frozen_stock,
                    after_frozen=product_stock.frozen_stock,
                    operator=f"order_service_{order_id}",
                    source="order_service"
                )
                self.db.add(log)

            self.db.commit()
            logger.info(f"释放库存成功: order_id={order_id}")

            for r in reservations:
                self._invalidate_cache(r.warehouse_id, r.product_id)

            return True

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"释放库存失败: {str(e)}")
            raise
        finally:
            if self.rlock and locks:
                for lock, _, _ in locks:
                    self.rlock.unlock(lock)
