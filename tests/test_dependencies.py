"""依赖注入单元测试"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
from redis import Redis
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
            mock_redis_client.ping.return_value = True
            
            redis_conn = get_redis()
            
            assert redis_conn == mock_redis_client
            mock_redis_client.ping.assert_called_once()

    def test_get_redis_failure(self):
        """测试 Redis 连接失败"""
        with patch('app.core.dependencies.redis_client') as mock_redis_client:
            mock_redis_client.ping.side_effect = Exception("连接失败")
            
            redis_conn = get_redis()
            
            # 连接失败应该返回 None
            assert redis_conn is None

    def test_get_redlock_success(self):
        """测试 Redlock 连接成功"""
        with patch('app.core.dependencies.redlock') as mock_redlock:
            mock_redlock.servers = [Mock()]  # 模拟有服务器配置
            
            rlock = get_redlock()
            
            assert rlock == mock_redlock

    def test_get_redlock_failure(self):
        """测试 Redlock 连接失败"""
        with patch('app.core.dependencies.redlock') as mock_redlock:
            mock_redlock.servers = []  # 模拟无服务器配置
            
            rlock = get_redlock()
            
            # 无服务器配置应该返回 None
            assert rlock is None

    def test_get_inventory_service(self):
        """测试库存服务依赖注入"""
        db_mock = Mock(spec=Session)
        redis_mock = Mock(spec=Redis)
        redlock_mock = Mock(spec=Redlock)
        
        with patch('app.core.dependencies.get_db') as mock_get_db, \
             patch('app.core.dependencies.get_redis') as mock_get_redis, \
             patch('app.core.dependencies.get_redlock') as mock_get_redlock:
            
            mock_get_db.return_value.__enter__.return_value = db_mock
            mock_get_redis.return_value = redis_mock
            mock_get_redlock.return_value = redlock_mock
            
            service = get_inventory_service()
            
            assert isinstance(service, InventoryService)
            assert service.db == db_mock
            assert service.redis == redis_mock
            assert service.rlock == redlock_mock

    def test_get_inventory_service_partial_deps(self):
        """测试部分依赖不可用时的服务创建"""
        db_mock = Mock(spec=Session)
        
        with patch('app.core.dependencies.get_db') as mock_get_db, \
             patch('app.core.dependencies.get_redis') as mock_get_redis, \
             patch('app.core.dependencies.get_redlock') as mock_get_redlock:
            
            mock_get_db.return_value.__enter__.return_value = db_mock
            mock_get_redis.return_value = None  # Redis 不可用
            mock_get_redlock.return_value = None  # Redlock 不可用
            
            service = get_inventory_service()
            
            assert isinstance(service, InventoryService)
            assert service.db == db_mock
            assert service.redis is None
            assert service.rlock is None
