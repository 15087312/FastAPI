"""核心模块"""

from app.core.config import settings
from app.core.redis import redis_client, async_redis, sync_redis, REDIS_URL
from app.core.aspects import (
    performance_monitor,
    log_operation,
    handle_exception,
    CacheInvalidationAspect,
    TransactionAspect,
    LoggingAspect,
    PERFORMANCE_THRESHOLD_WARNING,
    PERFORMANCE_THRESHOLD_CRITICAL,
)

__all__ = [
    "settings",
    "redis_client",
    "async_redis",
    "sync_redis",
    "REDIS_URL",
    "performance_monitor",
    "log_operation",
    "handle_exception",
    "CacheInvalidationAspect",
    "TransactionAspect",
    "LoggingAspect",
    "PERFORMANCE_THRESHOLD_WARNING",
    "PERFORMANCE_THRESHOLD_CRITICAL",
]
