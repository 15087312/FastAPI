"""Redis 客户端配置模块"""

import os
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redlock import Redlock

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
    
    return Redlock(servers)

redlock = create_redlock()

# 导出
__all__ = [
    "redis_client",
    "async_redis", 
    "sync_redis",
    "redlock",
    "REDIS_URL"
]