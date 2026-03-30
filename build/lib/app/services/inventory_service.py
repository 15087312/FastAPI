"""库存服务 Facade - 纯Redis操作，无数据库依赖"""

import logging
from typing import Optional, List, Dict, Any
from redis import Redis

from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_query import InventoryQueryService
from app.services.inventory_operation import InventoryOperationService
from app.services.inventory_reservation import InventoryReservationService

logger = logging.getLogger(__name__)

# 全局缓存服务实例（复用，避免每次创建）
_global_cache_service: Optional[InventoryCacheService] = None


def get_global_cache_service(redis: Redis = None) -> InventoryCacheService:
    """获取全局缓存服务实例（单例模式）"""
    global _global_cache_service
    
    if _global_cache_service is None:
        _global_cache_service = InventoryCacheService(redis)
        logger.debug("创建全局缓存服务实例")
    elif redis is not None and _global_cache_service.redis is None:
        _global_cache_service.redis = redis
    
    return _global_cache_service


class InventoryService:
    """库存服务 Facade - 统一入口，纯Redis操作"""

    def __init__(self, redis: Redis = None):
        self.redis = redis

        # 复用全局缓存服务
        self.cache_service = get_global_cache_service(redis)

        # 初始化子服务（纯Redis操作）
        self.query_service = InventoryQueryService(self.cache_service)
        self.operation_service = InventoryOperationService(self.cache_service)
        self.reservation_service = InventoryReservationService(self.cache_service)

    # ==================== 缓存相关 ====================

    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return self.cache_service._get_cache_key(warehouse_id, product_id)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效库存缓存"""
        self.cache_service.invalidate_cache(warehouse_id, product_id)

    # ==================== 查询服务代理 ====================

    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（纯Redis）"""
        return self.query_service.get_product_stock(warehouse_id, product_id)

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（纯Redis）"""
        return self.query_service.get_full_stock_info(warehouse_id, product_id)

    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> Dict[int, int]:
        """批量获取库存（纯Redis）"""
        return self.query_service.batch_get_stocks(warehouse_id, product_ids)

    # ==================== 操作服务代理 ====================

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

    # ==================== 预占服务代理 ====================

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
