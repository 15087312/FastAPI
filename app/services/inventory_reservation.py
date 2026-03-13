"""库存预占服务"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType
from app.services.inventory_cache import InventoryCacheService
from app.core.aspects import (
    performance_monitor,
    CacheInvalidationAspect,
    LoggingAspect
)

# 使用结构化日志
from app.core.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)

# 全局线程池（用于异步同步数据库，避免频繁创建线程）
_db_sync_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="db_sync_")


class InventoryReservationService:
    """库存预占服务
    
    使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
    """

    def __init__(
        self,
        db: Session,
        cache_service: InventoryCacheService = None
    ):
        self.db = db
        self.cache_service = cache_service
        # 使用统一的缓存失效切面
        self.cache_aspect = CacheInvalidationAspect(cache_service)

    def _invalidate_cache(self, warehouse_id: str, product_id: int):
        """失效缓存（使用统一切面）"""
        self.cache_aspect.invalidate_single(warehouse_id, product_id)

    @performance_monitor
    def reserve_stock(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str
    ) -> bool:
        """预占库存 - Redis Lua 脚本原子操作，异步写入数据库
        
        流程：
        1. 幂等性检查（Redis）
        2. Redis Lua 脚本原子扣减库存
        3. 异步写入数据库（不阻塞主流程）
        4. 记录幂等性结果
        """
        import asyncio
        from app.core.kafka_producer import send_inventory_event, InventoryEventType
        from app.services.inventory_sync import InventorySyncService
        
        start_time = time.time()
        
        # 幂等性检查：如果已处理过，直接返回之前的结果
        if self.cache_service and hasattr(self.cache_service, 'check_idempotent'):
            is_duplicate, previous_result = self.cache_service.check_idempotent("reserve", order_id)
            if is_duplicate and previous_result:
                logger.info(f"幂等命中：order_id={order_id}, 返回之前的结果")
                return previous_result.get("success", True)
        
        try:
            # 1. 使用 Redis Lua 脚本原子扣减库存
            if not self.cache_service:
                raise HTTPException(status_code=500, detail="缓存服务未初始化")
            
            new_stock, is_duplicate = self.cache_service.atomic_reserve_stock(
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=quantity,
                order_id=order_id,
                ttl=900  # 15 分钟
            )
            
            if is_duplicate:
                logger.warning(f"重复预占：order_id={order_id}")
                raise HTTPException(status_code=400, detail="该订单已预占此商品")
            
            if new_stock < 0:
                logger.warning(f"库存不足：warehouse={warehouse_id}, product={product_id}, stock={new_stock}")
                raise HTTPException(status_code=400, detail="库存不足")
            
            before_stock = new_stock + quantity  # 计算扣减前的库存
            after_stock = new_stock
            
            logger.info(f"✅ Redis 预占成功：order={order_id}, stock={before_stock}→{after_stock}")
            
            # 2. 异步写入数据库（不阻塞主流程）
            try:
                loop = asyncio.get_running_loop()
                
                async def sync_to_db():
                    """异步同步到数据库（使用独立连接，避免阻塞）"""
                    from app.db.session import SessionLocal
                    db_session = SessionLocal()  # 创建独立的数据库连接
                    try:
                        sync_service = InventorySyncService(db_session)
                        success = sync_service.sync_reserve_to_db(
                            warehouse_id=warehouse_id,
                            product_id=product_id,
                            quantity=quantity,
                            order_id=order_id,
                            new_stock=after_stock
                        )
                        if not success:
                            logger.error(f"数据库同步失败，需要人工介入：order={order_id}")
                    except Exception as e:
                        logger.error(f"数据库同步异常：{e}")
                        db_session.rollback()
                    finally:
                        db_session.close()
                
                asyncio.create_task(sync_to_db())
                logger.debug(f"已创建异步任务同步数据库：order={order_id}")
                
            except RuntimeError:
                # 没有 running loop，使用线程池执行（复用线程，避免频繁创建）
                def run_async():
                    from app.db.session import SessionLocal
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    db_session = SessionLocal()  # 创建独立的数据库连接
                    try:
                        sync_service = InventorySyncService(db_session)
                        success = sync_service.sync_reserve_to_db(
                            warehouse_id=warehouse_id,
                            product_id=product_id,
                            quantity=quantity,
                            order_id=order_id,
                            new_stock=after_stock
                        )
                        if not success:
                            logger.error(f"数据库同步失败：order={order_id}")
                    except Exception as e:
                        logger.error(f"数据库同步异常：{e}")
                        db_session.rollback()
                    finally:
                        db_session.close()
                        new_loop.close()
                
                _db_sync_executor.submit(run_async)
                logger.debug(f"已提交线程池任务同步数据库：order={order_id}")
                
            except Exception as e:
                logger.warning(f"异步同步数据库失败（不影响主流程）: {e}")
            
            elapsed_ms = (time.time() - start_time) * 1000
            LoggingAspect.log_operation_success(
                "reserve_stock",
                extra_data={
                    'warehouse_id': warehouse_id,
                    'product_id': product_id,
                    'quantity': quantity,
                    'order_id': order_id,
                    'before_stock': before_stock,
                    'after_stock': after_stock,
                    'elapsed_ms': elapsed_ms
                }
            )
            
            # 3. 记录幂等性结果（24 小时有效）
            if self.cache_service and hasattr(self.cache_service, 'set_idempotent'):
                self.cache_service.set_idempotent(
                    operation="reserve",
                    order_id=order_id,
                    result_data={"success": True, "warehouse_id": warehouse_id, "product_id": product_id, "quantity": quantity},
                    ttl=86400
                )
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"预占库存失败：{str(e)}")
            raise

    @performance_monitor
    def reserve_batch(
        self,
        order_id: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """批量预占库存（事务保证：全部成功或全部回滚）
        
        使用两阶段预检查：
        1. 第一阶段：预检查所有商品库存是否充足、是否存在重复预占
        2. 第二阶段：执行所有预占操作并一次性提交
        
        这样保证真正的原子性：要么全部成功，要么全部失败。
        """
        start_time = time.time()

        try:
            # ========== 第一阶段：预检查所有商品 ==========
            validation_results = []
            for item in items:
                warehouse_id = item["warehouse_id"]
                product_id = item["product_id"]
                quantity = item["quantity"]

                # 检查库存记录是否存在
                stock = self.db.execute(
                    select(ProductStock)
                    .where(
                        ProductStock.warehouse_id == warehouse_id,
                        ProductStock.product_id == product_id
                    )
                ).scalar_one_or_none()

                if not stock:
                    validation_results.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "valid": False,
                        "message": "库存记录不存在"
                    })
                    continue

                # 检查库存是否足够
                if stock.available_stock < quantity:
                    validation_results.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "valid": False,
                        "message": f"库存不足（当前可用: {stock.available_stock}，需要: {quantity}）"
                    })
                    continue

                # 检查是否已存在预占
                existing_reservation = self.db.execute(
                    select(InventoryReservation)
                    .where(
                        InventoryReservation.order_id == order_id,
                        InventoryReservation.warehouse_id == warehouse_id,
                        InventoryReservation.product_id == product_id,
                        InventoryReservation.status == ReservationStatus.RESERVED
                    )
                ).scalar_one_or_none()

                if existing_reservation:
                    validation_results.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "valid": False,
                        "message": "该订单已预占此商品"
                    })
                    continue

                # 预检查通过
                validation_results.append({
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "valid": True,
                    "message": "预检查通过"
                })

            # 检查是否有预检查失败的项目
            failed_items = [r for r in validation_results if not r["valid"]]
            if failed_items:
                # 预检查阶段失败，不执行任何数据库操作，直接返回
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "部分商品预检查失败",
                        "failed_items": failed_items,
                        "total_items": len(items),
                        "failed_count": len(failed_items)
                    }
                )

            # ========== 第二阶段：执行所有预占操作 ==========
            success_items = []
            try:
                for item, validation in zip(items, validation_results):
                    warehouse_id = item["warehouse_id"]
                    product_id = item["product_id"]
                    quantity = item["quantity"]

                    # 获取行级锁并执行扣减
                    stock = self.db.execute(
                        select(ProductStock)
                        .where(
                            ProductStock.warehouse_id == warehouse_id,
                            ProductStock.product_id == product_id
                        )
                        .with_for_update()
                    ).scalar_one()

                    before_available = stock.available_stock

                    # 再次检查库存（防止并发）
                    if stock.available_stock < quantity:
                        raise Exception(f"商品 {product_id} 库存不足")

                    # 执行扣减
                    stock.available_stock -= quantity
                    stock.reserved_stock += quantity

                    # 创建预占记录
                    reservation = InventoryReservation(
                        warehouse_id=warehouse_id,
                        order_id=order_id,
                        product_id=product_id,
                        quantity=quantity,
                        status=ReservationStatus.RESERVED,
                        expired_at=datetime.utcnow() + timedelta(minutes=15)
                    )
                    self.db.add(reservation)

                    # 记录日志
                    log = InventoryLog(
                        warehouse_id=warehouse_id,
                        product_id=product_id,
                        order_id=order_id,
                        change_type=ChangeType.BATCH_RESERVE,
                        quantity=-quantity,
                        before_available=before_available,
                        after_available=stock.available_stock,
                        before_reserved=stock.reserved_stock - quantity,
                        after_reserved=stock.reserved_stock,
                        before_frozen=stock.frozen_stock,
                        after_frozen=stock.frozen_stock,
                        operator=f"order_service_{order_id}",
                        source="order_service"
                    )
                    self.db.add(log)

                    success_items.append({
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "success": True,
                        "message": "预占成功"
                    })

                # 一次性提交所有更改
                self.db.commit()
                logger.info(f"批量预占成功：order_id={order_id}, count={len(success_items)}")

                # 使用统一的缓存失效切面
                self.cache_aspect.invalidate_batch(items)

                return {
                    "order_id": order_id,
                    "total_items": len(items),
                    "success_items": len(success_items),
                    "failed_items": 0,
                    "details": success_items
                }

            except Exception as e:
                # 执行阶段出错，回滚所有更改
                self.db.rollback()
                logger.error(f"批量预占执行失败，已回滚: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": f"批量预占执行失败，已回滚: {str(e)}",
                        "total_items": len(items),
                        "success_items": 0,
                        "failed_items": len(items)
                    }
                )

        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量预占失败: {str(e)}")
            raise

    @performance_monitor
    def confirm_stock(self, order_id: str) -> bool:
        """确认库存（实际扣减）+ 幂等性保证
        
        使用数据库行级锁 (SELECT FOR UPDATE) 保证并发安全
        """
        # 幂等性检查
        if self.cache_service and hasattr(self.cache_service, 'check_idempotent'):
            is_duplicate, previous_result = self.cache_service.check_idempotent("confirm", order_id)
            if is_duplicate and previous_result:
                logger.info(f"幂等命中(confirm): order_id={order_id}, 返回之前的结果")
                return previous_result.get("success", True)
        
        start_time = time.time()
        reservations = self.db.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.RESERVED
            )
        ).scalars().all()

        if not reservations:
            raise HTTPException(status_code=404, detail="未找到有效的预占记录")

        for reservation in reservations:
            product_stock = self.db.execute(
                select(ProductStock)
                .where(
                    ProductStock.warehouse_id == reservation.warehouse_id,
                    ProductStock.product_id == reservation.product_id
                )
                .with_for_update()
            ).scalar_one()

            product_stock.reserved_stock -= reservation.quantity

            reservation.status = ReservationStatus.CONFIRMED

            log = InventoryLog(
                warehouse_id=reservation.warehouse_id,
                product_id=reservation.product_id,
                order_id=order_id,
                change_type=ChangeType.CONFIRM,
                quantity=0,
                before_available=product_stock.available_stock,
                after_available=product_stock.available_stock,
                before_reserved=product_stock.reserved_stock + reservation.quantity,
                after_reserved=product_stock.reserved_stock,
                before_frozen=product_stock.frozen_stock,
                after_frozen=product_stock.frozen_stock,
                operator=f"order_service_{order_id}",
                source="order_service"
            )
            self.db.add(log)

        self.db.commit()
        LoggingAspect.log_operation_success("confirm_stock", extra_data={'order_id': order_id})

        # 使用统一的缓存失效切面
        self.cache_aspect.invalidate_by_order(reservations)
        
        # 记录幂等性结果
        if self.cache_service and hasattr(self.cache_service, 'set_idempotent'):
            self.cache_service.set_idempotent(
                operation="confirm",
                order_id=order_id,
                result_data={"success": True},
                ttl=86400
            )

        return True

    @performance_monitor
    def release_stock(self, order_id: str) -> bool:
        """释放库存（归还预占） - Redis Lua 脚本原子操作，异步写入数据库
            
        流程：
        1. 幂等性检查（Redis）
        2. Redis Lua 脚本原子释放库存
        3. 异步写入数据库（不阻塞主流程）
        4. 记录幂等性结果
        """
        import asyncio
        from app.services.inventory_sync import InventorySyncService
            
        # 幂等性检查
        if self.cache_service and hasattr(self.cache_service, 'check_idempotent'):
            is_duplicate, previous_result = self.cache_service.check_idempotent("release", order_id)
            if is_duplicate and previous_result:
                logger.info(f"幂等命中 (release): order_id={order_id}, 返回之前的结果")
                return previous_result.get("success", True)
            
        start_time = time.time()
            
        try:
            # 1. 查询预占记录（从数据库获取信息）
            reservations = self.db.execute(
                select(InventoryReservation).where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.status == ReservationStatus.RESERVED
                )
            ).scalars().all()
                
            if not reservations:
                raise HTTPException(status_code=404, detail="未找到有效的预占记录")
                
            # 2. 对每个商品执行 Redis 释放
            for reservation in reservations:
                if not self.cache_service:
                    raise HTTPException(status_code=500, detail="缓存服务未初始化")
                    
                new_stock, is_not_found = self.cache_service.atomic_release_stock(
                    warehouse_id=reservation.warehouse_id,
                    product_id=reservation.product_id,
                    quantity=reservation.quantity,
                    order_id=order_id
                )
                    
                if is_not_found:
                    logger.warning(f"Redis 中预占记录不存在：order={order_id}")
                    # 继续处理，因为可能已经在 Redis 中释放了
                    
                after_stock = new_stock
                before_stock = new_stock - reservation.quantity
                    
                logger.info(f"✅ Redis 释放成功：order={order_id}, stock={before_stock}→{after_stock}")
                    
                # 3. 异步写入数据库（使用独立连接）
                try:
                    loop = asyncio.get_running_loop()
                        
                    async def sync_to_db():
                        from app.db.session import SessionLocal
                        db_session = SessionLocal()  # 创建独立的数据库连接
                        try:
                            sync_service = InventorySyncService(db_session)
                            success = sync_service.sync_release_to_db(
                                warehouse_id=reservation.warehouse_id,
                                product_id=reservation.product_id,
                                quantity=reservation.quantity,
                                order_id=order_id,
                                new_stock=after_stock
                            )
                            if not success:
                                logger.error(f"数据库同步失败：order={order_id}")
                        except Exception as e:
                            logger.error(f"数据库同步异常：{e}")
                            db_session.rollback()
                        finally:
                            db_session.close()
                        
                    asyncio.create_task(sync_to_db())
                    logger.debug(f"已创建异步任务同步数据库：order={order_id}")
                        
                except RuntimeError:
                    import threading
                    def run_async():
                        from app.db.session import SessionLocal
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        db_session = SessionLocal()  # 创建独立的数据库连接
                        try:
                            sync_service = InventorySyncService(db_session)
                            success = sync_service.sync_release_to_db(
                                warehouse_id=reservation.warehouse_id,
                                product_id=reservation.product_id,
                                quantity=reservation.quantity,
                                order_id=order_id,
                                new_stock=after_stock
                            )
                            if not success:
                                logger.error(f"数据库同步失败：order={order_id}")
                        except Exception as e:
                            logger.error(f"数据库同步异常：{e}")
                            db_session.rollback()
                        finally:
                            db_session.close()
                            new_loop.close()
                        
                    _db_sync_executor.submit(run_async)
                    logger.debug(f"已提交线程池任务同步数据库：order={order_id}")
                        
                except Exception as e:
                    logger.warning(f"异步同步数据库失败（不影响主流程）: {e}")
                
            elapsed_ms = (time.time() - start_time) * 1000
            LoggingAspect.log_operation_success(
                "release_stock",
                extra_data={'order_id': order_id, 'elapsed_ms': elapsed_ms}
            )
                
            # 4. 记录幂等性结果
            if self.cache_service and hasattr(self.cache_service, 'set_idempotent'):
                self.cache_service.set_idempotent(
                    operation="release",
                    order_id=order_id,
                    result_data={"success": True},
                    ttl=86400
                )
                
            return True
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"释放库存失败：{str(e)}")
            raise
        
        # 记录幂等性结果
        if self.cache_service and hasattr(self.cache_service, 'set_idempotent'):
            self.cache_service.set_idempotent(
                operation="release",
                order_id=order_id,
                result_data={"success": True},
                ttl=86400
            )

        return True