"""测试配置和 fixtures"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis
try:
    from redlock import RedLock as Redlock
except ImportError:
    from redlock import Redlock

from app.db.base import Base
from app.core.config import settings


# 真实数据库连接（使用 Docker 容器中的数据库）
DATABASE_URL = "postgresql://postgres:123456@localhost:5432/mydb"


@pytest.fixture(scope="function")
def real_db_session():
    """创建真实数据库会话"""
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(scope="function")
def real_redis():
    """创建真实 Redis 客户端"""
    redis_client = Redis(
        host="localhost",
        port=6379,
        db=0,
        decode_responses=True
    )
    # 测试连接
    try:
        redis_client.ping()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")
    
    yield redis_client
    
    # 清理测试数据
    try:
        redis_client.flushdb()
    except:
        pass



@pytest.fixture(scope="function")
def real_redlock():
    """创建真实 Redlock 分布式锁实例"""
    try:
        redlock = Redlock([{"host": "localhost", "port": 6379, "db": 0}])
        yield redlock
    except Exception as e:
        pytest.skip(f"Redlock not available: {e}")





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
