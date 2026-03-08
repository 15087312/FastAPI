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
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as MockInventoryService:
            
            db_mock = Mock()
            mock_session_local.return_value = db_mock
            
            # 配置 mock 服务
            service_mock = Mock()
            MockInventoryService.return_value = service_mock
            
            # 执行任务
            result = process_reservation("ORDER001", [
                {"warehouse_id": "WH01", "product_id": 1, "quantity": 2},
                {"warehouse_id": "WH01", "product_id": 2, "quantity": 1}
            ])
            
            # 验证结果
            assert result == {"status": "success", "order_id": "ORDER001"}
            db_mock.close.assert_called_once()

    def test_process_reservation_exception(self):
        """测试处理预占任务异常 - 测试数据库连接失败"""
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local:
            # 模拟 SessionLocal 抛出异常
            mock_session_local.side_effect = Exception("数据库连接失败")
            
            # 执行任务应该抛出异常
            with pytest.raises(Exception) as exc_info:
                process_reservation("ORDER001", [{"warehouse_id": "WH01", "product_id": 1, "quantity": 2}])
            
            assert "数据库连接失败" in str(exc_info.value)

    def test_cleanup_expired_reservations_success(self):
        """测试清理过期预占任务成功"""
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as MockInventoryService:
            
            db_mock = Mock()
            mock_session_local.return_value = db_mock
            
            # 配置 mock 服务返回清理数量
            service_mock = Mock()
            service_mock.cleanup_expired_reservations.return_value = 5
            MockInventoryService.return_value = service_mock
            
            # 执行任务
            result = cleanup_expired_reservations(batch_size=100)
            
            # 验证结果
            assert result == "成功清理 5 条过期预占记录"
            service_mock.cleanup_expired_reservations.assert_called_once_with(100)
            db_mock.commit.assert_called_once()
            db_mock.close.assert_called_once()

    def test_cleanup_expired_reservations_exception(self):
        """测试清理过期预占任务异常"""
        with patch('tasks.inventory_tasks.SessionLocal') as mock_session_local, \
             patch('tasks.inventory_tasks.InventoryService') as MockInventoryService:
            
            db_mock = Mock()
            mock_session_local.return_value = db_mock
            
            # 配置 mock 服务抛出异常
            service_mock = Mock()
            service_mock.cleanup_expired_reservations.side_effect = Exception("清理过程出错")
            MockInventoryService.return_value = service_mock
            
            # 执行任务应该抛出异常
            with pytest.raises(Exception) as exc_info:
                cleanup_expired_reservations(batch_size=50)
            
            assert "清理过程出错" in str(exc_info.value)
            db_mock.rollback.assert_called_once()
            db_mock.close.assert_called_once()