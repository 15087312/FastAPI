"""测试配置和 fixtures"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis
from redlock import Redlock

from app.db.base import Base
from app.core.config import settings


@pytest.fixture
def mock_db_session():
    """创建模拟数据库会话"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def mock_redis():
    """创建模拟 Redis 客户端"""
    redis_mock = Mock(spec=Redis)
    redis_mock.get.return_value = None
    redis_mock.setex.return_value = True
    redis_mock.delete.return_value = 1
    redis_mock.mget.return_value = [None, None]
    redis_mock.pipeline.return_value = Mock()
    return redis_mock


@pytest.fixture
def mock_redlock():
    """创建模拟 Redlock 分布式锁"""
    redlock_mock = Mock(spec=Redlock)
    lock_mock = Mock()
    redlock_mock.lock.return_value = lock_mock
    redlock_mock.unlock.return_value = True
    return redlock_mock


@pytest.fixture
def sample_product_data():
    """示例商品数据"""
    return {
        "id": 1,
        "sku": "TEST001",
        "name": "测试商品"
    }


@pytest.fixture
def sample_stock_data():
    """示例库存数据"""
    return {
        "product_id": 1,
        "available_stock": 100,
        "reserved_stock": 0,
        "version": 0
    }


@pytest.fixture
def sample_reservation_data():
    """示例预占数据"""
    return {
        "order_id": "ORDER001",
        "product_id": 1,
        "quantity": 2,
        "status": "RESERVED"
    }
