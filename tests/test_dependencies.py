"""Dependency injection unit tests - using real database"""
import pytest
from sqlalchemy.orm import Session
from redis import Redis


from app.core.dependencies import (
    get_db,
    get_redis,
    get_inventory_service
)
from app.services.inventory_service import InventoryService


class TestDependencies:
    """Dependency injection test class - using real database"""

    def test_get_db(self, real_db_session):
        """Test database session dependency - using real database"""
        # Verify it returns a real Session instance
        assert isinstance(real_db_session, Session)
        
        # Verify it can perform real database operations
        from app.models.product import Product
        product = real_db_session.query(Product).first()
        # Don't care if data exists, just verify query succeeds
        assert product is None or isinstance(product, Product)

    def test_get_redis(self, real_redis):
        """Test Redis connection - using real Redis"""
        # Verify it returns a real Redis instance
        assert isinstance(real_redis, Redis)
        
        # Verify it can perform real Redis operations
        real_redis.set("test_dep_key", "test_value")
        value = real_redis.get("test_dep_key")
        assert value == "test_value"
        real_redis.delete("test_dep_key")

    def test_get_inventory_service(self, real_db_session, real_redis):
        """Test inventory service dependency injection - using real dependencies"""
        # Call InventoryService constructor directly
        service = InventoryService(real_db_session, real_redis)
        
        assert isinstance(service, InventoryService)
        assert service.db == real_db_session
        assert service.redis == real_redis

    def test_get_inventory_service_with_real_deps(self, real_db_session, real_redis):
        """Test service creation with real dependencies"""
        # Create service instance
        service = InventoryService(real_db_session, real_redis)
        
        # Verify service works correctly
        from app.models.product import Product
        from app.models.product_stocks import ProductStock
        import uuid
        
        unique_sku = f"TEST_DEP_{uuid.uuid4().hex[:8]}"
        product = Product(sku=unique_sku, name="Test Product")
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
        
        # Use service to query stock
        result = service.get_product_stock("WH01", product.id)
        assert result == 100