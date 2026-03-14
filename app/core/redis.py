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
    import redis
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis
except ImportError:
    # redis < 4.0.0
    import redis
    from redis.client import Redis
    from redis.asyncio.client import Redis as AsyncRedis


# 统一的 Redis 配置（从 settings 读取）
from app.core.config import settings

# Redis 连接池配置（提升高并发性能）
REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "50"))  # 连接池大小
REDIS_POOL_MAX_OVERFLOW = int(os.getenv("REDIS_POOL_MAX_OVERFLOW", "100"))  # 最大溢出连接
REDIS_POOL_TIMEOUT = int(os.getenv("REDIS_POOL_TIMEOUT", "5"))  # 获取连接超时
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))  # Socket 超时（秒）
REDIS_SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2.0"))  # 连接超时

# 构建 Redis URL（支持密码）
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
else:
    REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

# 创建连接池（优化网络参数）
redis_connection_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True,
    max_connections=REDIS_POOL_SIZE,
    socket_timeout=REDIS_SOCKET_TIMEOUT,  # 降低默认超时，加快失败检测
    socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
    socket_keepalive=True,  # 启用 TCP keepalive，减少重连开销
    retry_on_timeout=False,  # 超时时不重试，直接报错（避免长时间阻塞）
)

# 基础 Redis 客户端（使用连接池）
redis_client = Redis(connection_pool=redis_connection_pool)
async_redis = AsyncRedis.from_url(REDIS_URL, decode_responses=True, max_connections=REDIS_POOL_SIZE)
sync_redis = Redis(connection_pool=redis_connection_pool)



# 导出
__all__ = [
    "redis_client",
    "async_redis", 
    "sync_redis",
    "REDIS_URL"
]