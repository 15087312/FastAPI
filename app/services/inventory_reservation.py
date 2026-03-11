"""库存预占服务"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import time
from functools import wraps

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType
from app.services.inventory_cache import InventoryCacheService

logger = logging.getLogger(__name__)

# 性能监控阈值配置（毫秒）
PERFORMANCE_THRESHOLD_WARNING = 50  # 警告阈值
PERFORMANCE_THRESHOLD_CRITICAL = 100  # 严重阈值


def performance_monitor(func):
    """性能监控装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # 记录性能指标
            if elapsed_ms > PERFORMANCE_THRESHOLD_CRITICAL:
                logger.warning(
                    f"[PERF-CRITICAL] {func.__name__} took {elapsed_ms:.2f}ms",
                    extra={
                        'performance_critical': True,
                        'function': func.__name__,
                        'duration_ms': elapsed_ms
                    }
                )
            elif elapsed_ms > PERFORMANCE_THRESHOLD_WARNING:
                logger.info(
                    f"[PERF-WARNING] {func.__name__} took {elapsed_ms:.2f}ms",
                    extra={
                        'performance_warning': True,
                        'function': func.__name__,
                        'duration_ms': elapsed_ms
                    }
                )
            else:
                logger.debug(f"[PERF-OK] {func.__name__} took {elapsed_ms:.2f}ms")
            
            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[PERF-ERROR] {func.__name__} failed after {elapsed_ms:.2f}ms: {str(e)}",
                extra={
                    'performance_error': True,
                    'function': func.__name__,
                    'duration_ms': elapsed_ms,
                    'error': str(e)
                }
            )
            raise
    return wrapper


class InventoryReservationService:
    """库存预占服务
    
    使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
    """

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None
    ):
        self.db = db
        self.cache_service = cache_service

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)

    @performance_monitor
    def reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> bool:
        """预占库存
        
        使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
        优化：先快速检查（不加锁），再开启事务（加锁）
        """
        start_time = time.time()
        
        # 第一阶段：快速检查（不加锁，减少事务持锁时间）
        stock_check = self.db.execute(
            select(ProductStock)
            .where(
                ProductStock.warehouse_id == warehouse_id,
                ProductStock.product_id == product_id
            )
        ).scalar_one_or_none()
        
        if not stock_check:
            raise HTTPException(status_code=404, detail="库存记录不存在")
        
        # 检查重复预占（不加锁）
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
        
        # 第二阶段：加锁并执行实际操作（最小化持锁时间）
        stock = self.db.execute(
            select(ProductStock)
            .where(
                ProductStock.warehouse_id == warehouse_id,
                ProductStock.product_id == product_id
            )
            .with_for_update()
        ).scalar_one()
        
        lock_acquired_time = time.time()
        lock_wait_ms = (lock_acquired_time - start_time) * 1000
        
        if lock_wait_ms > 10:
            logger.warning(
                f"锁等待时间过长：order_id={order_id}, wait={lock_wait_ms:.2f}ms",
                extra={
                    'lock_wait': True,
                    'order_id': order_id,
                    'wait_ms': lock_wait_ms
                }
            )
        
        # 再次检查库存是否足够（在锁保护下）
        if stock.available_stock < quantity:
            raise HTTPException(status_code=400, detail="库存不足")
        
        # 执行扣减操作
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
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"预占库存成功：order_id={order_id}, warehouse={warehouse_id}, product={product_id}, quantity={quantity}, duration={elapsed_ms:.2f}ms",
            extra={
                'operation': 'reserve_stock',
                'order_id': order_id,
                'warehouse_id': warehouse_id,
                'product_id': product_id,
                'quantity': quantity,
                'duration_ms': elapsed_ms
            }
        )

        self._invalidate_cache(warehouse_id, product_id)

        return True

    @performance_monitor
    def reserve_batch(
        self,
        order_id: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量预占库存（事务保证：全部成功或全部回滚）
        
        使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
        """
        start_time = time.time()
        failed_items = []
        success_items = []

        try:
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
            logger.info(f"批量预占成功：order_id={order_id}, count={len(success_items)}")

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

    @performance_monitor
    def confirm_stock(self, order_id: str) -> bool:
        """确认库存（实际扣减）
        
        使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
        """
        start_time = time.time()
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
        logger.info(f"确认库存成功：order_id={order_id}")

        for r in reservations:
            self._invalidate_cache(r.warehouse_id, r.product_id)

        return True

    @performance_monitor
    def release_stock(self, order_id: str) -> bool:
        """释放库存（归还预占）
        
        使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
        """
        start_time = time.time()
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
        logger.info(f"释放库存成功：order_id={order_id}")

        for r in reservations:
            self._invalidate_cache(r.warehouse_id, r.product_id)

        return True