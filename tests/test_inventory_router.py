"""库存路由单元测试 - 使用真实数据库和 FastAPI TestClient"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.models.product import Product
from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from datetime import datetime, timedelta


class TestInventoryRouter:
    """库存路由测试类 - 使用真实数据库"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    @pytest.fixture
    def test_product(self, real_db_session):
        """创建或获取测试商品和库存"""
        # 先尝试查询是否已存在
        product = real_db_session.query(Product).filter(
            Product.sku == "ROUTER_TEST_001"
        ).first()
        
        if not product:
            # 不存在才创建
            product = Product(sku="ROUTER_TEST_001", name="路由测试商品")
            real_db_session.add(product)
            real_db_session.flush()
            
            stock = ProductStock(
                warehouse_id="WH01",
                product_id=product.id,
                available_stock=100,
                reserved_stock=0
            )
            real_db_session.add(stock)
            real_db_session.commit()
        else:
            # 如果存在，确保有对应的库存记录
            stock = real_db_session.query(ProductStock).filter(
                ProductStock.product_id == product.id,
                ProductStock.warehouse_id == "WH01"
            ).first()
            if not stock:
                stock = ProductStock(
                    warehouse_id="WH01",
                    product_id=product.id,
                    available_stock=100,
                    reserved_stock=0
                )
                real_db_session.add(stock)
                real_db_session.commit()
        
        yield product
        
        # 清理（只清理预占记录，保留商品和库存）
        real_db_session.query(InventoryReservation).filter(
            InventoryReservation.order_id.like("ROUTER_TEST_%")
        ).delete()
        real_db_session.commit()

    def test_reserve_stock_success(self, client, test_product, real_redis):
        """测试成功预占库存"""
        response = client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 2,
            "order_id": "ROUTER_TEST_ORDER_001"
        })
        
        # 打印详细响应信息以便调试
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "预占成功"

    def test_reserve_stock_insufficient(self, client, test_product):
        """测试库存不足"""
        response = client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 200,  # 超过可用库存
            "order_id": "ROUTER_TEST_ORDER_002"
        })
        
        print(f"\nInsufficient stock - Status: {response.status_code}, Body: {response.text}")
        
        assert response.status_code == 400
        data = response.json()
        assert "库存不足" in data.get("message", "") or "库存不足" in data.get("detail", "")

    def test_reserve_stock_duplicate(self, client, test_product):
        """测试重复预占（幂等性）"""
        # 第一次预占
        response1 = client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 2,
            "order_id": "ROUTER_TEST_ORDER_003"
        })
        assert response1.status_code == 200
        
        # 第二次预占同一订单（幂等性：返回之前成功的结果）
        response2 = client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 2,
            "order_id": "ROUTER_TEST_ORDER_003"
        })
        
        # 幂等性：返回 200 而不是 400
        assert response2.status_code == 200
        data = response2.json()
        assert data.get("success") == True

    def test_confirm_stock_success(self, client, test_product, real_db_session):
        """测试成功确认库存"""
        # 先预占
        client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 2,
            "order_id": "ROUTER_TEST_ORDER_004"
        })
        
        # 确认
        response = client.post(f"/api/v1/inventory/confirm/ROUTER_TEST_ORDER_004")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "确认成功"

    def test_confirm_stock_not_found(self, client):
        """测试确认不存在的订单"""
        response = client.post("/api/v1/inventory/confirm/NONEXISTENT_ORDER")
        
        assert response.status_code == 404
        data = response.json()
        assert "未找到有效的预占记录" in data.get("message", "") or "未找到有效的预占记录" in data.get("detail", "")

    def test_release_stock_success(self, client, test_product, real_db_session):
        """测试成功释放库存"""
        # 先预占
        reserve_response = client.post("/api/v1/inventory/reserve", params={
            "warehouse_id": "WH01",
            "product_id": test_product.id,
            "quantity": 2,
            "order_id": "ROUTER_TEST_ORDER_005"
        })
        print(f"\nReserve response: {reserve_response.status_code} - {reserve_response.text}")
        
        # 确认释放
        response = client.post(f"/api/v1/inventory/release/ROUTER_TEST_ORDER_005")
        print(f"Release response: {response.status_code} - {response.text}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "释放成功"

    def test_get_stock_success(self, client, test_product):
        """测试查询库存成功"""
        response = client.get(f"/api/v1/inventory/stock/{test_product.id}?warehouse_id=WH01")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["product_id"] == test_product.id

    def test_get_stock_not_found(self, client):
        """测试查询不存在的商品"""
        response = client.get("/api/v1/inventory/stock/999999?warehouse_id=WH01")
        
        assert response.status_code == 200
        data = response.json()
        # 返回空库存信息
        assert data["success"] is True

    def test_batch_get_stocks(self, client, test_product):
        """测试批量查询库存"""
        response = client.post(
            f"/api/v1/inventory/stock/batch?warehouse_id=WH01",
            json={"product_ids": [test_product.id]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_increase_stock(self, client, test_product):
        """测试入库"""
        response = client.post(
            "/api/v1/inventory/increase",
            json={
                "warehouse_id": "WH01",
                "product_id": test_product.id,
                "quantity": 50,
                "operator": "test_user",
                "remark": "测试入库"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_adjust_stock(self, client, test_product):
        """测试库存调整"""
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "warehouse_id": "WH01",
                "product_id": test_product.id,
                "adjust_type": "increase",
                "quantity": 10,
                "reason": "测试调整",
                "operator": "test_user"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
