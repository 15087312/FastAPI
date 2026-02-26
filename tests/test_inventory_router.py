"""库存路由单元测试"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.routers.inventory_router import router


class TestInventoryRouter:
    """库存路由测试类"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    @pytest.fixture
    def mock_service(self):
        """创建模拟库存服务"""
        with patch('app.routers.inventory_router.InventoryService') as mock:
            service_mock = Mock()
            mock.return_value = service_mock
            yield service_mock

    def test_reserve_stock_success(self, client, mock_service):
        """测试成功预占库存"""
        mock_service.reserve_stock.return_value = True
        
        response = client.post("/api/v1/inventory/reserve", params={
            "product_id": 1,
            "quantity": 2,
            "order_id": "ORDER001"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "预占成功"
        mock_service.reserve_stock.assert_called_once_with(1, 2, "ORDER001")

    def test_reserve_stock_http_exception(self, client, mock_service):
        """测试预占库存时抛出 HTTPException"""
        mock_service.reserve_stock.side_effect = HTTPException(
            status_code=400, detail="库存不足"
        )
        
        response = client.post("/api/v1/inventory/reserve", params={
            "product_id": 1,
            "quantity": 100,
            "order_id": "ORDER001"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "库存不足"

    def test_reserve_stock_unknown_exception(self, client, mock_service):
        """测试预占库存时抛出未知异常"""
        mock_service.reserve_stock.side_effect = ValueError("数据库连接失败")
        
        response = client.post("/api/v1/inventory/reserve", params={
            "product_id": 1,
            "quantity": 2,
            "order_id": "ORDER001"
        })
        
        assert response.status_code == 500
        data = response.json()
        assert "数据库连接失败" in data["detail"]

    def test_confirm_stock_success(self, client, mock_service):
        """测试成功确认库存"""
        mock_service.confirm_stock.return_value = True
        
        response = client.post("/api/v1/inventory/confirm/ORDER001")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "确认成功"
        mock_service.confirm_stock.assert_called_once_with("ORDER001")

    def test_confirm_stock_not_found(self, client, mock_service):
        """测试确认库存时找不到预占记录"""
        mock_service.confirm_stock.side_effect = HTTPException(
            status_code=404, detail="未找到有效的预占记录"
        )
        
        response = client.post("/api/v1/inventory/confirm/ORDER001")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "未找到有效的预占记录"

    def test_release_stock_success(self, client, mock_service):
        """测试成功释放库存"""
        mock_service.release_stock.return_value = True
        
        response = client.post("/api/v1/inventory/release/ORDER001")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "释放成功"
        mock_service.release_stock.assert_called_once_with("ORDER001")

    def test_manual_cleanup_success(self, client, mock_service):
        """测试手动清理成功"""
        mock_service.cleanup_expired_reservations.return_value = 5
        
        with patch('app.routers.inventory_router.get_db') as mock_get_db:
            db_mock = Mock()
            mock_get_db.return_value.__enter__.return_value = db_mock
            
            response = client.post("/api/v1/inventory/cleanup/manual", params={
                "batch_size": 100
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["cleaned_count"] == 5
            db_mock.commit.assert_called_once()

    def test_manual_cleanup_exception(self, client, mock_service):
        """测试手动清理异常"""
        mock_service.cleanup_expired_reservations.side_effect = Exception("清理失败")
        
        with patch('app.routers.inventory_router.get_db') as mock_get_db:
            db_mock = Mock()
            mock_get_db.return_value.__enter__.return_value = db_mock
            
            response = client.post("/api/v1/inventory/cleanup/manual")
            
            assert response.status_code == 500
            data = response.json()
            assert "清理失败" in data["detail"]
            db_mock.rollback.assert_called_once()

    def test_celery_cleanup_success(self, client):
        """测试 Celery 清理任务提交成功"""
        task_mock = Mock()
        task_mock.id = "task123"
        
        with patch('app.routers.inventory_router.celery_cleanup_task') as mock_task:
            mock_task.delay.return_value = task_mock
            
            response = client.post("/api/v1/inventory/cleanup/celery", params={
                "batch_size": 200
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["task_id"] == "task123"
            mock_task.delay.assert_called_once_with(200)

    def test_celery_cleanup_exception(self, client):
        """测试 Celery 清理任务提交异常"""
        with patch('app.routers.inventory_router.celery_cleanup_task') as mock_task:
            mock_task.delay.side_effect = Exception("Celery 配置错误")
            
            response = client.post("/api/v1/inventory/cleanup/celery")
            
            assert response.status_code == 500
            data = response.json()
            assert "Celery 配置错误" in data["detail"]

    def test_get_cleanup_status_pending(self, client):
        """测试查询清理任务状态 - 等待中"""
        task_mock = Mock()
        task_mock.state = "PENDING"
        
        with patch('app.routers.inventory_router.app') as mock_app:
            mock_app.AsyncResult.return_value = task_mock
            
            response = client.get("/api/v1/inventory/cleanup/status/task123")
            
            assert response.status_code == 200
            data = response.json()
            assert "任务等待中" in data["status"]
            assert data["state"] == "PENDING"

    def test_get_cleanup_status_success(self, client):
        """测试查询清理任务状态 - 成功"""
        task_mock = Mock()
        task_mock.state = "SUCCESS"
        task_mock.result = "清理完成，处理了5条记录"
        
        with patch('app.routers.inventory_router.app') as mock_app:
            mock_app.AsyncResult.return_value = task_mock
            
            response = client.get("/api/v1/inventory/cleanup/status/task123")
            
            assert response.status_code == 200
            data = response.json()
            assert "任务完成" in data["status"]
            assert "5条记录" in data["status"]

    def test_get_cleanup_status_failure(self, client):
        """测试查询清理任务状态 - 失败"""
        task_mock = Mock()
        task_mock.state = "FAILURE"
        task_mock.info = "内存不足"
        
        with patch('app.routers.inventory_router.app') as mock_app:
            mock_app.AsyncResult.return_value = task_mock
            
            response = client.get("/api/v1/inventory/cleanup/status/task123")
            
            assert response.status_code == 200
            data = response.json()
            assert "任务失败" in data["status"]
            assert "内存不足" in data["status"]

    def test_get_stock_success(self, client, mock_service):
        """测试查询单个商品库存成功"""
        mock_service.get_product_stock.return_value = 45
        
        response = client.get("/api/v1/inventory/stock/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["product_id"] == 1
        assert data["available_stock"] == 45
        mock_service.get_product_stock.assert_called_once_with(1)

    def test_get_stock_exception(self, client, mock_service):
        """测试查询库存异常"""
        mock_service.get_product_stock.side_effect = HTTPException(
            status_code=500, detail="数据库错误"
        )
        
        response = client.get("/api/v1/inventory/stock/999")
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "数据库错误"

    def test_batch_get_stocks_success(self, client, mock_service):
        """测试批量查询库存成功"""
        mock_service.batch_get_stocks.return_value = {
            1: 30,
            2: 25,
            3: 0
        }
        
        response = client.post("/api/v1/inventory/stock/batch", json={
            "product_ids": [1, 2, 3]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"] == {1: 30, 2: 25, 3: 0}
        mock_service.batch_get_stocks.assert_called_once_with([1, 2, 3])

    def test_batch_get_stocks_exception(self, client, mock_service):
        """测试批量查询库存异常"""
        mock_service.batch_get_stocks.side_effect = Exception("Redis 连接失败")
        
        response = client.post("/api/v1/inventory/stock/batch", json={
            "product_ids": [1, 2]
        })
        
        assert response.status_code == 500
        data = response.json()
        assert "Redis 连接失败" in data["detail"]
