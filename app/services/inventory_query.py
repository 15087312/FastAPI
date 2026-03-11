"""库存查询服务"""

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any

from app.models.product_stocks import ProductStock
from app.services.inventory_cache import InventoryCacheService


class InventoryQueryService:
    """库存查询服务"""

    def __init__(self, db: Session, cache_service: InventoryCacheService = None):
        self.db = db
        self.cache_service = cache_service

    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（带缓存）"""
        if self.cache_service:
            cached = self.cache_service.get_cached_stock(warehouse_id, product_id)
            if cached is not None:
                return cached

        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()
        available = stock.available_stock if stock else 0

        if self.cache_service:
            self.cache_service.set_cached_stock(warehouse_id, product_id, available)

        return available

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息"""
        if self.cache_service:
            cached = self.cache_service.get_cached_full_info(warehouse_id, product_id)
            if cached:
                return cached

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
            "safety_stock": stock.safety_stock,
            "total_stock": (
                stock.available_stock + stock.reserved_stock +
                stock.frozen_stock
            )
        }

        if self.cache_service:
            self.cache_service.set_cached_full_info(warehouse_id, product_id, info)

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
                safety_stock=0
            )
            self.db.add(stock)
            self.db.flush()

        return stock

    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> dict:
        """批量获取库存（带缓存优化）"""
        if not product_ids:
            return {}

        results = {}
        uncached_ids = product_ids

        if self.cache_service:
            results, uncached_ids = self.cache_service.batch_get_cached_stocks(warehouse_id, product_ids)

        if uncached_ids:
            stmt = select(ProductStock).where(
                ProductStock.warehouse_id == warehouse_id,
                ProductStock.product_id.in_(uncached_ids)
            )
            result = self.db.execute(stmt)
            stocks = result.scalars().all()

            stock_map = {stock.product_id: stock.available_stock for stock in stocks}

            for pid in uncached_ids:
                available = stock_map.get(pid, 0)
                results[pid] = available

            if self.cache_service:
                self.cache_service.batch_set_cached_stocks(warehouse_id, stock_map)

        return results
