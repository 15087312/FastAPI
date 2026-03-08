"""库存操作服务"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Dict, Optional, Any
import logging

from app.models.product_stocks import ProductStock
from app.models.inventory_logs import InventoryLog, ChangeType
from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_query import InventoryQueryService

logger = logging.getLogger(__name__)


class InventoryOperationService:
    """库存操作服务"""

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None,
        rlock: Any = None
    ):
        self.db = db
        self.cache_service = cache_service
        self.rlock = rlock
        self.query_service = InventoryQueryService(db, cache_service)

    def _acquire_lock(self, warehouse_id: str, product_id: int, ttl: int = 10000) -> Any:
        """获取分布式锁"""
        if not self.rlock:
            return None

        lock_key = f"lock:inventory:{warehouse_id}:{product_id}"
        lock = self.rlock.lock(lock_key, ttl=ttl)
        if not lock:
            raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
        return lock

    def _release_lock(self, lock: Any):
        """释放分布式锁"""
        if self.rlock and lock:
            self.rlock.unlock(lock)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)

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
        lock = self._acquire_lock(warehouse_id, product_id)

        try:
            stock = self.query_service._get_or_create_stock(warehouse_id, product_id)

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
            self._release_lock(lock)

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
        lock = self._acquire_lock(warehouse_id, product_id)

        try:
            stock = self.query_service._get_or_create_stock(warehouse_id, product_id)

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
            self._release_lock(lock)

    def freeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """冻结库存"""
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
            self._release_lock(lock)

    def unfreeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """解冻库存"""
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
            self._release_lock(lock)
