"""模型单元测试"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.product import Product
from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType


class TestModels:
    """数据模型测试类"""

    @pytest.fixture
    def db_session(self):
        """创建PostgreSQL数据库会话"""
        # 使用PostgreSQL测试数据库
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

    def test_product_model(self, db_session):
        """测试商品模型"""
        # 创建商品
        product = Product(
            sku="PROD001",
            name="测试商品"
        )
        db_session.add(product)
        db_session.commit()
        
        # 查询验证
        saved_product = db_session.query(Product).first()
        assert saved_product.id is not None
        assert saved_product.sku == "PROD001"
        assert saved_product.name == "测试商品"
        assert saved_product.created_at is not None
        assert saved_product.updated_at is not None

    def test_product_stock_model(self, db_session):
        """测试商品库存模型"""
        # 先创建商品
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        # 创建库存记录
        stock = ProductStock(
            product_id=product.id,
            available_stock=100,
            reserved_stock=10
        )
        db_session.add(stock)
        db_session.commit()
        
        # 查询验证
        saved_stock = db_session.query(ProductStock).first()
        assert saved_stock.product_id == product.id
        assert saved_stock.available_stock == 100
        assert saved_stock.reserved_stock == 10
        assert saved_stock.version == 0

    def test_inventory_reservation_model(self, db_session):
        """测试库存预占模型"""
        # 创建商品和库存
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        stock = ProductStock(product_id=product.id, available_stock=50)
        db_session.add(stock)
        db_session.flush()
        
        # 创建预占记录
        reservation = InventoryReservation(
            order_id="ORDER001",
            product_id=product.id,
            quantity=5,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow()
        )
        db_session.add(reservation)
        db_session.commit()
        
        # 查询验证
        saved_reservation = db_session.query(InventoryReservation).first()
        assert saved_reservation.order_id == "ORDER001"
        assert saved_reservation.product_id == product.id
        assert saved_reservation.quantity == 5
        assert saved_reservation.status == ReservationStatus.RESERVED
        assert saved_reservation.expired_at is not None

    def test_inventory_log_model(self, db_session):
        """测试库存日志模型"""
        # 创建商品
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        # 创建日志记录
        log = InventoryLog(
            product_id=product.id,
            order_id="ORDER001",
            change_type=ChangeType.RESERVE,
            quantity=-2,
            before_available=10,
            after_available=8,
            operator="test_user",
            source="order_service"
        )
        db_session.add(log)
        db_session.commit()
        
        # 查询验证
        saved_log = db_session.query(InventoryLog).first()
        assert saved_log.product_id == product.id
        assert saved_log.order_id == "ORDER001"
        assert saved_log.change_type == ChangeType.RESERVE
        assert saved_log.quantity == -2
        assert saved_log.before_available == 10
        assert saved_log.after_available == 8
        assert saved_log.operator == "test_user"
        assert saved_log.source == "order_service"
        assert saved_log.created_at is not None

    def test_unique_constraints(self, db_session):
        """测试唯一约束"""
        # 创建商品
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        # 创建第一条预占记录
        reservation1 = InventoryReservation(
            order_id="ORDER001",
            product_id=product.id,
            quantity=2,
            status=ReservationStatus.RESERVED
        )
        db_session.add(reservation1)
        db_session.commit()
        
        # 尝试创建重复的预占记录（相同订单和商品）
        reservation2 = InventoryReservation(
            order_id="ORDER001",  # 相同订单ID
            product_id=product.id,  # 相同商品ID
            quantity=3,
            status=ReservationStatus.RESERVED
        )
        db_session.add(reservation2)
        
        # 应该违反唯一约束
        with pytest.raises(Exception):
            db_session.commit()

    def test_check_constraints(self, db_session):
        """测试检查约束"""
        # 创建商品
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        # 尝试创建负库存（应该违反检查约束）
        stock = ProductStock(
            product_id=product.id,
            available_stock=-5,  # 负数库存
            reserved_stock=0
        )
        db_session.add(stock)
        
        # 应该违反检查约束
        with pytest.raises(Exception):
            db_session.commit()

    def test_relationships(self, db_session):
        """测试模型关系"""
        # 创建商品
        product = Product(sku="PROD001", name="测试商品")
        db_session.add(product)
        db_session.flush()
        
        # 创建库存
        stock = ProductStock(
            product_id=product.id,
            available_stock=100,
            reserved_stock=10
        )
        db_session.add(stock)
        db_session.flush()
        
        # 创建多个预占记录
        reservation1 = InventoryReservation(
            order_id="ORDER001",
            product_id=product.id,
            quantity=5,
            status=ReservationStatus.RESERVED
        )
        reservation2 = InventoryReservation(
            order_id="ORDER002",
            product_id=product.id,
            quantity=3,
            status=ReservationStatus.RESERVED
        )
        db_session.add_all([reservation1, reservation2])
        db_session.commit()
        
        # 验证可以通过商品查询相关记录
        saved_product = db_session.query(Product).first()
        assert saved_product.stocks is not None  # stocks 是单个对象
        assert len(saved_product.reservations) == 2  # reservations 是列表
