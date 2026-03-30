"""库存操作服务 - 纯Redis操作，Kafka异步同步数据库"""

from fastapi import HTTPException
from typing import Dict, Any, Optional
import logging

from app.services.inventory_cache import InventoryCacheService
from app.services.inventory_query import InventoryQueryService
from app.core.kafka_producer import send_inventory_event, InventoryEventType

logger = logging.getLogger(__name__)


class InventoryOperationService:
    """库存操作服务 - 纯Redis操作，Kafka异步同步数据库"""

    def __init__(self, cache_service: InventoryCacheService = None):
        self.cache_service = cache_service
        self.query_service = InventoryQueryService(cache_service)

    async def _send_kafka_event(
        self,
        event_type: str,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str,
        before_stock: int,
        after_stock: int,
        remark: str = None
    ):
        """发送Kafka事件"""
        try:
            await send_inventory_event(
                event_type=event_type,
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=quantity,
                order_id=order_id,
                before_stock=before_stock,
                after_stock=after_stock,
                remark=remark
            )
        except Exception as e:
            logger.warning(f"Kafka事件发送失败（不影响主流程）: {e}")

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
        """入库/补货 - Redis原子操作，Kafka异步同步数据库"""
        try:
            if not self.cache_service:
                raise HTTPException(status_code=500, detail="缓存服务未初始化")
            
            # 1. 获取当前库存（从 Redis）
            current_stock = self.cache_service.get_cached_stock(warehouse_id, product_id)
            
            # 如果Redis中没有数据，初始化为0
            if current_stock is None:
                current_stock = 0
                logger.info(f"Redis中无此商品数据，初始化为0: warehouse={warehouse_id}, product={product_id}")
            
            before_stock = current_stock
            after_stock = current_stock + quantity
            
            # 2. 更新 Redis 库存（永不过期）
            self.cache_service.set_cached_stock(warehouse_id, product_id, after_stock)
            
            # 更新完整信息
            full_info = {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "available_stock": after_stock,
                "reserved_stock": 0,
                "frozen_stock": 0,
                "safety_stock": 0,
                "total_stock": after_stock
            }
            self.cache_service.set_cached_full_info(warehouse_id, product_id, full_info)
            
            logger.info(f"✅ Redis 入库成功：stock={before_stock}→{after_stock}")
            
            # 3. 异步发送Kafka事件（不同步写数据库）
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_kafka_event(
                    event_type=InventoryEventType.INCREASE,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    quantity=quantity,
                    order_id=order_id or f"INCR_{product_id}",
                    before_stock=before_stock,
                    after_stock=after_stock,
                    remark=remark or f"入库: {quantity}"
                ))
            except RuntimeError:
                # 没有运行中的loop，在新线程中运行
                import threading
                def run_async():
                    asyncio.run(self._send_kafka_event(
                        event_type=InventoryEventType.INCREASE,
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        quantity=quantity,
                        order_id=order_id or f"INCR_{product_id}",
                        before_stock=before_stock,
                        after_stock=after_stock,
                        remark=remark or f"入库: {quantity}"
                    ))
                threading.Thread(target=run_async, daemon=True).start()
            
            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_stock": before_stock,
                "after_stock": after_stock,
                "quantity": quantity
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"入库失败：{str(e)}")
            raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")

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
        """库存调整（增加/减少/设置）- Redis操作，Kafka异步同步"""
        try:
            if not self.cache_service:
                raise HTTPException(status_code=500, detail="缓存服务未初始化")
            
            # 1. 获取当前库存（从 Redis）
            current_stock = self.cache_service.get_cached_stock(warehouse_id, product_id)
            if current_stock is None:
                current_stock = 0
            
            before_available = current_stock

            if adjust_type == "increase":
                after_available = current_stock + quantity
                change_qty = quantity
            elif adjust_type == "decrease":
                if current_stock < quantity:
                    raise HTTPException(status_code=400, detail="库存不足，无法减少")
                after_available = current_stock - quantity
                change_qty = -quantity
            elif adjust_type == "set":
                after_available = quantity
                change_qty = quantity - current_stock
            else:
                raise HTTPException(status_code=400, detail="无效的调整类型")

            # 2. 更新 Redis 库存
            self.cache_service.set_cached_stock(warehouse_id, product_id, after_available)
            
            # 更新完整信息
            full_info = {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "available_stock": after_available,
                "reserved_stock": 0,
                "frozen_stock": 0,
                "safety_stock": 0,
                "total_stock": after_available
            }
            self.cache_service.set_cached_full_info(warehouse_id, product_id, full_info)
            
            logger.info(f"✅ Redis 库存调整成功：stock={before_available}→{after_available}, type={adjust_type}")
            
            # 3. 异步发送Kafka事件
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_kafka_event(
                    event_type=InventoryEventType.INCREASE if change_qty > 0 else InventoryEventType.DECREASE,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    quantity=abs(change_qty),
                    order_id=f"ADJUST_{product_id}",
                    before_stock=before_available,
                    after_stock=after_available,
                    remark=reason
                ))
            except RuntimeError:
                import threading
                def run_async():
                    asyncio.run(self._send_kafka_event(
                        event_type=InventoryEventType.INCREASE if change_qty > 0 else InventoryEventType.DECREASE,
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        quantity=abs(change_qty),
                        order_id=f"ADJUST_{product_id}",
                        before_stock=before_available,
                        after_stock=after_available,
                        remark=reason
                    ))
                threading.Thread(target=run_async, daemon=True).start()

            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_available": before_available,
                "after_available": after_available,
                "adjust_type": adjust_type,
                "quantity": quantity
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"库存调整失败：{str(e)}")
            raise HTTPException(status_code=500, detail=f"库存调整失败: {str(e)}")

    def freeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """冻结库存 - Redis操作，Kafka异步同步"""
        try:
            if not self.cache_service:
                raise HTTPException(status_code=500, detail="缓存服务未初始化")
            
            # 1. 获取当前库存（从 Redis）
            current_stock = self.cache_service.get_cached_stock(warehouse_id, product_id)
            if current_stock is None:
                current_stock = 0
            
            if current_stock < quantity:
                raise HTTPException(status_code=400, detail="可用库存不足，无法冻结")
            
            before_available = current_stock
            after_available = current_stock - quantity
            
            # 2. 更新 Redis 库存
            self.cache_service.set_cached_stock(warehouse_id, product_id, after_available)
            
            # 更新完整信息
            full_info = {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "available_stock": after_available,
                "reserved_stock": 0,
                "frozen_stock": quantity,
                "safety_stock": 0,
                "total_stock": current_stock
            }
            self.cache_service.set_cached_full_info(warehouse_id, product_id, full_info)
            
            logger.info(f"✅ Redis 冻结成功：stock={before_available}→{after_available}, frozen={quantity}")
            
            # 3. 异步发送Kafka事件
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_kafka_event(
                    event_type=InventoryEventType.FREEZE,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    quantity=quantity,
                    order_id=f"FREEZE_{product_id}",
                    before_stock=before_available,
                    after_stock=after_available,
                    remark=reason
                ))
            except RuntimeError:
                import threading
                def run_async():
                    asyncio.run(self._send_kafka_event(
                        event_type=InventoryEventType.FREEZE,
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        quantity=quantity,
                        order_id=f"FREEZE_{product_id}",
                        before_stock=before_available,
                        after_stock=after_available,
                        remark=reason
                    ))
                threading.Thread(target=run_async, daemon=True).start()
            
            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_available": before_available,
                "after_available": after_available,
                "frozen_stock": quantity
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"冻结库存失败：{str(e)}")
            raise HTTPException(status_code=500, detail=f"冻结库存失败: {str(e)}")

    def unfreeze_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        reason: Optional[str] = None,
        operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """解冻库存 - Redis操作，Kafka异步同步"""
        try:
            if not self.cache_service:
                raise HTTPException(status_code=500, detail="缓存服务未初始化")
            
            # 1. 获取当前库存（从 Redis）
            current_available = self.cache_service.get_cached_stock(warehouse_id, product_id)
            current_frozen_info = self.cache_service.get_cached_full_info(warehouse_id, product_id)
            
            if current_available is None:
                current_available = 0
            
            current_frozen = current_frozen_info.get('frozen_stock', 0) if current_frozen_info else 0
            
            if current_frozen < quantity:
                raise HTTPException(status_code=400, detail="冻结库存不足，无法解冻")
            
            before_available = current_available
            after_available = current_available + quantity
            before_frozen = current_frozen
            after_frozen = current_frozen - quantity
            
            # 2. 更新 Redis 库存
            self.cache_service.set_cached_stock(warehouse_id, product_id, after_available)
            
            # 更新完整信息
            full_info = {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "available_stock": after_available,
                "reserved_stock": 0,
                "frozen_stock": after_frozen,
                "safety_stock": 0,
                "total_stock": after_available + after_frozen
            }
            self.cache_service.set_cached_full_info(warehouse_id, product_id, full_info)
            
            logger.info(f"✅ Redis 解冻成功：stock={before_available}→{after_available}, frozen={before_frozen}→{after_frozen}")
            
            # 3. 异步发送Kafka事件
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_kafka_event(
                    event_type=InventoryEventType.UNFREEZE,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    quantity=quantity,
                    order_id=f"UNFREEZE_{product_id}",
                    before_stock=before_available,
                    after_stock=after_available,
                    remark=reason
                ))
            except RuntimeError:
                import threading
                def run_async():
                    asyncio.run(self._send_kafka_event(
                        event_type=InventoryEventType.UNFREEZE,
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        quantity=quantity,
                        order_id=f"UNFREEZE_{product_id}",
                        before_stock=before_available,
                        after_stock=after_available,
                        remark=reason
                    ))
                threading.Thread(target=run_async, daemon=True).start()
            
            return {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "before_available": before_available,
                "after_available": after_available,
                "before_frozen": before_frozen,
                "after_frozen": after_frozen
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"解冻库存失败：{str(e)}")
            raise HTTPException(status_code=500, detail=f"解冻库存失败: {str(e)}")