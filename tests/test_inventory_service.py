"""库存服务单元测试"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from datetime import datetime, timedelta

from app.services.inventory_service import InventoryService
from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType


class TestInventoryService:
    """库存服务测试类"""

    def test_init_service(self, mock_db_session, mock_redis, mock_redlock):
        """测试服务初始化"""
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        assert service.db == mock_db_session
        assert service.redis == mock_redis
        assert service.rlock == mock_redlock

    def test_get_product_stock_cache_hit(self, mock_db_session, mock_redis, mock_redlock):
        """测试缓存命中情况下的库存查询"""
        # 设置缓存返回值
        mock_redis.get.return_value = "50"
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.get_product_stock(1)
        
        assert result == 50
        mock_redis.get.assert_called_once_with("stock:available:1")
        # 缓存命中不应该查询数据库
        mock_db_session.execute.assert_not_called()

    def test_get_product_stock_cache_miss(self, mock_db_session, mock_redis, mock_redlock):
        """测试缓存未命中情况下的库存查询"""
        # 设置缓存未命中
        mock_redis.get.return_value = None
        
        # 模拟数据库查询结果
        stock_mock = Mock()
        stock_mock.available_stock = 30
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = stock_mock
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.get_product_stock(1)
        
        assert result == 30
        mock_redis.get.assert_called_once_with("stock:available:1")
        mock_db_session.execute.assert_called_once()
        # 应该设置缓存
        mock_redis.setex.assert_called_once_with("stock:available:1", 300, 30)

    def test_get_product_stock_no_stock_record(self, mock_db_session, mock_redis, mock_redlock):
        """测试商品无库存记录的情况"""
        mock_redis.get.return_value = None
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.get_product_stock(999)
        
        assert result == 0
        mock_redis.setex.assert_called_once_with("stock:available:999", 300, 0)

    def test_reserve_stock_success(self, mock_db_session, mock_redis, mock_redlock):
        """测试成功预占库存"""
        # 设置分布式锁
        lock_mock = Mock()
        mock_redlock.lock.return_value = lock_mock
        
        # 模拟数据库查询结果
        stock_mock = Mock()
        stock_mock.available_stock = 10
        stock_mock.reserved_stock = 0
        
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.reserve_stock(1, 2, "ORDER001")
        
        assert result is True
        # 验证库存扣减
        assert stock_mock.available_stock == 8
        assert stock_mock.reserved_stock == 2
        # 验证创建了预占记录
        mock_db_session.add.assert_called()
        # 验证事务提交
        mock_db_session.commit.assert_called_once()
        # 验证缓存失效
        mock_redis.delete.assert_called_once_with("stock:available:1")

    def test_reserve_stock_insufficient_stock(self, mock_db_session, mock_redis, mock_redlock):
        """测试库存不足的情况"""
        mock_redlock.lock.return_value = Mock()
        
        stock_mock = Mock()
        stock_mock.available_stock = 1  # 库存只有1个
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        
        with pytest.raises(HTTPException) as exc_info:
            service.reserve_stock(1, 5, "ORDER001")  # 尝试预占5个
        
        assert exc_info.value.status_code == 400
        assert "库存不足" in str(exc_info.value.detail)
        mock_db_session.rollback.assert_called_once()

    def test_reserve_stock_duplicate_reservation(self, mock_db_session, mock_redis, mock_redlock):
        """测试重复预占的情况"""
        mock_redlock.lock.return_value = Mock()
        
        stock_mock = Mock()
        stock_mock.available_stock = 10
        
        # 模拟已存在预占记录
        existing_reservation = Mock()
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_reservation
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        
        with pytest.raises(HTTPException) as exc_info:
            service.reserve_stock(1, 2, "ORDER001")
        
        assert exc_info.value.status_code == 400
        assert "该订单已预占此商品" in str(exc_info.value.detail)

    def test_reserve_stock_lock_failure(self, mock_db_session, mock_redis, mock_redlock):
        """测试获取分布式锁失败"""
        mock_redlock.lock.return_value = None  # 锁获取失败
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        
        with pytest.raises(HTTPException) as exc_info:
            service.reserve_stock(1, 2, "ORDER001")
        
        assert exc_info.value.status_code == 429
        assert "库存操作冲突，请稍后重试" in str(exc_info.value.detail)

    def test_confirm_stock_success(self, mock_db_session, mock_redis, mock_redlock):
        """测试成功确认库存"""
        lock_mock = Mock()
        mock_redlock.lock.return_value = lock_mock
        
        # 模拟预占记录
        reservation_mock = Mock()
        reservation_mock.product_id = 1
        reservation_mock.quantity = 2
        reservation_mock.status = ReservationStatus.RESERVED
        
        # 模拟商品库存
        stock_mock = Mock()
        stock_mock.reserved_stock = 2
        
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [reservation_mock]
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.confirm_stock("ORDER001")
        
        assert result is True
        assert reservation_mock.status == ReservationStatus.CONFIRMED
        assert stock_mock.reserved_stock == 0
        mock_db_session.commit.assert_called_once()

    def test_confirm_stock_not_found(self, mock_db_session, mock_redis, mock_redlock):
        """测试未找到预占记录"""
        mock_redlock.lock.return_value = Mock()
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []  # 无预占记录
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_stock("ORDER001")
        
        assert exc_info.value.status_code == 404
        assert "未找到有效的预占记录" in str(exc_info.value.detail)

    def test_release_stock_success(self, mock_db_session, mock_redis, mock_redlock):
        """测试成功释放库存"""
        lock_mock = Mock()
        mock_redlock.lock.return_value = lock_mock
        
        # 模拟预占记录
        reservation_mock = Mock()
        reservation_mock.product_id = 1
        reservation_mock.quantity = 2
        reservation_mock.status = ReservationStatus.RESERVED
        
        # 模拟商品库存
        stock_mock = Mock()
        stock_mock.available_stock = 8
        stock_mock.reserved_stock = 2
        
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [reservation_mock]
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.release_stock("ORDER001")
        
        assert result is True
        assert reservation_mock.status == ReservationStatus.RELEASED
        assert stock_mock.available_stock == 10  # 8 + 2
        assert stock_mock.reserved_stock == 0    # 2 - 2
        mock_db_session.commit.assert_called_once()

    def test_batch_get_stocks_partial_cache(self, mock_db_session, mock_redis, mock_redlock):
        """测试批量获取库存 - 部分缓存命中"""
        # 模拟部分缓存命中
        mock_redis.mget.return_value = ["30", None]  # product_id=1命中，product_id=2未命中
        
        # 模拟数据库查询结果
        stock1_mock = Mock()
        stock1_mock.product_id = 2
        stock1_mock.available_stock = 25
        
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [stock1_mock]
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.batch_get_stocks([1, 2])
        
        assert result == {1: 30, 2: 25}
        mock_redis.mget.assert_called_once()
        mock_db_session.execute.assert_called_once()
        # 验证设置了新缓存
        mock_redis.pipeline.assert_called_once()

    def test_cleanup_expired_reservations(self, mock_db_session, mock_redis, mock_redlock):
        """测试清理过期预占记录"""
        # 模拟过期预占记录
        reservation_mock = Mock()
        reservation_mock.product_id = 1
        reservation_mock.order_id = "ORDER001"
        reservation_mock.quantity = 2
        reservation_mock.status = ReservationStatus.RESERVED
        
        # 模拟商品库存
        stock_mock = Mock()
        stock_mock.available_stock = 8
        stock_mock.reserved_stock = 2
        
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = [reservation_mock]
        mock_db_session.execute.return_value.scalar_one.return_value = stock_mock
        
        service = InventoryService(mock_db_session, mock_redis, mock_redlock)
        result = service.cleanup_expired_reservations(batch_size=100)
        
        assert result == 1
        assert stock_mock.available_stock == 10  # 8 + 2
        assert stock_mock.reserved_stock == 0    # 2 - 2
        assert reservation_mock.status == ReservationStatus.RELEASED
        mock_db_session.commit.assert_called_once()
