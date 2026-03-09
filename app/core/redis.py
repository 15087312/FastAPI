"""Redis 客户端配置模块"""

import os
import logging

logger = logging.getLogger(__name__)

# 确保加载 .env 文件
try:
    from dotenv import load_dotenv
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    env_file = os.path.join(project_root, '.env')
    if os.path.exists(env_file):
        load_dotenv(env_file)
except Exception:
    pass  # 静默失败，使用默认值

try:
    # redis >= 4.0.0
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis
except ImportError:
    # redis < 4.0.0
    from redis.client import Redis
    from redis.asyncio.client import Redis as AsyncRedis


# 统一的 Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
# 确保 URL 包含 redis:// 前缀（强制添加，防止环境变量缺失）
if REDIS_HOST and not REDIS_HOST.startswith(('redis://', 'rediss://', 'unix://')):
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}" if REDIS_HOST else "redis://localhost:6379/0"

# 基础 Redis 客户端
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
async_redis = AsyncRedis.from_url(REDIS_URL, decode_responses=True)
sync_redis = Redis.from_url(REDIS_URL, decode_responses=True)



# 导出
__all__ = [
    "redis_client",
    "async_redis", 
    "sync_redis",
    "redlock",
    "REDIS_URL"
]