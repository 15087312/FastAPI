"""Redis 客户端配置模块"""

import os

try:
    # redis >= 4.0.0
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis
except ImportError:
    # redis < 4.0.0
    from redis.client import Redis
    from redis.asyncio.client import Redis as AsyncRedis

try:
    # redlock 新版本
    from redlock import RedLock as Redlock
except ImportError:
    # redlock 旧版本
    from redlock import Redlock


class RedLockAdapter:
    """RedLock 适配器 - 添加 lock/unlock 接口兼容"""
    
    def __init__(self, servers, ttl=10000):
        self._servers = servers
        self._ttl = ttl
    
    def lock(self, resource, ttl=None):
        """获取锁 - 返回一个可以 unlock 的对象"""
        if ttl is None:
            ttl = self._ttl
        # Redlock 构造函数使用 ttl 参数（毫秒）
        redlock_obj = Redlock(resource, self._servers, ttl=ttl)
        if redlock_obj.acquire():
            return redlock_obj
        return None
    
    def unlock(self, lock_obj):
        """释放锁"""
        if lock_obj:
            lock_obj.release()
        return True


# 统一的 Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# 基础 Redis 客户端
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
async_redis = AsyncRedis.from_url(REDIS_URL, decode_responses=True)
sync_redis = Redis.from_url(REDIS_URL, decode_responses=True)

# Redlock 配置（支持单实例和多实例）
def create_redlock():
    """根据环境变量动态创建 Redlock 实例"""
    redis_hosts = os.getenv("REDIS_HOSTS", REDIS_HOST)
    
    if "," in redis_hosts:  # 多实例模式
        hosts = redis_hosts.split(",")
        servers = [
            {"host": host.strip(), "port": REDIS_PORT, "db": REDIS_DB}
            for host in hosts
        ]
    else:  # 单实例模式
        servers = [
            {"host": REDIS_HOST, "port": REDIS_PORT, "db": REDIS_DB}
        ]
    
    # 返回适配器以支持 lock/unlock API
    return RedLockAdapter(servers)

redlock = create_redlock()

# 导出
__all__ = [
    "redis_client",
    "async_redis", 
    "sync_redis",
    "redlock",
    "REDIS_URL"
]