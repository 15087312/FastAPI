"""
通用配置模块 - 允许通过配置文件自定义模型和业务逻辑
使用方法：
1. 复制此文件为 config_generic.py
2. 根据实际情况修改 MODEL_CONFIG 配置
3. 在 .env 文件中设置 GENERIC_CONFIG_PATH 指向配置文件
"""

import os
import importlib
from typing import Dict, Any, Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


class ModelFieldConfig(BaseSettings):
    """模型字段配置"""
    type: str = "BigInteger"  # 字段类型：BigInteger, Integer, String, TIMESTAMP, etc.
    nullable: bool = False
    default: Optional[Any] = None
    primary_key: bool = False
    index: bool = False
    unique: bool = False
    comment: str = ""
    max_length: Optional[int] = None  # String 类型需要
    foreign_key: Optional[str] = None  # 外键关系
    autoincrement: bool = False
    server_default: Optional[str] = None  # 数据库默认值
    onupdate: Optional[str] = None  # 更新时的默认值


class ModelConfig(BaseSettings):
    """模型配置"""
    table_name: str
    fields: Dict[str, ModelFieldConfig] = {}
    relationships: Dict[str, str] = {}  # 关系定义：{关系名："目标模型。关系类型"}
    constraints: List[Dict[str, Any]] = []  # 约束条件
    indexes: List[Dict[str, Any]] = []  # 索引定义


class GenericConfig(BaseSettings):
    """通用配置类"""
    
    # ==================== 模型配置 ====================
    # 启用哪些模型（逗号分隔）
    ENABLED_MODELS: str = "Product,ProductStock,InventoryReservation,InventoryLog,IdempotencyKey"
    
    # 自定义模型配置路径（可选，JSON 或 YAML 文件）
    CUSTOM_MODEL_CONFIG_PATH: Optional[str] = None
    
    # 是否使用内置的库存相关模型
    USE_BUILTIN_INVENTORY_MODELS: bool = True
    
    # 是否使用自定义模型
    USE_CUSTOM_MODELS: bool = False
    
    # ==================== 业务逻辑配置 ====================
    # 库存操作类型
    INVENTORY_OPERATION_TYPES: str = "increase,decrease,freeze,unfreeze,reserve,confirm,release"
    
    # 是否启用 Kafka 异步同步
    ENABLE_KAFKA_SYNC: bool = False
    
    # 是否启用 Redis 缓存
    ENABLE_REDIS_CACHE: bool = True
    
    # 是否启用布隆过滤器
    ENABLE_BLOOM_FILTER: bool = True
    
    # 是否启用幂等性检查
    ENABLE_IDEMPOTENCY: bool = True
    
    # ==================== 性能配置 ====================
    # Redis 缓存过期时间（秒），0 表示永不过期
    REDIS_CACHE_TTL: int = 0
    
    # 批量操作最大数量
    BATCH_OPERATION_MAX_SIZE: int = 100
    
    # 是否启用 Lua 脚本预注册
    PRE_REGISTER_LUA_SCRIPTS: bool = True
    
    # ==================== 日志配置 ====================
    # 是否记录详细的操作日志
    LOG_OPERATIONS: bool = True
    
    # 日志级别
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        extra = "ignore"


# ==================== 内置模型配置示例 ====================

BUILTIN_MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "Product": ModelConfig(
        table_name="products",
        fields={
            "id": ModelFieldConfig(
                type="BigInteger",
                primary_key=True,
                autoincrement=True
            ),
            "sku": ModelFieldConfig(
                type="String",
                max_length=64,
                nullable=False,
                unique=True,
                comment="商品唯一 SKU"
            ),
            "name": ModelFieldConfig(
                type="String",
                max_length=255,
                nullable=False,
                comment="商品名称"
            ),
            "description": ModelFieldConfig(
                type="String",
                max_length=2000,
                nullable=True,
                comment="商品描述"
            ),
            "price": ModelFieldConfig(
                type="Integer",
                nullable=False,
                default=0,
                comment="商品价格（分）"
            ),
            "created_at": ModelFieldConfig(
                type="TIMESTAMP",
                nullable=False,
                server_default="now()"
            ),
            "updated_at": ModelFieldConfig(
                type="TIMESTAMP",
                nullable=False,
                server_default="now()",
                onupdate="now()"
            )
        },
        relationships={
            "stocks": "ProductStock.one-to-many",
            "reservations": "InventoryReservation.many-to-one"
        }
    ),
    
    "ProductStock": ModelConfig(
        table_name="product_stocks",
        fields={
            "id": ModelFieldConfig(
                type="BigInteger",
                primary_key=True,
                autoincrement=True,
                comment="主键 ID"
            ),
            "warehouse_id": ModelFieldConfig(
                type="String",
                max_length=32,
                nullable=False,
                index=True,
                comment="仓库 ID"
            ),
            "product_id": ModelFieldConfig(
                type="BigInteger",
                nullable=False,
                index=True,
                foreign_key="products.id",
                comment="商品 ID"
            ),
            "available_stock": ModelFieldConfig(
                type="Integer",
                nullable=False,
                default=0,
                comment="可用库存"
            ),
            "reserved_stock": ModelFieldConfig(
                type="Integer",
                nullable=False,
                default=0,
                comment="预占库存"
            ),
            "frozen_stock": ModelFieldConfig(
                type="Integer",
                nullable=False,
                default=0,
                comment="冻结库存"
            ),
            "safety_stock": ModelFieldConfig(
                type="Integer",
                nullable=False,
                default=0,
                comment="安全库存"
            ),
            "created_at": ModelFieldConfig(
                type="TIMESTAMP",
                nullable=False,
                server_default="now()"
            ),
            "updated_at": ModelFieldConfig(
                type="TIMESTAMP",
                nullable=False,
                server_default="now()",
                onupdate="now()"
            )
        },
        constraints=[
            {"type": "unique_index", "fields": ["warehouse_id", "product_id"]},
            {"type": "check", "expression": "available_stock >= 0"},
            {"type": "check", "expression": "reserved_stock >= 0"},
            {"type": "check", "expression": "frozen_stock >= 0"},
            {"type": "check", "expression": "safety_stock >= 0"}
        ]
    )
}


