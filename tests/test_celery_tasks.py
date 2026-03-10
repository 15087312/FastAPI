"""Celery task unit tests - using real database"""
import pytest
from datetime import datetime, timedelta
import uuid

from tasks.inventory_tasks import (
    process_reservation,
    cleanup_expired_reservations
)
from app.models.product import Product
from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus


class TestInventoryTasks:
    """Inventory Celery task test class - using real database"""

    def test_process_reservation_success(self, real_db_session, real_redis):
        """Test successful reservation processing"""
        unique_sku = f"TEST_TASK_{uuid.uuid4().hex[:8]}"
        unique_order_id = f"ORDER_TASK_{uuid.uuid4().hex[:8]}"
        
        # Create products and stock
        product1 = Product(sku=unique_sku + "_1", name="Test Product 1")
        product2 = Product(sku=unique_sku + "_2", name="Test Product 2")
        real_db_session.add_all([product1, product2])
        real_db_session.flush()
        
        stock1 = ProductStock(
            warehouse_id="WH01",
            product_id=product1.id,
            available_stock=50,
            reserved_stock=0
        )
        stock2 = ProductStock(
            warehouse_id="WH01",
            product_id=product2.id,
            available_stock=30,
            reserved_stock=0
        )
        real_db_session.add_all([stock1, stock2])
        real_db_session.commit()
        
        # Execute task
        result = process_reservation(unique_order_id, [
            {"warehouse_id": "WH01", "product_id": product1.id, "quantity": 2},
            {"warehouse_id": "WH01", "product_id": product2.id, "quantity": 1}
        ])
        
        # Verify result
        assert result["status"] == "success"
        assert result["order_id"] == unique_order_id
        
        # Verify stock deduction
        real_db_session.refresh(stock1)
        real_db_session.refresh(stock2)
        assert stock1.available_stock == 48
        assert stock1.reserved_stock == 2
        assert stock2.available_stock == 29
        assert stock2.reserved_stock == 1
        
        # Verify reservations created
        reservations = real_db_session.query(InventoryReservation).filter(
            InventoryReservation.order_id == unique_order_id
        ).all()
        assert len(reservations) == 2

    def test_process_reservation_exception(self, real_db_session, real_redis):
        """Test reservation with insufficient stock"""
        unique_sku = f"TEST_TASK_ERR_{uuid.uuid4().hex[:8]}"
        unique_order_id = f"ORDER_TASK_ERR_{uuid.uuid4().hex[:8]}"
        
        # Create product and stock (insufficient)
        product = Product(sku=unique_sku, name="Test Product")
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
        
        # Try to reserve more than available, should raise exception
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            process_reservation(unique_order_id, [
                {"warehouse_id": "WH01", "product_id": product.id, "quantity": 5}
            ])
        
        assert "库存不足" in str(exc_info.value) or "预占失败" in str(exc_info.value)

    def test_cleanup_expired_reservations_success(self, real_db_session, real_redis):
        """Test successful cleanup of expired reservations"""
        unique_sku = f"TEST_CLEANUP_{uuid.uuid4().hex[:8]}"
        
        # Create product and stock
        product = Product(sku=unique_sku, name="Test Product")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=50,
            reserved_stock=10
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        # Create expired reservation
        expired_reservation = InventoryReservation(
            warehouse_id="WH01",
            order_id=f"ORDER_EXPIRED_{uuid.uuid4().hex[:8]}",
            product_id=product.id,
            quantity=5,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow() - timedelta(minutes=10)  # Expired
        )
        real_db_session.add(expired_reservation)
        real_db_session.commit()
        
        # Execute cleanup task
        result = cleanup_expired_reservations(batch_size=100)
        
        # Verify result
        assert "成功清理" in result or "cleaned" in result.lower()
        
        # Refresh session to see changes from other session
        real_db_session.expire_all()
        
        # Verify expired reservation status changed to RELEASED
        deleted_reservation = real_db_session.query(InventoryReservation).filter(
            InventoryReservation.order_id == expired_reservation.order_id
        ).first()
        print(f"Found reservation after cleanup: {deleted_reservation}, status: {deleted_reservation.status}")
        assert deleted_reservation.status == ReservationStatus.RELEASED

    def test_cleanup_expired_reservations_no_expired(self, real_db_session, real_redis):
        """Test cleanup when no expired reservations exist"""
        unique_sku = f"TEST_NOT_EXPIRED_{uuid.uuid4().hex[:8]}"
        
        # Create product and stock
        product = Product(sku=unique_sku, name="Test Product")
        real_db_session.add(product)
        real_db_session.flush()
        
        stock = ProductStock(
            warehouse_id="WH01",
            product_id=product.id,
            available_stock=50,
            reserved_stock=10
        )
        real_db_session.add(stock)
        real_db_session.commit()
        
        # Create valid (non-expired) reservation
        valid_reservation = InventoryReservation(
            warehouse_id="WH01",
            order_id=f"ORDER_VALID_{uuid.uuid4().hex[:8]}",
            product_id=product.id,
            quantity=5,
            status=ReservationStatus.RESERVED,
            expired_at=datetime.utcnow() + timedelta(hours=1)  # Expires in 1 hour
        )
        real_db_session.add(valid_reservation)
        real_db_session.commit()
        
        # Execute cleanup task
        result = cleanup_expired_reservations(batch_size=100)
        
        # Verify no records were cleaned
        assert "成功清理 0 条" in result or "cleaned 0" in result.lower() or "清理" not in result
        
        # Verify valid reservation still exists
        saved_reservation = real_db_session.query(InventoryReservation).filter(
            InventoryReservation.order_id == valid_reservation.order_id
        ).first()
        assert saved_reservation is not None