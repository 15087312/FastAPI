"""依赖注入配置模块"""

from fastapi import Depends

# 数据库会话依赖
from app.db.session import SessionLocal
from sqlalchemy.orm import Session

# Redis 依赖
from app.core.redis import redis_client, redlock, async_redis

from app.services.inventory_service import InventoryService


def get_redis():
    """获取同步 Redis 客户端"""
    return redis_client

def get_async_redis():
    """获取异步 Redis 客户端"""
    return async_redis

def get_redlock():
    """获取 Redlock 分布式锁实例"""
    return redlock

def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_inventory_service(
    db: Session = Depends(get_db),
    redis = Depends(get_redis),
    rlock = Depends(get_redlock)
) -> InventoryService:
    """获取库存服务实例（依赖注入）"""
    return InventoryService(db=db, redis=redis, rlock=rlock)


# 常用的依赖注入别名
DatabaseDep = Depends(get_db)
RedisDep = Depends(get_redis)
AsyncRedisDep = Depends(get_async_redis)
RedlockDep = Depends(get_redlock)
InventoryServiceDep = Depends(get_inventory_service)