"""
动态模型工厂 - 根据配置动态创建 SQLAlchemy 模型
使用方法：
1. 在 config_generic.py 中配置模型
2. 使用 ModelFactory.create_model() 创建模型
3. 或在 .env 中设置 CUSTOM_MODEL_CONFIG_PATH 指向 JSON 配置文件
"""

from typing import Dict, Any, Optional, List, Type
from sqlalchemy import Column, BigInteger, Integer, String, TIMESTAMP, text, Index, CheckConstraint, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import relationship
import logging

from app.db.base import Base
from app.core.config_generic import (
    GenericConfig, 
    ModelConfig, 
    ModelFieldConfig,
    get_model_config,
    is_model_enabled,
    BUILTIN_MODEL_CONFIGS
)

logger = logging.getLogger(__name__)


class ModelFactory:
    """模型工厂类 - 用于动态创建模型"""
    
    # 缓存已创建的模型类
    _created_models: Dict[str, Type] = {}
    
    @classmethod
    def create_model(cls, model_name: str, use_builtin: bool = True) -> Optional[Type]:
        """
        创建或获取模型类
        
        Args:
            model_name: 模型名称（如 "Product", "ProductStock"）
            use_builtin: 是否使用内置配置
            
        Returns:
            模型类，如果不存在则返回 None
        """
        # 检查是否已创建
        if model_name in cls._created_models:
            logger.debug(f"模型 {model_name} 已存在，直接返回")
            return cls._created_models[model_name]
        
        # 检查模型是否启用
        if not is_model_enabled(model_name):
            logger.warning(f"模型 {model_name} 未启用")
            return None
        
        # 获取模型配置
        config = get_model_config(model_name)
        
        if config is None:
            logger.error(f"找不到模型 {model_name} 的配置")
            return None
        
        # 动态创建模型
        try:
            model_class = cls._create_model_from_config(model_name, config)
            cls._created_models[model_name] = model_class
            logger.info(f"成功创建模型 {model_name}")
            return model_class
        except Exception as e:
            logger.error(f"创建模型 {model_name} 失败：{e}")
            return None
    
    @classmethod
    def _create_model_from_config(cls, model_name: str, config: ModelConfig) -> Type:
        """从配置创建模型类"""
        
        # 构建属性字典
        attrs: Dict[str, Any] = {
            "__tablename__": config.table_name,
        }
        
        # 字段类型映射
        TYPE_MAP = {
            "BigInteger": BigInteger,
            "Integer": Integer,
            "String": String,
            "TIMESTAMP": lambda: TIMESTAMP(timezone=True),
            "Boolean": Boolean,
            "Float": Float,
            "Text": Text,
        }
        
        # 添加字段
        for field_name, field_config in config.fields.items():
            column_type = TYPE_MAP.get(field_config.type)
            
            if column_type is None:
                logger.warning(f"未知的字段类型 {field_config.type}，跳过字段 {field_name}")
                continue
            
            # 处理可调用类型（如 TIMESTAMP）
            if callable(column_type):
                column_type = column_type()
            
            # 处理 String 类型的 max_length
            if field_config.type == "String" and field_config.max_length:
                column_type = String(field_config.max_length)
            
            # 处理外键
            if field_config.foreign_key:
                column_type = ForeignKey(field_config.foreign_key, ondelete="CASCADE")
            
            # 创建 Column 的参数
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
            if field_config.onupdate:
                column_kwargs["onupdate"] = text(field_config.onupdate)
            if field_config.comment:
                column_kwargs["comment"] = field_config.comment
            if field_config.index:
                column_kwargs["index"] = True
            if field_config.unique:
                column_kwargs["unique"] = True
            
            # 创建列
            attrs[field_name] = Column(column_type, **column_kwargs)
        
        # 处理约束和索引
        table_args = []
        
        # 添加复合索引
        if config.indexes:
            for idx in config.indexes:
                index_fields = idx.get("fields", [])
                if index_fields:
                    unique = idx.get("unique", False)
                    index_name = idx.get("name", f"idx_{'_'.join(index_fields)}")
                    table_args.append(
                        Index(index_name, *index_fields, unique=unique)
                    )
        
        # 添加约束
        if config.constraints:
            for constraint in config.constraints:
                ctype = constraint.get("type")
                if ctype == "unique_index":
                    fields = constraint.get("fields", [])
                    if fields:
                        table_args.append(
                            Index(
                                f"uq_{'_'.join(fields)}",
                                *fields,
                                unique=True
                            )
                        )
                elif ctype == "check":
                    expression = constraint.get("expression")
                    if expression:
                        table_args.append(
                            CheckConstraint(expression, name=constraint.get("name"))
                        )
        
        if table_args:
            attrs["__table_args__"] = tuple(table_args)
        
        # 动态创建类
        model_class = type(model_name, (Base,), attrs)
        
        return model_class
    
    @classmethod
    def create_all_models(cls) -> Dict[str, Type]:
        """创建所有启用的模型"""
        generic_config = GenericConfig()
        enabled_models = [m.strip() for m in generic_config.ENABLED_MODELS.split(",")]
        
        created = {}
        for model_name in enabled_models:
            model_class = cls.create_model(model_name)
            if model_class:
                created[model_name] = model_class
        
        return created
    
    @classmethod
    def clear_cache(cls):
        """清除模型缓存"""
        cls._created_models.clear()
        logger.info("模型工厂缓存已清除")
    
    @classmethod
    def create_all_models(cls) -> Dict[str, Type]:
        """创建所有启用的模型"""
        generic_config = GenericConfig()
        enabled_models = [m.strip() for m in generic_config.ENABLED_MODELS.split(",")]
        
        created = {}
        for model_name in enabled_models:
            model_class = cls.create_model(model_name)
            if model_class:
                created[model_name] = model_class
        
        return created
    
    @classmethod
    def clear_cache(cls):
        """清除模型缓存"""
        cls._created_models.clear()
        logger.info("模型工厂缓存已清除")


# ==================== 快速创建模型的便捷函数 ====================

def create_product_model() -> Optional[Type]:
    """创建 Product 模型"""
    return ModelFactory.create_model("Product")


def create_product_stock_model() -> Optional[Type]:
    """创建 ProductStock 模型"""
    return ModelFactory.create_model("ProductStock")


def create_inventory_reservation_model() -> Optional[Type]:
    """创建 InventoryReservation 模型"""
    return ModelFactory.create_model("InventoryReservation")


def create_inventory_log_model() -> Optional[Type]:
    """创建 InventoryLog 模型"""
    return ModelFactory.create_model("InventoryLog")


def create_idempotency_key_model() -> Optional[Type]:
    """创建 IdempotencyKey 模型"""
    return ModelFactory.create_model("IdempotencyKey")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例 1：创建单个模型
    print("示例 1：创建单个模型")
    Product = create_product_model()
    if Product:
        print(f"Product 表名：{Product.__tablename__}")
    
    # 示例 2：创建所有启用的模型
    print("\n示例 2：创建所有启用的模型")
    models = ModelFactory.create_all_models()
    for name, model in models.items():
        print(f"  - {name}: {model.__tablename__}")
    
    # 示例 3：自定义模型
    print("\n示例 3：使用自定义配置")
    # 需要在 .env 中设置 CUSTOM_MODEL_CONFIG_PATH
