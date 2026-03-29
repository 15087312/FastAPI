"""
通用库存服务 - 基于动态模型，可适配不同业务场景
使用方法：
1. 在 config_generic.py 中配置要使用的模型
2. 或使用 JSON 配置文件定义模型结构
3. 服务会自动使用动态创建的模型
"""

import logging
from typing import Optional, List, Dict, Any
from redis import Redis

from app.core.model_factory import (
    create_product_model,
    create_product_stock_model,
    create_inventory_reservation_model,
    ModelFactory
)
from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_query import InventoryQueryService
from app.services.inventory_operation import InventoryOperationService
from app.services.inventory_reservation import InventoryReservationService

logger = logging.getLogger(__name__)


class GenericInventoryService:
    """
    通用库存服务 Facade
    支持动态模型配置，可适配不同的业务场景
    """
    
    def __init__(self, redis: Redis = None):
        self.redis = redis
        
        # 动态加载模型
        self.Product = create_product_model()
        self.ProductStock = create_product_stock_model()
        self.InventoryReservation = create_inventory_reservation_model()
        
        # 验证模型是否成功加载
        if not all([self.Product, self.ProductStock]):
            logger.error("关键模型加载失败，请检查配置")
            raise RuntimeError("模型加载失败")
        
        # 初始化缓存服务
        self.cache_service = InventoryCacheService(redis)
        
        # 初始化子服务
        self.query_service = InventoryQueryService(self.cache_service)
        self.operation_service = InventoryOperationService(self.cache_service)
        self.reservation_service = InventoryReservationService(self.cache_service)
        
        logger.info(f"通用库存服务初始化完成")
        logger.info(f"使用模型：Product={self.Product.__tablename__}, ProductStock={self.ProductStock.__tablename__}")
    
    # ==================== 查询服务 ====================
    
    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（纯 Redis）"""
        return self.query_service.get_product_stock(warehouse_id, product_id)
    
    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（纯 Redis）"""
        return self.query_service.get_full_stock_info(warehouse_id, product_id)
    
    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> Dict[int, int]:
        """批量获取库存（纯 Redis）"""
        return self.query_service.batch_get_stocks(warehouse_id, product_ids)
    
    # ==================== 操作服务 ====================
    
    def increase_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: Optional[str] = None,
        operator: Optional[str] = None,
        remark: Optional[str] = None,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """入库/补货"""
        return self.operation_service.increase_stock(
            warehouse_id, product_id, quantity, order_id, operator, remark, source
        )
    
    def adjust_stock(
        self,
        warehouse_id: str,
        product_id: int,
        adjust_type: str,
        quantity: int,
        reason: str,
        operator: Optional[str] = None,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """库存调整（增加/减少/设置）"""
        return self.operation_service.adjust_stock(
            warehouse_id, product_id, adjust_type, quantity, reason, operator, source
        )
    
    def freeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """冻结库存"""
        return self.operation_service.freeze_stock(warehouse_id, product_id, quantity, reason, operator)
    
    def unfreeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """解冻库存"""
        return self.operation_service.unfreeze_stock(warehouse_id, product_id, quantity, reason, operator)
    
    # ==================== 预占服务 ====================
    
    def reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> bool:
        """预占库存"""
        return self.reservation_service.reserve_stock(warehouse_id, product_id, quantity, order_id)
    
    def reserve_batch(
        self,
        order_id: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量预占库存"""
        return self.reservation_service.reserve_batch(order_id, items)
    
    def confirm_stock(self, order_id: str) -> bool:
        """确认库存"""
        return self.reservation_service.confirm_stock(order_id)
    
    def release_stock(self, order_id: str) -> bool:
        """释放库存"""
        return self.reservation_service.release_stock(order_id)
    
    # ==================== 数据库操作（可选） ====================
    
    def sync_to_database(self, warehouse_id: str, product_id: int, db_session):
        """
        将 Redis 中的库存数据同步到数据库
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            db_session: SQLAlchemy Session
        """
        from sqlalchemy import select
        
        # 从 Redis 获取完整库存信息
        stock_info = self.get_full_stock_info(warehouse_id, product_id)
        
        if not stock_info:
            logger.warning(f"Redis 中没有 {warehouse_id}:{product_id} 的库存信息")
            return
        
        # 查询数据库中是否存在
        stmt = select(self.ProductStock).where(
            self.ProductStock.warehouse_id == warehouse_id,
            self.ProductStock.product_id == product_id
        )
        stock_record = db_session.execute(stmt).scalar_one_or_none()
        
        if stock_record:
            # 更新现有记录
            stock_record.available_stock = stock_info["available_stock"]
            stock_record.reserved_stock = stock_info["reserved_stock"]
            stock_record.frozen_stock = stock_info["frozen_stock"]
            stock_record.safety_stock = stock_info["safety_stock"]
            logger.info(f"更新数据库库存：{warehouse_id}:{product_id}")
        else:
            # 创建新记录
            new_stock = self.ProductStock(
                warehouse_id=warehouse_id,
                product_id=product_id,
                available_stock=stock_info["available_stock"],
                reserved_stock=stock_info["reserved_stock"],
                frozen_stock=stock_info["frozen_stock"],
                safety_stock=stock_info["safety_stock"]
            )
            db_session.add(new_stock)
            logger.info(f"创建数据库库存：{warehouse_id}:{product_id}")
        
        db_session.commit()


# ==================== 工厂函数 ====================

def create_generic_inventory_service(redis: Redis = None) -> GenericInventoryService:
    """创建通用库存服务实例"""
    return GenericInventoryService(redis)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例：使用通用服务
    from app.core.redis import sync_redis
    
    try:
        service = create_generic_inventory_service(sync_redis)
        
        # 查询库存
        stock = service.get_product_stock("WH001", 980)
        print(f"可用库存：{stock}")
        
        # 获取完整信息
        info = service.get_full_stock_info("WH001", 980)
        print(f"完整信息：{info}")
        
        # 预占库存
        success = service.reserve_stock("WH001", 980, 5, "ORDER_001")
        print(f"预占结果：{success}")
        
    except Exception as e:
        print(f"服务调用失败：{e}")
