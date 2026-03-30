"""库存缓存服务 - 纯Redis操作，数据永不过期"""

from typing import Optional, Dict, Any
import logging
import json
from redis import Redis

logger = logging.getLogger(__name__)


# ==================== 预注册的 Lua 脚本（应用启动时注册一次） ====================
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
# 返回值：[[product_id, new_stock, success], ...]
BATCH_RESERVE_LUA = """
local results = {}
local warehouse_id = ARGV[1]
local order_id = ARGV[2]
local n = (#ARGV - 2) / 2

for i = 1, n do
    local idx = (i - 1) * 2 + 3
    local product_id = tonumber(ARGV[idx])
    local quantity = tonumber(ARGV[idx + 1])

    local stock_key = 'stock:available:' .. warehouse_id .. ':' .. product_id
    local reservation_key = 'reservation:' .. warehouse_id .. ':' .. product_id

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
    table.insert(results, success == 1)
end

return results
"""

# 预注册的脚本对象（单例）
_registered_scripts = {}


def init_lua_scripts(redis_client: Redis):
    """应用启动时预注册所有Lua脚本（只执行一次）
    
    Args:
        redis_client: Redis客户端实例
    """
    global _registered_scripts
    
    if not redis_client:
        logger.warning("Redis客户端未初始化，无法注册Lua脚本")
        return
    
    # 如果已经注册过，直接返回
    if _registered_scripts:
        logger.debug("Lua脚本已预注册，跳过")
        return
    
    try:
        _registered_scripts['reserve'] = redis_client.register_script(RESERVE_STOCK_LUA)
        _registered_scripts['release'] = redis_client.register_script(RELEASE_STOCK_LUA)
        _registered_scripts['batch_reserve'] = redis_client.register_script(BATCH_RESERVE_LUA)
        logger.info("✅ Lua脚本预注册成功")
    except Exception as e:
        logger.error(f"Lua脚本预注册失败: {e}")
        raise


def get_registered_script(name: str):
    """获取预注册的Lua脚本对象
    
    Args:
        name: 脚本名称 (reserve, release, batch_reserve)
    
    Returns:
        注册的脚本对象
    """
    return _registered_scripts.get(name)


