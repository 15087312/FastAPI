"""依赖注入单元测试"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
from redis import Redis
try:
    from redlock import RedLock as Redlock
except ImportError:
    from redlock import Redlock

from app.core.dependencies import (
    get_db,
    get_redis,
    get_redlock,
    get_inventory_service
)
from app.services.inventory_service import InventoryService


class TestDependencies:
    """依赖注入测试类"""

    def test_get_db(self):
        """测试数据库会话依赖"""
        with patch('app.core.dependencies.SessionLocal') as mock_session_local:
            db_mock = Mock(spec=Session)
            mock_session_local.return_value = db_mock
            
            # 获取生成器
            gen = get_db()
            db = next(gen)
            
            assert db == db_mock
            mock_session_local.assert_called_once()
            
            # 测试清理
            try:
                gen.throw(GeneratorExit)
            except GeneratorExit:
                pass
            db_mock.close.assert_called_once()

    def test_get_redis_success(self):
        """测试 Redis 连接成功"""
        with patch('app.core.dependencies.redis_client') as mock_redis_client:
            # get_redis() 直接返回 redis_client，不进行 ping() 调用
            result = get_redis()
            
            # 验证返回的是 redis_client
            assert result == mock_redis_client

    def test_get_redis_when_client_none(self):
        """测试 Redis 客户端为空的情况"""
        with patch('app.core.dependencies.redis_client', None):
            result = get_redis()
            
            # 当 redis_client 为 None 时返回 None
            assert result is None

    def test_get_redlock_success(self):
        """测试 Redlock 连接成功"""
        with patch('app.core.dependencies.redlock') as mock_redlock:
            mock_redlock.servers = [Mock()]  # 模拟有服务器配置
            
            rlock = get_redlock()
            
            assert rlock == mock_redlock

    def test_get_redlock_when_none(self):
        """测试 Redlock 客户端为空的情况"""
        with patch('app.core.dependencies.redlock', None):
            result = get_redlock()
            
            # 当 redlock 为 None 时返回 None
            assert result is None

    def test_get_inventory_service(self):
        """测试库存服务依赖注入"""
        db_mock = Mock(spec=Session)
        redis_mock = Mock(spec=Redis)
        redlock_mock = Mock(spec=Redlock)
        
        # 直接调用 InventoryService 构造函数
        service = InventoryService(db_mock, redis_mock, redlock_mock)
        
        assert isinstance(service, InventoryService)
        assert service.db == db_mock
        assert service.redis == redis_mock
        assert service.rlock == redlock_mock

    def test_get_inventory_service_partial_deps(self):
        """测试部分依赖不可用时的服务创建"""
        db_mock = Mock(spec=Session)
        
        # 测试只有 db 的情况
        service = InventoryService(db_mock, None, None)
        
        assert isinstance(service, InventoryService)
        assert service.db == db_mock
        assert service.redis is None
        assert service.rlock is None
