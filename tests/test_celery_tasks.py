"""Celery 任务单元测试"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from tasks.inventory_tasks import (
    process_reservation,
    cleanup_expired_reservations
)


class TestInventoryTasks:
    """库存 Celery 任务测试类"""

    def test_process_reservation_success(self):
        """测试处理预占任务成功"""
        # 模拟依赖
        service_mock = Mock()
        db_mock = Mock()
        
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as mock_inventory_service, \
             patch('tasks.inventory_tasks.redis_client') as mock_redis, \
             patch('tasks.inventory_tasks.redlock') as mock_redlock:
            
            mock_session_local.return_value = db_mock
            mock_inventory_service.return_value = service_mock
            
            # 执行任务
            result = process_reservation("ORDER001", [
                {"product_id": 1, "quantity": 2},
                {"product_id": 2, "quantity": 1}
            ])
            
            # 验证结果
            assert result == {"status": "success", "order_id": "ORDER001"}
            db_mock.commit.assert_called_once()

    def test_process_reservation_exception(self):
        """测试处理预占任务异常"""
        db_mock = Mock()
        
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as mock_inventory_service:
            
            mock_session_local.return_value = db_mock
            mock_inventory_service.side_effect = Exception("数据库错误")
            
            # 执行任务应该抛出异常
            with pytest.raises(Exception) as exc_info:
                process_reservation("ORDER001", [{"product_id": 1, "quantity": 2}])
            
            assert "数据库错误" in str(exc_info.value)
            db_mock.rollback.assert_called_once()

    def test_cleanup_expired_reservations_success(self):
        """测试清理过期预占任务成功"""
        service_mock = Mock()
        service_mock.cleanup_expired_reservations.return_value = 5
        db_mock = Mock()
        
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as mock_inventory_service, \
             patch('tasks.inventory_tasks.redis_client') as mock_redis, \
             patch('tasks.inventory_tasks.redlock') as mock_redlock:
            
            mock_session_local.return_value = db_mock
            mock_inventory_service.return_value = service_mock
            
            # 执行任务
            result = cleanup_expired_reservations(batch_size=100)
            
            # 验证结果
            assert result == "成功清理 5 条过期预占记录"
            service_mock.cleanup_expired_reservations.assert_called_once_with(100)
            db_mock.commit.assert_called_once()

    def test_cleanup_expired_reservations_exception(self):
        """测试清理过期预占任务异常"""
        db_mock = Mock()
        
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as mock_inventory_service:
            
            mock_session_local.return_value = db_mock
            mock_inventory_service.side_effect = Exception("清理过程出错")
            
            # 执行任务应该抛出异常
            with pytest.raises(Exception) as exc_info:
                cleanup_expired_reservations(batch_size=50)
            
            assert "清理过程出错" in str(exc_info.value)
            db_mock.rollback.assert_called_once()