class InventoryCacheService:
    """库存缓存服务 - 纯Redis操作，数据永不过期"""

    def __init__(self, redis: Redis = None):
        self.redis = redis
        # 复用预注册的 Lua 脚本，避免每次创建服务都重新注册
        self._reserve_script = get_registered_script('reserve')
        self._release_script = get_registered_script('release')
        self._batch_reserve_script = get_registered_script('batch_reserve')
        logger.info("✅ 库存缓存服务已初始化（纯Redis模式，数据永不过期）")

    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return f"stock:available:{warehouse_id}:{product_id}"

    def _get_full_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成完整库存信息缓存键"""
        return f"stock:full:{warehouse_id}:{product_id}"

    def get_cached_stock(self, warehouse_id: str, product_id: int) -> Optional[int]:
        """获取缓存的可用库存（纯Redis，无回源）"""
        cache_key = self._get_cache_key(warehouse_id, product_id)
        
        if not self.redis:
            logger.error("Redis未初始化")
            return None

        cached = self.redis.get(cache_key)

        if cached is not None:
            value = int(cached)
            logger.debug(f"Redis cache hit: {cache_key} = {value}")
            return value

        # Redis中没有数据，返回0（不在查询数据库）
        logger.debug(f"Redis cache miss: {cache_key}, return 0")
        return 0

    def set_cached_stock(self, warehouse_id: str, product_id: int, available: int):
        """设置缓存的可用库存（永不过期，TTL=0）"""
        cache_key = self._get_cache_key(warehouse_id, product_id)
        
        if not self.redis:
            logger.error("Redis未初始化")
            return

        # 永不过期：TTL=0 或不设置过期时间
        self.redis.set(cache_key, available)
        logger.debug(f"Redis cache set (no expiry): {cache_key} = {available}")

    def get_cached_full_info_optimized(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（优化版：使用 MGET 批量读取，仅 1 次网络往返）
            
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            
        Returns:
            完整库存信息字典，如果不存在则返回 None
        """
        if not self.redis:
            logger.error("Redis 未初始化")
            return None
            
        # 构建所有需要的 key，一次性 MGET 读取
        keys = [
            f"stock:full:{warehouse_id}:{product_id}",      # 完整信息
            f"stock:available:{warehouse_id}:{product_id}",  # 可用库存
            f"stock:reserved:{warehouse_id}:{product_id}",   # 预占库存
            f"stock:frozen:{warehouse_id}:{product_id}",     # 冻结库存
            f"stock:safety:{warehouse_id}:{product_id}"      # 安全库存
        ]
            
        # 单次网络往返，批量读取所有字段
        values = self.redis.mget(keys)
            
        full_info_raw, available_raw, reserved_raw, frozen_raw, safety_raw = values
            
        # 优先使用完整信息缓存
        if full_info_raw:
            value = full_info_raw.decode('utf-8') if isinstance(full_info_raw, bytes) else full_info_raw
            info = json.loads(value)
            logger.debug(f"MGET 命中完整信息：{warehouse_id}:{product_id}")
            return info
            
        # 如果没有完整信息，尝试从各个字段构建
        available = int(available_raw) if available_raw else 0
        reserved = int(reserved_raw) if reserved_raw else 0
        frozen = int(frozen_raw) if frozen_raw else 0
        safety = int(safety_raw) if safety_raw else 0
            
        # 如果所有字段都是 0，说明数据不存在
        if available == 0 and reserved == 0 and frozen == 0 and safety == 0:
            logger.debug(f"MGET 未命中：{warehouse_id}:{product_id}")
            return None
            
        # 构建完整信息
        info = {
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "available_stock": available,
            "reserved_stock": reserved,
            "frozen_stock": frozen,
            "safety_stock": safety,
            "total_stock": available + reserved + frozen
        }
            
        logger.debug(f"MGET 构建完整信息：{warehouse_id}:{product_id}")
        return info

    def set_cached_full_info(self, warehouse_id: str, product_id: int, info: Dict[str, Any]):
        """设置缓存的完整库存信息（永不过期）"""
        cache_key = self._get_full_cache_key(warehouse_id, product_id)
        
        if not self.redis:
            logger.error("Redis未初始化")
            return

        # 永不过期
        self.redis.set(cache_key, json.dumps(info))
        logger.debug(f"Redis full stock cache set (no expiry): {cache_key}")

    def invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效库存缓存"""
        if self.redis:
            self.redis.delete(self._get_cache_key(warehouse_id, product_id))
            logger.debug(f"Cache invalidated for warehouse {warehouse_id}, product {product_id}")

    def invalidate_caches(self, items: list):
        """批量失效缓存（使用管道优化）"""
        if not self.redis:
            return

        keys_to_delete = []
        for item in items:
            warehouse_id = item.get("warehouse_id")
            product_id = item.get("product_id")
            if warehouse_id and product_id:
                keys_to_delete.append(self._get_cache_key(warehouse_id, product_id))

        if keys_to_delete:
            pipe = self.redis.pipeline()
            for key in keys_to_delete:
                pipe.delete(key)
            pipe.execute()
            logger.debug(f"Batch cache invalidated: {len(keys_to_delete)} keys")

    def batch_get_cached_stocks(self, warehouse_id: str, product_ids: list) -> Dict[int, int]:
        """批量获取缓存的库存"""
        if not self.redis or not product_ids:
            return {}

        cache_keys = [self._get_cache_key(warehouse_id, pid) for pid in product_ids]
        cached_values = self.redis.mget(cache_keys)

        results = {}

        for pid, cached in zip(product_ids, cached_values):
            if cached is not None:
                results[pid] = int(cached)
                logger.debug(f"Batch cache hit for warehouse {warehouse_id}, product {pid}")
            else:
                # 未命中的返回0，不查数据库
                results[pid] = 0

        return results

    def batch_set_cached_stocks(self, warehouse_id: str, stock_map: dict):
        """批量设置缓存的库存（永不过期）"""
        if not self.redis or not stock_map:
            return

        pipe = self.redis.pipeline(transaction=False)

        for product_id, available in stock_map.items():
            # 永不过期
            pipe.set(self._get_cache_key(warehouse_id, product_id), available)
            logger.debug(f"Batch cache set for warehouse {warehouse_id}, product {product_id}: {available}")

        pipe.execute()

    # ==================== Lua 脚本方法 ====================

    def atomic_reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str,
        ttl: int = 900
    ) -> tuple:
        """原子预占库存（使用 Lua 脚本）"""
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
        """原子释放库存（使用 Lua 脚本）"""
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
        """原子批量预占库存（使用 Lua 脚本）"""
        if not self.redis or not self._batch_reserve_script:
            return []
            
        args = [warehouse_id]
        for product_id, quantity in items:
            args.extend([product_id, quantity])
            
        try:
            result = self._batch_reserve_script(args=args)
                
            results = []
            for i in range(0, len(result), 3):
                results.append({
                    'product_id': result[i],
                    'new_stock': result[i + 1],
                    'success': bool(result[i + 2])
                })
                
            return results
                
        except Exception as e:
            logger.error(f"原子批量预占失败：{e}")
            return []

    # ==================== 幂等性校验 ====================
    
    def check_idempotent(self, operation: str, order_id: str) -> tuple[bool, Optional[Dict]]:
        """检查操作是否已经处理过（幂等性校验）"""
        if not self.redis:
            return False, None
        
        key = f"idempotent:{operation}:{order_id}"
        
        try:
            result = self.redis.get(key)
            if result:
                try:
                    previous_result = json.loads(result)
                    logger.info(f"幂等命中: operation={operation}, order_id={order_id}")
                    return True, previous_result
                except json.JSONDecodeError:
                    return True, {"status": result.decode() if isinstance(result, bytes) else result}
            return False, None
        except Exception as e:
            logger.error(f"幂等性检查失败: {e}")
            return False, None
    
    def set_idempotent(self, operation: str, order_id: str, result_data: Dict, ttl: int = 86400):
        """记录操作结果（用于幂等性校验）"""
        if not self.redis:
            return
        
        key = f"idempotent:{operation}:{order_id}"
        
        try:
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