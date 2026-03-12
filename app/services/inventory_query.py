"""库存查询服务"""

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any

from app.models.product_stocks import ProductStock
from app.services.inventory_cache import InventoryCacheService
from app.services.bloom_filter import product_bloom_filter


class ProductNotFoundError(Exception):
    """商品不存在异常"""
    pass


class InventoryQueryService:
    """库存查询服务"""

    def __init__(self, db: Session, cache_service: InventoryCacheService = None):
        self.db = db
        self.cache_service = cache_service

    def _check_product_exists(self, product_id: int) -> bool:
        """检查商品是否存在于布隆过滤器中
        
        Returns:
            True: 可能存在
            False: 一定不存在
        """
        # 如果布隆过滤器已初始化，则检查
        if product_bloom_filter.is_initialized():
            return product_bloom_filter.contains(product_id)
        # 如果未初始化，放行让请求查数据库
        return True

    def get_product_stock(self, warehouse_id: str, product_id: int) -> Optional[int]:
        """查询商品可用库存（带缓存，防穿透，布隆过滤器）"""
        # 先检查布隆过滤器
        if not self._check_product_exists(product_id):
            # 布隆过滤器判断商品一定不存在，直接返回
            return None

        # 先检查缓存
        if self.cache_service:
            cached = self.cache_service.get_cached_stock(warehouse_id, product_id)
            if cached is not None:
                # 命中：无论有值还是空值标记，都直接返回
                # 有值返回实际数量，空值标记返回 None
                return cached

        # 缓存未命中，查询数据库
        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()

        if stock:
            available = stock.available_stock
        else:
            # 数据库中不存在该商品，记录空值缓存（60秒后重试）
            available = None

        if self.cache_service:
            self.cache_service.set_cached_stock(warehouse_id, product_id, available)

        return available if available is not None else 0

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（防穿透，布隆过滤器）"""
        # 先检查布隆过滤器
        if not self._check_product_exists(product_id):
            # 布隆过滤器判断商品一定不存在
            return None

        # 先检查缓存
        if self.cache_service:
            cached = self.cache_service.get_cached_full_info(warehouse_id, product_id)
            if cached is not None:
                # 命中缓存，返回缓存数据
                return cached

        # 缓存未命中，查询数据库
        stmt = select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()

        if not stock:
            # 数据库中不存在该商品，记录空值缓存
            if self.cache_service:
                self.cache_service.set_cached_full_info(warehouse_id, product_id, None)
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
        """批量获取库存（带缓存优化，布隆过滤器）"""
        if not product_ids:
            return {}

        # 布隆过滤器过滤：移除一定不存在的商品 ID
        valid_product_ids = []
        invalid_product_ids = []
        
        if product_bloom_filter.is_initialized():
            for pid in product_ids:
                if product_bloom_filter.contains(pid):
                    valid_product_ids.append(pid)
                else:
                    invalid_product_ids.append(pid)
            # 不存在的商品返回 0
            results = {pid: None for pid in invalid_product_ids}
        else:
            valid_product_ids = product_ids
            results = {}

        if not valid_product_ids:
            return results

        uncached_ids = valid_product_ids

        if self.cache_service:
            cached_results, uncached_ids = self.cache_service.batch_get_cached_stocks(warehouse_id, valid_product_ids)
            results.update(cached_results)

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
