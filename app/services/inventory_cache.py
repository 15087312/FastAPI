"""库存缓存服务"""

from typing import Optional
import logging
from redis import Redis

logger = logging.getLogger(__name__)

# 空值缓存标记
NULL_CACHE_MARKER = -1
NULL_CACHE_TTL = 60  # 空值缓存 60 秒


class InventoryCacheService:
    """库存缓存服务"""

    def __init__(self, redis: Redis = None):
        self.redis = redis
        # 预编译 Lua 脚本
        self._reserve_script = None
        self._release_script = None
        self._batch_reserve_script = None
        if self.redis:
            self._reserve_script = self.redis.register_script(self.RESERVE_STOCK_LUA)
            self._release_script = self.redis.register_script(self.RELEASE_STOCK_LUA)
            self._batch_reserve_script = self.redis.register_script(self.BATCH_RESERVE_LUA)

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
            value = int(cached)
            if value == NULL_CACHE_MARKER:
                logger.debug(f"Cache hit (null) for warehouse {warehouse_id}, product {product_id}")
                return None  # 返回 None 表示缓存命中但值为空
            logger.debug(f"Cache hit for warehouse {warehouse_id}, product {product_id}")
            return value

        return None

    def set_cached_stock(self, warehouse_id: str, product_id: int, available: int, ttl: int = 0):
        """设置缓存的可用库存"""
        if not self.redis:
            return

        cache_key = self._get_cache_key(warehouse_id, product_id)
        if available is None:
            # 存储空值标记
            self.redis.setex(cache_key, NULL_CACHE_TTL, NULL_CACHE_MARKER)
            logger.debug(f"Null cache set for warehouse {warehouse_id}, product {product_id}")
        else:
            if ttl > 0:
                self.redis.setex(cache_key, ttl, available)
            else:
                self.redis.set(cache_key, available)
            logger.debug(f"Cache set for warehouse {warehouse_id}, product {product_id}: {available}")

    def get_cached_full_info(self, warehouse_id: str, product_id: int) -> Optional[dict]:
        """获取缓存的完整库存信息"""
        if not self.redis:
            return None

        import json
        cache_key = self._get_full_cache_key(warehouse_id, product_id)
        cached = self.redis.get(cache_key)

        if cached:
            value = cached.decode('utf-8') if isinstance(cached, bytes) else cached
            if value == "NULL":
                logger.debug(f"Full cache hit (null) for warehouse {warehouse_id}, product {product_id}")
                return None  # 返回 None 表示缓存命中但值为空
            return json.loads(value)

        return None

    def set_cached_full_info(self, warehouse_id: str, product_id: int, info: dict, ttl: int = 0):
        """设置缓存的完整库存信息"""
        if not self.redis:
            return

        import json
        cache_key = self._get_full_cache_key(warehouse_id, product_id)
        if info is None:
            # 存储空值标记
            self.redis.setex(cache_key, NULL_CACHE_TTL, "NULL")
            logger.debug(f"Full null cache set for warehouse {warehouse_id}, product {product_id}")
        else:
            if ttl > 0:
                self.redis.setex(cache_key, ttl, json.dumps(info))
            else:
                self.redis.set(cache_key, json.dumps(info))
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

    def batch_set_cached_stocks(self, warehouse_id: str, stock_map: dict, ttl: int = 0):
        """批量设置缓存的库存"""
        if not self.redis or not stock_map:
            return

        pipe = self.redis.pipeline()

        for product_id, available in stock_map.items():
            if ttl > 0:
                pipe.set(self._get_cache_key(warehouse_id, product_id), available, ex=ttl)
            else:
                pipe.set(self._get_cache_key(warehouse_id, product_id), available)
            logger.debug(f"Batch cache set for warehouse {warehouse_id}, product {product_id}: {available}")

        pipe.execute()

    # ==================== Lua 脚本 ====================
    
    # 原子扣减库存 Lua 脚本
    # 返回值: [new_stock, is_duplicate]
    # - new_stock: 扣减后的库存（如果失败返回负数）
    # - is_duplicate: 1 表示重复预占，0 表示正常
    RESERVE_STOCK_LUA = """
    local stock_key = KEYS[1]
    local reservation_key = KEYS[2]
    local quantity = tonumber(ARGV[1])
    local order_id = ARGV[2]
    local ttl = tonumber(ARGV[3])
    
    -- 获取当前库存
    local current_stock = tonumber(redis.call('GET', stock_key) or '0')
    
    -- 检查库存是否足够
    if current_stock < quantity then
        return {current_stock, 0}
    end
    
    -- 检查是否重复预占
    if redis.call('SISMEMBER', reservation_key, order_id) == 1 then
        return {current_stock, 1}
    end
    
    -- 原子扣减库存
    local new_stock = redis.call('DECRBY', stock_key, quantity)
    
    -- 记录预占信息
    redis.call('SADD', reservation_key, order_id)
    redis.call('EXPIRE', reservation_key, ttl)
    
    return {new_stock, 0}
    """
    
    # 原子释放库存 Lua 脚本
    # 返回值: [new_stock, is_not_found]
    RELEASE_STOCK_LUA = """
    local stock_key = KEYS[1]
    local reservation_key = KEYS[2]
    local quantity = tonumber(ARGV[1])
    local order_id = ARGV[2]
    
    -- 检查预占记录是否存在
    if redis.call('SISMEMBER', reservation_key, order_id) == 0 then
        return {-1, 1}
    end
    
    -- 原子增加库存
    local new_stock = redis.call('INCRBY', stock_key, quantity)
    
    -- 移除预占记录
    redis.call('SREM', reservation_key, order_id)
    
    return {new_stock, 0}
    """
    
    # 批量原子扣减库存 Lua 脚本
    # 返回值: [[product_id, new_stock, success], ...]
    BATCH_RESERVE_LUA = """
    local results = {}
    local n = #ARGV / 3
    
    for i = 1, n do
        local idx = (i - 1) * 3
        local product_id = tonumber(ARGV[idx + 1])
        local quantity = tonumber(ARGV[idx + 2])
        local order_id = ARGV[idx + 3]
        
        local stock_key = 'stock:available:WH01:' .. product_id
        local reservation_key = 'reservation:WH01:' .. product_id
        
        -- 获取当前库存
        local current_stock = tonumber(redis.call('GET', stock_key) or '0')
        
        -- 检查库存和重复
        local success = 0
        if current_stock >= quantity and redis.call('SISMEMBER', reservation_key, order_id) == 0 then
            redis.call('DECRBY', stock_key, quantity)
            redis.call('SADD', reservation_key, order_id)
            redis.call('EXPIRE', reservation_key, 900)
            current_stock = current_stock - quantity
            success = 1
        end
        
        table.insert(results, product_id)
        table.insert(results, current_stock)
        table.insert(results, success)
    end
    
    return results
    """

    def atomic_reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str,
        ttl: int = 900
    ) -> tuple:
        """原子预占库存（使用 Lua 脚本）
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            quantity: 预占数量
            order_id: 订单 ID
            ttl: 预占记录过期时间（秒）
            
        Returns:
            (new_stock, is_duplicate)
            - new_stock: 扣减后的库存（如果失败返回负数）
            - is_duplicate: True 表示重复预占
        """
        if not self.redis or not self._reserve_script:
            return None, False
        
        stock_key = self._get_cache_key(warehouse_id, product_id)
        reservation_key = f"reservation:{warehouse_id}:{product_id}"
        
        try:
            result = self._reserve_script(
                keys=[stock_key, reservation_key],
                args=[quantity, order_id, ttl]
            )
            new_stock = result[0]
            is_duplicate = bool(result[1])
            
            if new_stock < 0:
                logger.warning(f"库存不足: warehouse={warehouse_id}, product={product_id}, stock={new_stock}")
                return new_stock, False
            
            if is_duplicate:
                logger.warning(f"重复预占: order_id={order_id}")
                return new_stock, True
            
            logger.info(f"Redis 原子预占成功: order_id={order_id}, 新库存={new_stock}")
            return new_stock, False
            
        except Exception as e:
            logger.error(f"原子预占失败: {e}")
            return None, False

    def atomic_release_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> tuple:
        """原子释放库存（使用 Lua 脚本）
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            quantity: 释放数量
            order_id: 订单 ID
            
        Returns:
            (new_stock, is_not_found)
            - new_stock: 释放后的库存（如果失败返回 -1）
            - is_not_found: True 表示预占记录不存在
        """
        if not self.redis or not self._release_script:
            return None, False
        
        stock_key = self._get_cache_key(warehouse_id, product_id)
        reservation_key = f"reservation:{warehouse_id}:{product_id}"
        
        try:
            result = self._release_script(
                keys=[stock_key, reservation_key],
                args=[quantity, order_id]
            )
            new_stock = result[0]
            is_not_found = bool(result[1])
            
            if is_not_found:
                logger.warning(f"预占记录不存在: order_id={order_id}")
                return new_stock, True
            
            logger.info(f"Redis 原子释放成功: order_id={order_id}, 新库存={new_stock}")
            return new_stock, False
            
        except Exception as e:
            logger.error(f"原子释放失败: {e}")
            return None, False

    def atomic_batch_reserve(
        self,
        warehouse_id: str,
        order_id: str,
        items: list
    ) -> list:
        """原子批量预占库存（使用 Lua 脚本）
        
        Args:
            warehouse_id: 仓库 ID
            order_id: 订单 ID
            items: [(product_id, quantity), ...]
            
        Returns:
            [{product_id, new_stock, success}, ...]
        """
        if not self.redis or not self._batch_reserve_script:
            return []
        
        # 构建参数: [product_id, quantity, order_id, ...]
        args = []
        for product_id, quantity in items:
            args.extend([product_id, quantity, order_id])
        
        try:
            result = self._batch_reserve_script(args=args)
            
            # 解析结果: [product_id, new_stock, success, ...]
            results = []
            for i in range(0, len(result), 3):
                results.append({
                    'product_id': result[i],
                    'new_stock': result[i + 1],
                    'success': bool(result[i + 2])
                })
            
            return results
            
        except Exception as e:
            logger.error(f"原子批量预占失败: {e}")
            return []

    # ==================== 幂等性校验 ====================
    
    def check_idempotent(self, operation: str, order_id: str) -> tuple[bool, dict]:
        """检查操作是否已经处理过（幂等性校验）
        
        Args:
            operation: 操作类型 (reserve, confirm, release)
            order_id: 订单 ID
            
        Returns:
            (is_duplicate, result)
            - is_duplicate: True 表示已处理过，直接返回之前的结果
            - result: 如果已处理，返回之前的结果
        """
        if not self.redis:
            return False, None
        
        # 幂等性 key: idempotent:operation:order_id
        key = f"idempotent:{operation}:{order_id}"
        
        try:
            result = self.redis.get(key)
            if result:
                import json
                try:
                    previous_result = json.loads(result)
                    logger.info(f"幂等命中: operation={operation}, order_id={order_id}")
                    return True, previous_result
                except json.JSONDecodeError:
                    # 如果不是 JSON，说明是简单标记（兼容旧数据）
                    return True, {"status": result.decode() if isinstance(result, bytes) else result}
            return False, None
        except Exception as e:
            logger.error(f"幂等性检查失败: {e}")
            return False, None
    
    def set_idempotent(self, operation: str, order_id: str, result_data: dict, ttl: int = 86400):
        """记录操作结果（用于幂等性校验）
        
        Args:
            operation: 操作类型 (reserve, confirm, release)
            order_id: 订单 ID
            result_data: 操作结果数据
            ttl: 过期时间，默认 24 小时
        """
        if not self.redis:
            return
        
        import json
        key = f"idempotent:{operation}:{order_id}"
        
        try:
            # 存储结果为 JSON 字符串
            self.redis.setex(key, ttl, json.dumps(result_data, ensure_ascii=False))
            logger.info(f"幂等结果已记录: operation={operation}, order_id={order_id}")
        except Exception as e:
            logger.error(f"记录幂等结果失败: {e}")
    
    def delete_idempotent(self, operation: str, order_id: str):
        """删除幂等性记录（用于测试清理）"""
        if not self.redis:
            return
        
        key = f"idempotent:{operation}:{order_id}"
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"删除幂等记录失败: {e}")
