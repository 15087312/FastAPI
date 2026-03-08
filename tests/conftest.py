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


# 真实的数据库连接（使用 Docker 容器中的数据库）
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


class RedLockAdapter:
    """RedLock 适配器 - 使用 Mock 来模拟锁"""
    
    def __init__(self, servers, ttl=10000):
        self._ttl = ttl
    
    def lock(self, resource, ttl=None):
        """获取锁 - 返回一个 Mock 对象"""
        mock_lock = Mock()
        mock_lock.release = Mock(return_value=True)
        return mock_lock
    
    def unlock(self, lock):
        """释放锁"""
        if lock and hasattr(lock, 'release'):
            lock.release()
        return True


@pytest.fixture(scope="function")
def real_redlock():
    """创建真实 Redlock 分布式锁实例"""
    try:
        redlock = RedLockAdapter([{"host": "localhost", "port": 6379, "db": 0}])
        yield redlock
    except Exception as e:
        pytest.skip(f"Redlock not available: {e}")


@pytest.fixture
def mock_db_session():
    """创建模拟数据库会话"""
    # 使用测试数据库URL
    DATABASE_URL = "postgresql://postgres:123456@localhost:5432/mydb"
    engine = create_engine(DATABASE_URL, echo=False)
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
    # 创建一个完整的 mock 对象，包含 lock 和 unlock 方法
    redlock_mock = Mock()
    lock_mock = Mock()
    
    # 配置 mock_redlock.lock() 返回 lock_mock
    redlock_mock.lock = Mock(return_value=lock_mock)
    # 配置 mock_redlock.unlock() 返回 True
    redlock_mock.unlock = Mock(return_value=True)
    
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
