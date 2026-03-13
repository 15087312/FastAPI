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


# 统一的 Redis 配置（从 settings 读取）
from app.core.config import settings

# 构建 Redis URL（支持密码）
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
else:
    REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

# 基础 Redis 客户端
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
async_redis = AsyncRedis.from_url(REDIS_URL, decode_responses=True)
sync_redis = Redis.from_url(REDIS_URL, decode_responses=True)



# 导出
__all__ = [
    "redis_client",
    "async_redis", 
    "sync_redis",
    "REDIS_URL"
]