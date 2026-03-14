"""库存查询服务 - 纯Redis查询，无数据库回源"""

from typing import List, Dict, Optional, Any
import logging

from app.services.inventory_cache import InventoryCacheService

logger = logging.getLogger(__name__)


class ProductNotFoundError(Exception):
    """商品不存在异常"""
    pass


class InventoryQueryService:
    """库存查询服务 - 纯Redis查询，无数据库回源"""

    def __init__(self, cache_service: InventoryCacheService = None):
        self.cache_service = cache_service

    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（纯Redis，无数据库回源）
        
        直接从Redis获取库存数据，不再查数据库作为回源。
        如果Redis中没有数据，返回0。
        """
        if not self.cache_service:
            logger.error("缓存服务未初始化")
            return 0
        
        # 直接从Redis获取
        stock = self.cache_service.get_cached_stock(warehouse_id, product_id)
        logger.debug(f"查询库存: warehouse={warehouse_id}, product={product_id}, stock={stock}")
        return stock if stock is not None else 0

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（纯Redis，无数据库回源）
        
        直接从Redis获取完整库存数据。
        """
        if not self.cache_service:
            logger.error("缓存服务未初始化")
            return None
        
        # 从 Redis 获取完整信息（使用 MGET 批量读取优化）
        info = self.cache_service.get_cached_full_info_optimized(warehouse_id, product_id)
        
        return info

    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> Dict[int, int]:
        """批量获取库存（纯Redis，无数据库回源）
        
        直接从Redis批量获取所有商品库存。
        未命中的商品返回0，不再查数据库。
        """
        if not product_ids:
            return {}

        if not self.cache_service:
            logger.error("缓存服务未初始化")
            return {pid: 0 for pid in product_ids}

        # 直接从Redis批量获取
        results = self.cache_service.batch_get_cached_stocks(warehouse_id, product_ids)
        
        logger.debug(f"批量查询库存: warehouse={warehouse_id}, count={len(product_ids)}")
        return results