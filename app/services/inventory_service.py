"""库存服务实现"""

from fastapi import Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging
from redis import Redis
from redlock import Redlock

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType

logger = logging.getLogger(__name__)


class InventoryService:
    """库存核心服务类"""

    def __init__(self, db: Session, redis: Redis = None, rlock: Redlock = None):
        self.db = db
        self.redis = redis
        self.rlock = rlock

    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return f"stock:available:{warehouse_id}:{product_id}"

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效库存缓存"""
        if self.redis:
            self.redis.delete(self._get_cache_key(warehouse_id, product_id))
            logger.debug(f"Cache invalidated for warehouse {warehouse_id}, product {product_id}")

    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（带缓存）"""
        cache_key = self._get_cache_key(warehouse_id, product_id)

        if self.redis:
            cached = self.redis.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for warehouse {warehouse_id}, product {product_id}")
                return int(cached)

        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()
        available = stock.available_stock if stock else 0

        if self.redis:
            self.redis.setex(cache_key, 300, available)
            logger.debug(f"Cache set for warehouse {warehouse_id}, product {product_id}: {available}")

        return available

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息"""
        cache_key = f"stock:full:{warehouse_id}:{product_id}"

        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                import json
                return json.loads(cached)

        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()

        if not stock:
            return None

        info = {
            "warehouse_id": stock.warehouse_id,
            "product_id": stock.product_id,
            "available_stock": stock.available_stock,
            "reserved_stock": stock.reserved_stock,
            "frozen_stock": stock.frozen_stock,
            "in_transit_stock": stock.in_transit_stock,
            "safety_stock": stock.safety_stock,
            "total_stock": (
                stock.available_stock + stock.reserved_stock +
                stock.frozen_stock + stock.in_transit_stock
            )
        }

        if self.redis:
            import json
            self.redis.setex(cache_key, 300, json.dumps(info))
            logger.debug(f"Full stock cache set for warehouse {warehouse_id}, product {product_id}")

        return info

    def _get_or_create_stock(self, warehouse_id: str, product_id: int) -> ProductStock:
        """获取或创建库存记录"""
        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()

        if not stock:
            stock = ProductStock(
                warehouse_id=warehouse_id,
                product_id=product_id,
                available_stock=0,
                reserved_stock=0,
                frozen_stock=0,
                in_transit_stock=0,
                safety_stock=0
            )
            self.db.add(stock)
            self.db.flush()
            logger.info(f"Created new stock record: warehouse={warehouse_id}, product={product_id}")

        return stock

    def increase_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: Optional[str] = None,
        operator: Optional[str] = None,
        remark: Optional[str] = None,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """入库/补货"""
        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = None

        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

        try:
            stock = self._get_or_create_stock(warehouse_id, product_id)

            before_available = stock.available_stock
            stock.available_stock += quantity

            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.INCREASE,
                quantity=quantity,
                before_available=before_available,
                after_available=stock.available_stock,
                before_reserved=stock.reserved_stock,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                remark=remark,
                operator=operator or "system",
                source=source
            )
            self.db.add(log)

            self.db.commit()
            logger.info(f"入库成功: warehouse={warehouse_id}, product={product_id}, quantity={quantity}")

            self._invalidate_cache(warehouse_id, product_id)

            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_stock": before_available,
                "after_stock": stock.available_stock,
                "quantity": quantity
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"入库失败: {str(e)}")
            raise
        finally:
            if self.rlock and lock:
                self.rlock.unlock(lock)

    def adjust_stock(
        self,
        warehouse_id: str,
        product_id: int,
        adjust_type: str,
        quantity: int,
        reason: str,
        operator: Optional[str] = None,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """库存调整（增加/减少/设置）"""
        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = None

        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

        try:
            stock = self._get_or_create_stock(warehouse_id, product_id)

            before_available = stock.available_stock

            if adjust_type == "increase":
                stock.available_stock += quantity
                change_qty = quantity
            elif adjust_type == "decrease":
                if stock.available_stock < quantity:
                    raise HTTPException(status_code=400, detail="库存不足，无法减少")
                stock.available_stock -= quantity
                change_qty = -quantity
            elif adjust_type == "set":
                diff = quantity - stock.available_stock
                stock.available_stock = quantity
                change_qty = diff
            else:
                raise HTTPException(status_code=400, detail="无效的调整类型")

            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=None,
                change_type=ChangeType.ADJUST,
                quantity=change_qty,
                before_available=before_available,
                after_available=stock.available_stock,
                before_reserved=stock.reserved_stock,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                remark=reason,
                operator=operator or "system",
                source=source
            )
            self.db.add(log)

            self.db.commit()
            logger.info(f"库存调整成功: warehouse={warehouse_id}, product={product_id}, type={adjust_type}, quantity={quantity}")

            self._invalidate_cache(warehouse_id, product_id)

            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_available": before_available,
                "after_available": stock.available_stock,
                "adjust_type": adjust_type,
                "quantity": quantity
            }

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"库存调整失败: {str(e)}")
            raise
        finally:
            if self.rlock and lock:
                self.rlock.unlock(lock)

    def freeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """冻结库存"""
        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = None

        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

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
                raise HTTPException(status_code=400, detail="可用库存不足，无法冻结")

            before_frozen = stock.frozen_stock
            stock.available_stock -= quantity
            stock.frozen_stock += quantity

            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=None,
                change_type=ChangeType.FREEZE,
                quantity=-quantity,
                before_available=stock.available_stock + quantity,
                after_available=stock.available_stock,
                before_reserved=stock.reserved_stock,
                after_reserved=stock.reserved_stock,
                before_frozen=before_frozen,
                after_frozen=stock.frozen_stock,
                remark=reason,
                operator=operator or "system",
                source="manual"
            )
            self.db.add(log)

            self.db.commit()
            logger.info(f"冻结库存成功: warehouse={warehouse_id}, product={product_id}, quantity={quantity}")

            self._invalidate_cache(warehouse_id, product_id)

            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_frozen": before_frozen,
                "after_frozen": stock.frozen_stock
            }

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"冻结库存失败: {str(e)}")
            raise
        finally:
            if self.rlock and lock:
                self.rlock.unlock(lock)

    def unfreeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """解冻库存"""
        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = None

        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

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

            if stock.frozen_stock < quantity:
                raise HTTPException(status_code=400, detail="冻结库存不足，无法解冻")

            before_frozen = stock.frozen_stock
            stock.frozen_stock -= quantity
            stock.available_stock += quantity

            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=None,
                change_type=ChangeType.UNFREEZE,
                quantity=quantity,
                before_available=stock.available_stock - quantity,
                after_available=stock.available_stock,
                before_reserved=stock.reserved_stock,
                after_reserved=stock.reserved_stock,
                before_frozen=before_frozen,
                after_frozen=stock.frozen_stock,
                remark=reason,
                operator=operator or "system",
                source="manual"
            )
            self.db.add(log)

            self.db.commit()
            logger.info(f"解冻库存成功: warehouse={warehouse_id}, product={product_id}, quantity={quantity}")

            self._invalidate_cache(warehouse_id, product_id)

            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_frozen": before_frozen,
                "after_frozen": stock.frozen_stock
            }

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"解冻库存失败: {str(e)}")
            raise
        finally:
            if self.rlock and lock:
                self.rlock.unlock(lock)
    
    def reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> bool:
        """预占库存（带分布式锁）"""
        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = None

        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")

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
            if self.rlock and lock:
                self.rlock.unlock(lock)

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
    
    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> dict:
        """批量获取库存（带缓存优化）"""
        if not product_ids:
            return {}

        results = {}
        uncached_ids = []

        if self.redis:
            cache_keys = [self._get_cache_key(warehouse_id, pid) for pid in product_ids]
            cached_values = self.redis.mget(cache_keys)

            for i, (pid, cached) in enumerate(zip(product_ids, cached_values)):
                if cached is not None:
                    results[pid] = int(cached)
                    logger.debug(f"Batch cache hit for warehouse {warehouse_id}, product {pid}")
                else:
                    uncached_ids.append(pid)
        else:
            uncached_ids = product_ids

        if uncached_ids:
            stmt = select(ProductStock).where(
                ProductStock.warehouse_id == warehouse_id,
                ProductStock.product_id.in_(uncached_ids)
            )
            result = self.db.execute(stmt)
            stocks = result.scalars().all()

            stock_map = {stock.product_id: stock.available_stock for stock in stocks}

            if self.redis:
                pipe = self.redis.pipeline()

            for pid in uncached_ids:
                available = stock_map.get(pid, 0)
                results[pid] = available

                if self.redis:
                    pipe.setex(self._get_cache_key(warehouse_id, pid), 300, available)
                    logger.debug(f"Batch cache set for warehouse {warehouse_id}, product {pid}: {available}")

            if self.redis:
                pipe.execute()

        return results

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



