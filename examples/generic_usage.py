"""
通用模型配置使用示例
演示如何使用动态模型系统适配不同的业务场景
"""

from app.core.model_factory import ModelFactory, create_product_model
from app.core.config_generic import GenericConfig
import json


def example_1_builtin_models():
    """示例 1：使用内置模型"""
    print("=" * 60)
    print("示例 1：使用内置模型")
    print("=" * 60)
    
    # 创建 Product 模型
    Product = create_product_model()
    
    if Product:
        print(f"✓ Product 模型创建成功")
        print(f"  表名：{Product.__tablename__}")
        print(f"  字段：{[c.name for c in Product.__table__.columns]}")
    else:
        print("✗ Product 模型创建失败，请检查配置")


def example_2_custom_config():
    """示例 2：使用自定义 JSON 配置"""
    print("\n" + "=" * 60)
    print("示例 2：使用自定义 JSON 配置")
    print("=" * 60)
    
    # 修改配置使用自定义模型
    from dotenv import load_dotenv
    import os
    
    # 设置使用自定义模型
    os.environ["USE_CUSTOM_MODELS"] = "True"
    os.environ["CUSTOM_MODEL_CONFIG_PATH"] = "app/core/model_configs.json"
    
    # 重新加载配置（实际使用时建议重启应用）
    ModelFactory.clear_cache()
    
    # 创建 Warehouse 模型
    Warehouse = ModelFactory.create_model("Warehouse")
    
    if Warehouse:
        print(f"✓ Warehouse 模型创建成功")
        print(f"  表名：{Warehouse.__tablename__}")
        print(f"  主键：{[c.name for c in Warehouse.__table__.columns if c.primary_key]}")
        print(f"  索引：{[c.name for c in Warehouse.__table__.columns if c.index]}")
    else:
        print("✗ Warehouse 模型创建失败")


def example_3_dynamic_creation():
    """示例 3：动态创建所有启用的模型"""
    print("\n" + "=" * 60)
    print("示例 3：批量创建模型")
    print("=" * 60)
    
    # 清除缓存
    ModelFactory.clear_cache()
    
    # 创建所有启用的模型
    models = ModelFactory.create_all_models()
    
    print(f"成功创建 {len(models)} 个模型:")
    for name, model_class in models.items():
        print(f"  - {name}: {model_class.__tablename__}")


def example_4_database_operations():
    """示例 4：使用动态模型进行数据库操作"""
    print("\n" + "=" * 60)
    print("示例 4：数据库操作示例")
    print("=" * 60)
    
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.db.base import Base
        
        # 创建模型
        Product = create_product_model()
        
        if not Product:
            print("✗ 模型创建失败")
            return
        
        # 创建测试数据库（内存数据库）
        engine = create_engine("sqlite:///:memory:", echo=True)
        Base.metadata.create_all(engine)
        
        # 插入测试数据
        with Session(engine) as session:
            new_product = Product(
                sku="TEST001",
                name="测试商品",
                description="这是一个测试商品",
                price=9900  # 99 元
            )
            session.add(new_product)
            session.commit()
            
            print(f"✓ 成功插入商品：{new_product.id}")
        
        # 查询数据
        with Session(engine) as session:
            stmt = select(Product).where(Product.sku == "TEST001")
            product = session.execute(stmt).scalar_one_or_none()
            
            if product:
                print(f"✓ 查询成功：{product.name} (SKU: {product.sku})")
            else:
                print("✗ 查询失败")
    
    except Exception as e:
        print(f"✗ 数据库操作失败：{e}")


def example_5_generic_service():
    """示例 5：使用通用库存服务"""
    print("\n" + "=" * 60)
    print("示例 5：通用服务使用")
    print("=" * 60)
    
    try:
        from app.services.generic_inventory_service import create_generic_inventory_service
        
        # 注意：实际使用需要 Redis 连接
        # 这里仅演示 API
        print("API 使用示例:")
        print("""
# 创建服务实例
service = create_generic_inventory_service(redis_client)

# 查询库存
stock = service.get_product_stock("WH001", 980)

# 预占库存
success = service.reserve_stock("WH001", 980, 5, "ORDER_001")

# 批量预占
items = [
    {"warehouse_id": "WH001", "product_id": 980, "quantity": 5},
    {"warehouse_id": "WH001", "product_id": 981, "quantity": 3}
]
result = service.reserve_batch("ORDER_002", items)

# 确认库存
service.confirm_stock("ORDER_001")

# 释放库存
service.release_stock("ORDER_001")
        """)
        
        print("✓ 更多用法请参考 docs/通用版本配置指南.md")
    
    except ImportError as e:
        print(f"✗ 导入失败：{e}")


def example_6_config_validation():
    """示例 6：配置验证"""
    print("\n" + "=" * 60)
    print("示例 6：配置验证")
    print("=" * 60)
    
    # 加载配置
    config = GenericConfig()
    
    print(f"当前配置:")
    print(f"  启用的模型：{config.ENABLED_MODELS}")
    print(f"  使用内置模型：{config.USE_BUILTIN_INVENTORY_MODELS}")
    print(f"  使用自定义模型：{config.USE_CUSTOM_MODELS}")
    print(f"  自定义配置路径：{config.CUSTOM_MODEL_CONFIG_PATH}")
    print(f"  启用 Redis 缓存：{config.ENABLE_REDIS_CACHE}")
    print(f"  启用布隆过滤器：{config.ENABLE_BLOOM_FILTER}")
    print(f"  启用幂等性：{config.ENABLE_IDEMPOTENCY}")


def main():
    """运行所有示例"""
    print("\n🚀 通用模型配置系统 - 使用示例\n")
    
    # 运行示例
    example_1_builtin_models()
    example_2_custom_config()
    example_3_dynamic_creation()
    example_4_database_operations()
    example_5_generic_service()
    example_6_config_validation()
    
    print("\n" + "=" * 60)
    print("📚 更多信息请查看:")
    print("  - docs/通用版本配置指南.md")
    print("  - app/core/config_generic.py")
    print("  - app/core/model_factory.py")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
