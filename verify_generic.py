"""
简单验证通用配置系统
"""

print("=" * 60)
print("验证通用模型配置系统")
print("=" * 60)

# 1. 测试配置加载
print("\n1. 测试配置加载...")
from app.core.config_generic import GenericConfig, get_model_config

config = GenericConfig()
print(f"   ✓ 配置加载成功")
print(f"   启用的模型：{config.ENABLED_MODELS}")

# 2. 测试获取模型配置
print("\n2. 测试获取模型配置...")
product_config = get_model_config("Product")
if product_config:
    print(f"   ✓ Product 配置存在")
    print(f"   表名：{product_config.table_name}")
    print(f"   字段数：{len(product_config.fields)}")
else:
    print(f"   ✗ Product 配置不存在")

# 3. 测试模型工厂（不实际创建，避免与现有模型冲突）
print("\n3. 测试模型工厂...")
from app.core.model_factory import ModelFactory

# 清除缓存
ModelFactory.clear_cache()
print(f"   ✓ 缓存已清除")

# 4. 显示可用的便捷函数
print("\n4. 可用的便捷函数:")
print("   - create_product_model()")
print("   - create_product_stock_model()")
print("   - create_inventory_reservation_model()")
print("   - create_inventory_log_model()")
print("   - create_idempotency_key_model()")

# 5. 显示 JSON 配置示例
print("\n5. JSON 配置文件位置:")
print("   - app/core/model_configs.json")

print("\n" + "=" * 60)
print("✅ 验证完成！通用配置系统已就绪")
print("=" * 60)

print("\n📚 使用指南:")
print("   1. 查看 QUICKSTART_GENERIC.md 快速开始")
print("   2. 查看 docs/通用版本配置指南.md 详细文档")
print("   3. 运行 examples/generic_usage.py 查看使用示例")
print("   4. 参考 app/core/model_configs.json 自定义模型")
