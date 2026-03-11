"""
初始化测试数据脚本

在应用启动时自动创建测试产品和库存数据
"""
import logging
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_stocks import ProductStock

logger = logging.getLogger(__name__)

# 测试仓库列表
TEST_WAREHOUSES = ["WH01", "WH02", "WH03"]

# 测试产品数据
TEST_PRODUCTS = [
    {"sku": "SKU001", "name": "iPhone 15 Pro", "initial_stock": 100},
    {"sku": "SKU002", "name": "MacBook Pro 14寸", "initial_stock": 50},
    {"sku": "SKU003", "name": "AirPods Pro 2", "initial_stock": 200},
    {"sku": "SKU004", "name": "iPad Air", "initial_stock": 80},
    {"sku": "SKU005", "name": "Apple Watch S9", "initial_stock": 120},
    {"sku": "SKU006", "name": "华为 Mate 60", "initial_stock": 60},
    {"sku": "SKU007", "name": "小米14 Ultra", "initial_stock": 70},
    {"sku": "SKU008", "name": "三星 S24 Ultra", "initial_stock": 40},
    {"sku": "SKU009", "name": "ThinkPad X1 Carbon", "initial_stock": 30},
    {"sku": "SKU010", "name": "Dell XPS 15", "initial_stock": 25},
]


def init_test_data() -> bool:
    """
    初始化测试数据
    
    Returns:
        bool: 是否成功初始化数据
    """
    db: Session = SessionLocal()
    try:
        # 检查是否已有产品数据
        existing_count = db.execute(select(Product).limit(1)).scalar_one_or_none()
        if existing_count is not None:
            logger.info("产品数据已存在，跳过初始化")
            return True
        
        logger.info("开始初始化测试数据...")
        
        # 插入产品数据
        product_ids = []
        for product_data in TEST_PRODUCTS:
            product = Product(
                sku=product_data["sku"],
                name=product_data["name"]
            )
            db.add(product)
            db.flush()  # 获取 product.id
            product_ids.append((product.id, product_data["initial_stock"]))
            logger.info(f"创建产品: {product.sku} - {product.name}")
        
        # 插入库存数据（为每个产品在每个仓库创建库存记录）
        for product_id, initial_stock in product_ids:
            for warehouse_id in TEST_WAREHOUSES:
                # 为主仓库设置初始库存，其他仓库设置较少库存
                stock_amount = initial_stock if warehouse_id == "WH01" else initial_stock // 2
                
                stock = ProductStock(
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    available_stock=stock_amount,
                    reserved_stock=0,
                    frozen_stock=0,
                    safety_stock=10
                )
                db.add(stock)
                logger.info(f"创建库存: product_id={product_id}, warehouse={warehouse_id}, stock={stock_amount}")
        
        db.commit()
        logger.info(f"测试数据初始化完成: {len(TEST_PRODUCTS)} 个产品, {len(TEST_WAREHOUSES)} 个仓库")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"初始化测试数据失败: {e}")
        return False
    finally:
        db.close()


def check_and_init_data():
    """检查并初始化数据（带错误处理）"""
    try:
        init_test_data()
    except Exception as e:
        logger.warning(f"初始化测试数据时出错: {e}")
        # 不阻断应用启动
