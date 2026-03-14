"""依赖注入配置模块 - Redis 优先架构"""

from fastapi import Depends

# Redis 依赖
from app.core.redis import redis_client, async_redis

# 数据库依赖（仅用于日志查询、历史记录等特定场景）
from app.db.session import SessionLocal


def get_redis():
    """获取同步 Redis 客户端"""
    return redis_client

def get_async_redis():
    """获取异步 Redis 客户端"""
    return async_redis


def get_db():
    """获取数据库会话（仅用于日志查询等特定场景）
    
    注意：正常的库存查询和操作已迁移到纯 Redis 架构，
    此数据库会话仅用于日志查询、历史记录等审计功能。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()