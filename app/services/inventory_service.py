"""库存服务 Facade - 组合所有库存相关服务"""

import logging
from fastapi import Depends
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
from redis import Redis

from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_query import InventoryQueryService
from app.services.inventory_operation import InventoryOperationService
from app.services.inventory_reservation import InventoryReservationService
from app.services.inventory_log import InventoryLogService

logger = logging.getLogger(__name__)


class InventoryService:
    """库存服务 Facade - 统一入口，组合所有子服务"""

    def __init__(self, db: Session, redis: Redis = None, rlock: Any = None):
        self.db = db
        self.redis = redis
        self.rlock = rlock

        # 初始化缓存服务
        self.cache_service = InventoryCacheService(redis)

        # 初始化子服务（共享缓存服务和数据库会话）
        self.query_service = InventoryQueryService(db, self.cache_service)
        self.operation_service = InventoryOperationService(db, self.cache_service, rlock)
        self.reservation_service = InventoryReservationService(db, self.cache_service, rlock)
        self.log_service = InventoryLogService(db, self.cache_service, rlock)

    # ==================== 缓存相关 ====================

    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return self.cache_service._get_cache_key(warehouse_id, product_id)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效库存缓存"""
        self.cache_service.invalidate_cache(warehouse_id, product_id)

    # ==================== 查询服务代理 ====================

    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存（带缓存）"""
        return self.query_service.get_product_stock(warehouse_id, product_id)

    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息"""
        return self.query_service.get_full_stock_info(warehouse_id, product_id)

    def _get_or_create_stock(self, warehouse_id: str, product_id: int):
        """获取或创建库存记录"""
        return self.query_service._get_or_create_stock(warehouse_id, product_id)

    def batch_get_stocks(self, warehouse_id: str, product_ids: List[int]) -> dict:
        """批量获取库存（带缓存优化）"""
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

    # ==================== 日志服务代理 ====================

    def get_inventory_logs(
        self,
        warehouse_id: Optional[str] = None,
        product_id: Optional[int] = None,
        order_id: Optional[str] = None,
        change_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """查询库存流水日志"""
        return self.log_service.get_inventory_logs(
            warehouse_id, product_id, order_id, change_type, start_date, end_date, page, page_size
        )

    def cleanup_expired_reservations(self, batch_size: int = 500) -> int:
        """清理过期的库存预占记录"""
        return self.log_service.cleanup_expired_reservations(batch_size)