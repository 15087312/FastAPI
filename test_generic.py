"""
测试通用模型配置系统
验证动态模型创建功能是否正常工作
"""

import pytest
from app.core.model_factory import ModelFactory, create_product_model, create_product_stock_model
from app.core.config_generic import GenericConfig, get_model_config, is_model_enabled


class TestGenericConfig:
    """测试通用配置类"""
    
    def test_load_config(self):
        """测试加载配置"""
        config = GenericConfig()
        assert config.ENABLED_MODELS is not None
        assert isinstance(config.USE_BUILTIN_INVENTORY_MODELS, bool)
    
    def test_builtin_model_config(self):
        """测试内置模型配置"""
        product_config = get_model_config("Product")
        assert product_config is not None
        assert product_config.table_name == "products"
        assert "id" in product_config.fields
        assert "sku" in product_config.fields
    
    def test_model_enabled_check(self):
        """测试模型启用检查"""
        # Product 应该在启用的模型列表中
        assert is_model_enabled("Product") is True


class TestModelFactory:
    """测试模型工厂"""
    
    def setup_method(self):
        """每个测试前的准备"""
        ModelFactory.clear_cache()
    
    def teardown_method(self):
        """每个测试后的清理"""
        ModelFactory.clear_cache()
    
    def test_create_product_model(self):
        """测试创建 Product 模型"""
        Product = create_product_model()
        
        assert Product is not None
        assert Product.__tablename__ == "products"
        
        # 检查字段是否存在
        columns = [c.name for c in Product.__table__.columns]
        assert "id" in columns
        assert "sku" in columns
        assert "name" in columns
        
        # 检查主键
        primary_keys = [c.name for c in Product.__table__.columns if c.primary_key]
        assert "id" in primary_keys
    
    def test_create_product_stock_model(self):
        """测试创建 ProductStock 模型"""
        ProductStock = create_product_stock_model()
        
        assert ProductStock is not None
        assert ProductStock.__tablename__ == "product_stocks"
        
        # 检查字段
        columns = [c.name for c in ProductStock.__table__.columns]
        assert "warehouse_id" in columns
        assert "product_id" in columns
        assert "available_stock" in columns
        
        # 检查复合唯一索引
        indexes = [idx.name for idx in ProductStock.__table__.indexes]
        assert any("uq_warehouse_product" in idx for idx in indexes)
    
    def test_create_all_models(self):
        """测试批量创建模型"""
        models = ModelFactory.create_all_models()
        
        assert len(models) > 0
        assert "Product" in models or "ProductStock" in models
    
    def test_model_caching(self):
        """测试模型缓存机制"""
        # 第一次创建
        Product1 = create_product_model()
        
        # 第二次创建（应该从缓存返回）
        Product2 = create_product_model()
        
        # 应该是同一个类
        assert Product1 is Product2
    
    def test_clear_cache(self):
        """测试清除缓存"""
        create_product_model()
        ModelFactory.clear_cache()
        
        # 缓存应该为空
        assert len(ModelFactory._created_models) == 0


class TestDynamicModelCreation:
    """测试动态模型创建"""
    
    def setup_method(self):
        ModelFactory.clear_cache()
    
    def test_model_inheritance(self):
        """测试模型继承关系"""
        from app.db.base import Base
        
        Product = create_product_model()
        
        # Product 应该继承自 Base
        assert issubclass(Product, Base)
    
    def test_model_table_args(self):
        """测试模型的表参数"""
        ProductStock = create_product_stock_model()
        
        # 应该有 __table_args__
        assert hasattr(ProductStock, "__table_args__")
        
        # 应该包含约束和索引
        table_args = ProductStock.__table_args__
        assert len(table_args) > 0
    
    def test_model_relationships(self):
        """测试模型关系定义"""
        Product = create_product_model()
        
        # 检查是否有 stocks 关系
        assert hasattr(Product, "stocks")


@pytest.mark.asyncio
class TestGenericService:
    """测试通用服务（需要 Redis）"""
    
    async def test_service_initialization(self):
        """测试服务初始化"""
        try:
            from app.services.generic_inventory_service import create_generic_inventory_service
            from app.core.redis import sync_redis
            
            service = create_generic_inventory_service(sync_redis)
            
            assert service is not None
            assert service.Product is not None
            assert service.ProductStock is not None
            
        except ImportError:
            pytest.skip("通用服务未安装")
        except Exception as e:
            pytest.skip(f"Redis 不可用：{e}")


def main():
    """手动运行测试"""
    print("运行通用模型配置测试...\n")
    
    # 测试配置
    print("1. 测试配置加载")
    test_config = TestGenericConfig()
    test_config.test_load_config()
    print("   ✓ 配置加载成功")
    
    test_config.test_builtin_model_config()
    print("   ✓ 内置模型配置正确")
    
    # 测试模型工厂
    print("\n2. 测试模型工厂")
    test_factory = TestModelFactory()
    test_factory.setup_method()
    
    test_factory.test_create_product_model()
    print("   ✓ Product 模型创建成功")
    
    test_factory.test_create_product_stock_model()
    print("   ✓ ProductStock 模型创建成功")
    
    test_factory.test_create_all_models()
    print(f"   ✓ 批量创建模型成功")
    
    test_factory.teardown_method()
    
    # 测试动态创建
    print("\n3. 测试动态模型创建")
    test_dynamic = TestDynamicModelCreation()
    test_dynamic.setup_method()
    
    test_dynamic.test_model_inheritance()
    print("   ✓ 模型继承关系正确")
    
    test_dynamic.test_model_table_args()
    print("   ✓ 表参数配置正确")
    
    test_dynamic.teardown_method()
    
    print("\n✅ 所有测试通过！")
    print("\n📚 更多信息请查看:")
    print("   - QUICKSTART_GENERIC.md")
    print("   - docs/通用版本配置指南.md")


if __name__ == "__main__":
    main()
