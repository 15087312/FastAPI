"""测试配置和 fixtures"""
import pytest
import os
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis


# 加载 .env 文件（确保测试时使用正确的环境配置）
from dotenv import load_dotenv
# 使用绝对路径，避免工作目录问题
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
env_file = os.path.join(project_root, '.env')
if os.path.exists(env_file):
    load_dotenv(env_file)
    print(f"Loaded .env from: {env_file}")
else:
    print(f"Warning: .env not found at {env_file}")

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
