"""Redis 客户端配置模块"""

import os
import logging

logger = logging.getLogger(__name__)

# 确保加载 .env 文件（防止 PyCharm 等 IDE 未加载环境变量）
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

try:
    # redlock-ng (推荐，最新 2.0.4) - 注意是小写 Redlock
    from redlock import Redlock
except ImportError:
    try:
        # redlock 旧版本（大写 RedLock）
        from redlock import RedLock as Redlock
    except ImportError:
        # 如果都找不到，抛出明确的错误
        raise ImportError(
            "未找到 redlock 库，请安装：pip install redlock-py 或 pip install redlock-ng"
        )


class RedLockAdapter:
    """RedLock 适配器 - 支持 redlock-py 和 redlock-ng"""
    
    def __init__(self, servers, ttl=10000):
        self._servers = servers
        self._ttl = ttl
        # 导入 Redlock
        try:
            from redlock import Redlock
            self._redlock = Redlock(servers)
            self._is_new_version = False  # redlock-py 或旧版 redlock-ng
        except (ImportError, TypeError):
            # 如果是 redlock-ng 2.0+
            from redlock import Redlock
            self._redlock = Redlock(servers)
            self._is_new_version = True
    
    def lock(self, resource, ttl=None):
        """获取锁 - 返回一个可以 unlock 的对象"""
        if ttl is None:
            ttl = self._ttl
        
        try:
            lock_result = self._redlock.lock(resource, ttl)
            
            if not lock_result:
                return None
            
            # 检查是否是 LockContext（redlock-ng 2.0+）
            if hasattr(lock_result, '__enter__') and hasattr(lock_result, '__exit__'):
                # redlock-ng 2.0+: 需要调用 __enter__() 获取锁
                try:
                    lock_obj = lock_result.__enter__()
                    if lock_obj:
                        return (lock_result, lock_obj)
                except Exception:
                    return None
            else:
                # redlock-py 或旧版本：直接返回 Lock 对象
                return (None, lock_result)
                
        except Exception as e:
            logger.error(f"Redlock.lock() 异常：{e}")
            return None
        
        return None
    
    def unlock(self, lock_obj):
        """释放锁 - 需要传入 lock 返回的 lock 对象"""
        if not lock_obj:
            return True
        
        try:
            # 如果是元组 (lock_context, lock_obj)
            if isinstance(lock_obj, tuple) and len(lock_obj) == 2:
                lock_context, lock = lock_obj
                if lock_context and hasattr(lock_context, '__exit__'):
                    # redlock-ng 2.0+: 使用 __exit__ 释放
                    lock_context.__exit__(None, None, None)
                elif lock:
                    # redlock-py: 尝试调用 extend 或其他方法
                    if hasattr(lock, 'extend'):
                        lock.extend(0)  # 立即释放
                    elif hasattr(lock, 'release'):
                        lock.release()  # 某些版本用 release
                    # 否则让锁自动过期
            elif hasattr(lock_obj, 'extend'):
                # 直接的 Lock 对象（旧版本）
                lock_obj.extend(0)
            elif hasattr(lock_obj, 'release'):
                # 某些版本的 Lock 对象
                lock_obj.release()
            return True
        except Exception as e:
            logger.error(f"Redlock.unlock() 异常：{e}")
            return False


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

# Redlock 配置（支持单实例和多实例）
def create_redlock():
    """根据环境变量动态创建 Redlock 实例"""
    redis_hosts = os.getenv("REDIS_HOSTS", REDIS_HOST)
    
    if "," in redis_hosts:  # 多实例模式
        hosts = redis_hosts.split(",")
        # redlock-ng 使用字符串格式：redis://host:port/db
        servers = [f"redis://{host.strip()}:{REDIS_PORT}/{REDIS_DB}" for host in hosts]
    else:  # 单实例模式
        # redlock-ng 必须使用 redis:// URL 格式
        servers = [f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"]
    
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