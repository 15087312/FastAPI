"""库存缓存服务"""

from typing import Optional
import logging
from redis import Redis

logger = logging.getLogger(__name__)


class InventoryCacheService:
    """库存缓存服务"""

    def __init__(self, redis: Redis = None):
        self.redis = redis

    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return f"stock:available:{warehouse_id}:{product_id}"

    def _get_full_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成完整库存信息缓存键"""
        return f"stock:full:{warehouse_id}:{product_id}"

    def get_cached_stock(self, warehouse_id: str, product_id: int) -> Optional[int]:
        """获取缓存的可用库存"""
        if not self.redis:
            return None

        cache_key = self._get_cache_key(warehouse_id, product_id)
        cached = self.redis.get(cache_key)

        if cached is not None:
            logger.debug(f"Cache hit for warehouse {warehouse_id}, product {product_id}")
            return int(cached)

        return None

    def set_cached_stock(self, warehouse_id: str, product_id: int, available: int, ttl: int = 300):
        """设置缓存的可用库存"""
        if not self.redis:
            return

        cache_key = self._get_cache_key(warehouse_id, product_id)
        self.redis.setex(cache_key, ttl, available)
        logger.debug(f"Cache set for warehouse {warehouse_id}, product {product_id}: {available}")

    def get_cached_full_info(self, warehouse_id: str, product_id: int) -> Optional[dict]:
        """获取缓存的完整库存信息"""
        if not self.redis:
            return None

        import json
        cache_key = self._get_full_cache_key(warehouse_id, product_id)
        cached = self.redis.get(cache_key)

        if cached:
            return json.loads(cached)

        return None

    def set_cached_full_info(self, warehouse_id: str, product_id: int, info: dict, ttl: int = 300):
        """设置缓存的完整库存信息"""
        if not self.redis:
            return

        import json
        cache_key = self._get_full_cache_key(warehouse_id, product_id)
        self.redis.setex(cache_key, ttl, json.dumps(info))
        logger.debug(f"Full stock cache set for warehouse {warehouse_id}, product {product_id}")

    def invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效库存缓存"""
        if self.redis:
            self.redis.delete(self._get_cache_key(warehouse_id, product_id))
            logger.debug(f"Cache invalidated for warehouse {warehouse_id}, product {product_id}")

    def invalidate_caches(self, items: list):
        """批量失效缓存"""
        if not self.redis:
            return

        keys_to_delete = []
        for item in items:
            warehouse_id = item.get("warehouse_id")
            product_id = item.get("product_id")
            if warehouse_id and product_id:
                keys_to_delete.append(self._get_cache_key(warehouse_id, product_id))

        if keys_to_delete:
            self.redis.delete(*keys_to_delete)
            logger.debug(f"Batch cache invalidated: {len(keys_to_delete)} keys")

    def batch_get_cached_stocks(self, warehouse_id: str, product_ids: list) -> tuple:
        """批量获取缓存的库存，返回(命中的结果, 未命中的product_ids)"""
        if not self.redis or not product_ids:
            return {}, product_ids

        cache_keys = [self._get_cache_key(warehouse_id, pid) for pid in product_ids]
        cached_values = self.redis.mget(cache_keys)

        results = {}
        uncached_ids = []

        for pid, cached in zip(product_ids, cached_values):
            if cached is not None:
                results[pid] = int(cached)
                logger.debug(f"Batch cache hit for warehouse {warehouse_id}, product {pid}")
            else:
                uncached_ids.append(pid)

        return results, uncached_ids

    def batch_set_cached_stocks(self, warehouse_id: str, stock_map: dict, ttl: int = 300):
        """批量设置缓存的库存"""
        if not self.redis or not stock_map:
            return

        pipe = self.redis.pipeline()

        for product_id, available in stock_map.items():
            pipe.set(self._get_cache_key(warehouse_id, product_id), available, ex=ttl)
            logger.debug(f"Batch cache set for warehouse {warehouse_id}, product {product_id}: {available}")

        pipe.execute()