def load_generic_config() -> GenericConfig:
    """加载通用配置"""
    return GenericConfig()


def get_model_config(model_name: str) -> Optional[ModelConfig]:
    """获取模型配置"""
    generic_config = load_generic_config()
    
    # 如果启用了内置模型配置
    if generic_config.USE_BUILTIN_INVENTORY_MODELS:
        return BUILTIN_MODEL_CONFIGS.get(model_name)
    
    # 从自定义配置文件加载
    if generic_config.CUSTOM_MODEL_CONFIG_PATH:
        try:
            import json
            with open(generic_config.CUSTOM_MODEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                custom_configs = json.load(f)
                if model_name in custom_configs:
                    return ModelConfig(**custom_configs[model_name])
        except Exception as e:
            print(f"加载自定义模型配置失败：{e}")
    
    return None


def is_model_enabled(model_name: str) -> bool:
    """检查模型是否启用"""
    generic_config = load_generic_config()
    enabled_models = [m.strip() for m in generic_config.ENABLED_MODELS.split(",")]
    return model_name in enabled_models


# ==================== 动态模型创建工具函数 ====================

def create_dynamic_model(model_name: str, base_class: Any, config: ModelConfig) -> Any:
    """
    动态创建 SQLAlchemy 模型类
    
    Args:
        model_name: 模型名称
        base_class: SQLAlchemy Base 类
        config: 模型配置
    
    Returns:
        动态创建的模型类
    """
    from sqlalchemy import Column, BigInteger, Integer, String, TIMESTAMP, text, Index, CheckConstraint, ForeignKey
    
    # 字段类型映射
    TYPE_MAP = {
        "BigInteger": BigInteger,
        "Integer": Integer,
        "String": String,
        "TIMESTAMP": TIMESTAMP,
        "Boolean": None,  # 需要特殊处理
        "Float": None,    # 需要特殊处理
        "Text": None,     # 需要特殊处理
    }
    
    # 构建属性字典
    attrs = {
        "__tablename__": config.table_name,
        "__table_args__": tuple(config.constraints) if config.constraints else ()
    }
    
    # 添加字段
    for field_name, field_config in config.fields.items():
        column_type = TYPE_MAP.get(field_config.type)
        
        if column_type is None:
            print(f"警告：未知的字段类型 {field_config.type}，跳过字段 {field_name}")
            continue
        
        # 处理 String 类型的 max_length
        if field_config.type == "String" and field_config.max_length:
            column_type = String(field_config.max_length)
        
        # 处理外键
        if field_config.foreign_key:
            column_type = ForeignKey(field_config.foreign_key)
        
        # 创建 Column
        column_kwargs = {
            "nullable": field_config.nullable,
        }
        
        if field_config.primary_key:
            column_kwargs["primary_key"] = True
        if field_config.autoincrement:
            column_kwargs["autoincrement"] = True
        if field_config.default is not None:
            column_kwargs["default"] = field_config.default
        if field_config.server_default:
            column_kwargs["server_default"] = text(field_config.server_default)
        if field_config.comment:
            column_kwargs["comment"] = field_config.comment
        
        attrs[field_name] = Column(column_type, **column_kwargs)
    
    # 动态创建类
    model_class = type(model_name, (base_class,), attrs)
    
    return model_class


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例：加载配置
    config = load_generic_config()
    print(f"启用的模型：{config.ENABLED_MODELS}")
    print(f"使用内置模型：{config.USE_BUILTIN_INVENTORY_MODELS}")
    
    # 示例：获取 Product 模型配置
    product_config = get_model_config("Product")
    if product_config:
        print(f"\nProduct 表名：{product_config.table_name}")
        print(f"Product 字段：{list(product_config.fields.keys())}")
    
    # 示例：检查模型是否启用
    print(f"\nProduct 模型已启用：{is_model_enabled('Product')}")
    print(f"CustomModel 模型已启用：{is_model_enabled('CustomModel')}")
