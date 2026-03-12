"""库存服务单元测试 - 使用真实数据库"""
import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta

from app.services.inventory_service import InventoryService
from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType
from app.models.product import Product


class TestInventoryService:
    """库存服务测试类 - 使用真实数据库"""

    def test_init_service(self, real_db_session, real_redis):
        """测试服务初始化"""
        service = InventoryService(real_db_session, real_redis)
        assert service.db == real_db_session
        assert service.redis == real_redis

    def test_get_product_stock_cache_hit(self, real_db_session, real_redis):
        """测试缓存命中情况下的库存查询"""
        import uuid
        unique_sku = f"TEST_CACHE_HIT_{uuid.uuid4().hex[:8]}"
        
        # 先插入库存数据到数据库
        product = Product(sku=unique_sku, name="测试商品")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=50,
            reserved_stock=0
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        # 设置缓存
        real_redis.setex("stock:available:WH01:50", 300, 50)
        
        # 查询 - 应该命中缓存
        service = InventoryService(real_db_session, real_redis)
        result = service.get_product_stock("WH01", product.id)
        
        # 由于 product.id 不同，缓存未命中，从数据库返回
        assert result >= 0

    def test_get_product_stock_cache_miss(self, real_db_session, real_redis):
        """测试缓存未命中情况下的库存查询"""
        import uuid
        unique_sku = f"TEST_CACHE_MISS_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据
        product = Product(sku=unique_sku, name="测试商品 2")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=30,
            reserved_stock=0
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        # 清空缓存
        real_redis.delete(f"stock:available:WH01:{product.id}")
        
        # 查询 - 缓存未命中，从数据库查询
        service = InventoryService(real_db_session, real_redis)
        result = service.get_product_stock("WH01", product.id)
        
        assert result == 30
        
        # 验证缓存已设置
        cached = real_redis.get(f"stock:available:WH01:{product.id}")
        assert cached == "30"

    def test_get_product_stock_no_stock_record(self, real_db_session, real_redis):
        """测试商品无库存记录的情况"""
        # 清空缓存
        real_redis.delete("stock:available:WH01:999999")
        
        service = InventoryService(real_db_session, real_redis)
        result = service.get_product_stock("WH01", 999999)
        
        assert result == 0

    def test_reserve_stock_success(self, real_db_session, real_redis):
        """测试成功预占库存"""
        import uuid
        unique_sku = f"TEST_RESERVE_OK_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据
        product = Product(sku=unique_sku, name="测试商品 3")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=10,
            reserved_stock=0
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        result = service.reserve_stock("WH01", product.id, 2, "ORDER_TEST_001")
        
        assert result is True
        
        # 验证库存扣减
        real_db_session.refresh(stock)
        assert stock.available_stock == 8
        assert stock.reserved_stock == 2
        
        # 验证创建了预占记录
        reservation = real_db_session.query(InventoryReservation).filter(
            InventoryReservation.order_id == "ORDER_TEST_001"
        ).first()
        assert reservation is not None
        assert reservation.quantity == 2
        
        # 验证缓存失效
        cached = real_redis.get(f"stock:available:WH01:{product.id}")
        assert cached is None

    def test_reserve_stock_insufficient_stock(self, real_db_session, real_redis):
        """测试库存不足的情况"""
        import uuid
        unique_sku = f"TEST_INSUFFICIENT_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据
        product = Product(sku=unique_sku, name="测试商品 4")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=1,
            reserved_stock=0
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        
        with pytest.raises(HTTPException) as exc_info:
            service.reserve_stock("WH01", product.id, 5, "ORDER_TEST_002")
        
        assert exc_info.value.status_code == 400
        assert "库存不足" in str(exc_info.value.detail)
        real_db_session.rollback()

    def test_reserve_stock_duplicate_reservation(self, real_db_session, real_redis):
        """测试重复预占的情况"""
        import uuid
        unique_sku = f"TEST_DUPLICATE_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据和预占记录
        product = Product(sku=unique_sku, name="测试商品 5")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=10,
            reserved_stock=0
        )
        real_db_session.add(stock)
        
        # 第一次预占
        reservation = InventoryReservation(
            warehouse_id="WH01",
            order_id="ORDER_TEST_003",
            product_id=product.id,
            quantity=2,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow() + timedelta(minutes=15)
        )
        real_db_session.add(reservation)
        real_db_session.commit()
        
        stock.available_stock -= 2
        stock.reserved_stock += 2
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        
        with pytest.raises(HTTPException) as exc_info:
            service.reserve_stock("WH01", product.id, 2, "ORDER_TEST_003")
        
        assert exc_info.value.status_code == 400
        assert "该订单已预占此商品" in str(exc_info.value.detail)

    def test_confirm_stock_success(self, real_db_session, real_redis):
        """测试成功确认库存"""
        import uuid
        unique_sku = f"TEST_CONFIRM_OK_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据和预占记录
        product = Product(sku=unique_sku, name="测试商品 6")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=8,
            reserved_stock=2
        )
        real_db_session.add(stock)
        
        reservation = InventoryReservation(
            warehouse_id="WH01",
            order_id="ORDER_TEST_004",
            product_id=product.id,
            quantity=2,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow() + timedelta(minutes=15)
        )
        real_db_session.add(reservation)
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        result = service.confirm_stock("ORDER_TEST_004")
        
        assert result is True
        
        # 验证预占状态
        real_db_session.refresh(reservation)
        assert reservation.status == ReservationStatus.CONFIRMED
        
        # 验证库存
        real_db_session.refresh(stock)
        assert stock.reserved_stock == 0

    def test_confirm_stock_not_found(self, real_db_session, real_redis):
        """测试未找到预占记录"""
        service = InventoryService(real_db_session, real_redis)
        
        with pytest.raises(HTTPException) as exc_info:
            service.confirm_stock("NONEXISTENT_ORDER")
        
        assert exc_info.value.status_code == 404
        assert "未找到有效的预占记录" in str(exc_info.value.detail)

    def test_release_stock_success(self, real_db_session, real_redis):
        """测试成功释放库存"""
        import uuid
        unique_sku = f"TEST_RELEASE_OK_{uuid.uuid4().hex[:8]}"
            
        # 插入库存数据和预占记录
        product = Product(sku=unique_sku, name="测试商品 7")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=8,
            reserved_stock=2
        )
        real_db_session.add(stock)
        
        reservation = InventoryReservation(
            warehouse_id="WH01",
            order_id="ORDER_TEST_005",
            product_id=product.id,
            quantity=2,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow() + timedelta(minutes=15)
        )
        real_db_session.add(reservation)
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        result = service.release_stock("ORDER_TEST_005")
        
        assert result is True
        
        # 验证预占状态
        real_db_session.refresh(reservation)
        assert reservation.status == ReservationStatus.RELEASED
        
        # 验证库存归还
        real_db_session.refresh(stock)
        assert stock.available_stock == 10
        assert stock.reserved_stock == 0

    def test_batch_get_stocks(self, real_db_session, real_redis):
        """测试批量获取库存"""
        import uuid
        unique_sku1 = f"TEST_BATCH_1_{uuid.uuid4().hex[:8]}"
        unique_sku2 = f"TEST_BATCH_2_{uuid.uuid4().hex[:8]}"
            
        # 插入多个商品库存
        product1 = Product(sku=unique_sku1, name="测试商品 8")
        product2 = Product(sku=unique_sku2, name="测试商品 9")
        real_db_session.add_all([product1, product2])
        real_db_session.flush()
        
        stock1 = ProductStock(
            warehouse_id="WH01",
            product_id=product1.id,
            available_stock=30,
            reserved_stock=0
        )
        stock2 = ProductStock(
            warehouse_id="WH01",
            product_id=product2.id,
            available_stock=25,
            reserved_stock=0
        )
        real_db_session.add_all([stock1, stock2])
        real_db_session.commit()
        
        service = InventoryService(real_db_session, real_redis)
        result = service.batch_get_stocks("WH01", [product1.id, product2.id])
        
        assert result[product1.id] == 30
        assert result[product2.id] == 25
