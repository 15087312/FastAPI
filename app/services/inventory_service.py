"""库存服务实现"""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import logging
from redis import Redis
from redlock import Redlock

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation, ReservationStatus
from app.models.inventory_logs import InventoryLog, ChangeType

logger = logging.getLogger(__name__)


class InventoryService:
    """库存核心服务类"""
    
    def __init__(self, db: Session, redis: Redis = None, rlock: Redlock = None):
        self.db = db
        self.redis = redis
        self.rlock = rlock
    
    def get_product_stock(self, product_id: int) -> int:
        """查询商品可用库存（带缓存）"""
        cache_key = f"stock:available:{product_id}"
        
        # 先查缓存
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for product {product_id}")
                return int(cached)
        
        # 缓存未命中，查询数据库
        stmt = select(ProductStock).where(ProductStock.product_id == product_id)
        result = self.db.execute(stmt)
        stock = result.scalar_one_or_none()
        available = stock.available_stock if stock else 0
        
        # 设置缓存（5分钟过期）
        if self.redis:
            self.redis.setex(cache_key, 300, available)
            logger.debug(f"Cache set for product {product_id}: {available}")
        
        return available
    
    def reserve_stock(self, product_id: int, quantity: int, order_id: str) -> bool:
        """预占库存（带分布式锁）"""
        lock_key = f"lock:inventory:{product_id}"
        lock = None
        
        # 获取分布式锁
        if self.rlock:
            lock = self.rlock.lock(lock_key, ttl=10000)  # 10秒TTL
            if not lock:
                raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
        
        try:
            # 使用行级锁查询商品库存
            stock = self.db.execute(
                select(ProductStock)
                .where(ProductStock.product_id == product_id)
                .with_for_update()
            ).scalar_one()

            if stock.available_stock < quantity:
                raise HTTPException(status_code=400, detail="库存不足")

            # 检查是否已有预占记录
            existing_reservation = self.db.execute(
                select(InventoryReservation)
                .where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.product_id == product_id
                )
            ).scalar_one_or_none()

            if existing_reservation:
                raise HTTPException(status_code=400, detail="该订单已预占此商品")

            # 扣减可用库存，增加预占库存
            stock.available_stock -= quantity
            stock.reserved_stock += quantity

            # 创建预占记录（15分钟过期）
            reservation = InventoryReservation(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                status=ReservationStatus.RESERVED,
                expired_at=datetime.utcnow() + timedelta(minutes=15)
            )

            self.db.add(reservation)
            
            # 记录库存变更日志
            log = InventoryLog(
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.RESERVE,
                quantity=-quantity,
                before_available=stock.available_stock + quantity,
                after_available=stock.available_stock,
                operator=f"order_service_{order_id}",
                source="order_service"
            )
            self.db.add(log)
            
            self.db.commit()
            logger.info(f"预占库存成功: order_id={order_id}, product_id={product_id}, quantity={quantity}")
            
            # 失效缓存
            if self.redis:
                self.redis.delete(f"stock:available:{product_id}")
                logger.debug(f"Cache invalidated for product {product_id}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"预占库存失败: {str(e)}")
            raise
        finally:
            # 释放分布式锁
            if self.rlock and lock:
                self.rlock.unlock(lock)
    
    def confirm_stock(self, order_id: str) -> bool:
        """确认库存（实际扣减，带分布式锁）"""
        # 先获取涉及的商品ID
        reservations_check = self.db.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.RESERVED
            )
        ).scalars().all()
        
        product_ids = [r.product_id for r in reservations_check]
        locks = []
        
        # 获取所有涉及商品的分布式锁
        if self.rlock and product_ids:
            for product_id in product_ids:
                lock_key = f"lock:inventory:{product_id}"
                lock = self.rlock.lock(lock_key, ttl=10000)
                if not lock:
                    raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
                locks.append((lock, product_id))
        
        try:
            # 查询所有待确认的预占记录
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
                # 使用行级锁查询商品
                product_stock = self.db.execute(
                    select(ProductStock)
                    .where(ProductStock.product_id == reservation.product_id)
                    .with_for_update()
                ).scalar_one()

                # 扣减预占库存，增加销售数量
                product_stock.reserved_stock -= reservation.quantity
                # 这里可以添加 sales_count 字段来记录销量
                
                # 更新预占状态
                reservation.status = ReservationStatus.CONFIRMED
                
                # 记录确认日志
                log = InventoryLog(
                    product_id=reservation.product_id,
                    order_id=order_id,
                    change_type=ChangeType.CONFIRM,
                    quantity=0,  # 状态变更不改变数量
                    before_available=product_stock.available_stock,
                    after_available=product_stock.available_stock,
                    operator=f"order_service_{order_id}",
                    source="order_service"
                )
                self.db.add(log)
            
            self.db.commit()
            logger.info(f"确认库存成功: order_id={order_id}")
            
            # 失效相关商品的缓存
            if self.redis and product_ids:
                for product_id in product_ids:
                    self.redis.delete(f"stock:available:{product_id}")
                    logger.debug(f"Cache invalidated for product {product_id}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"确认库存失败: {str(e)}")
            raise
        finally:
            # 释放所有分布式锁
            if self.rlock and locks:
                for lock, _ in locks:
                    self.rlock.unlock(lock)
    
    def release_stock(self, order_id: str) -> bool:
        """释放库存（归还预占，带分布式锁）"""
        # 先获取涉及的商品ID
        reservations_check = self.db.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.RESERVED
            )
        ).scalars().all()
        
        product_ids = [r.product_id for r in reservations_check]
        locks = []
        
        # 获取所有涉及商品的分布式锁
        if self.rlock and product_ids:
            for product_id in product_ids:
                lock_key = f"lock:inventory:{product_id}"
                lock = self.rlock.lock(lock_key, ttl=10000)
                if not lock:
                    raise HTTPException(status_code=429, detail="库存操作冲突，请稍后重试")
                locks.append((lock, product_id))
        
        try:
            # 查询所有待释放的预占记录
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
                # 使用行级锁查询商品
                product_stock = self.db.execute(
                    select(ProductStock)
                    .where(ProductStock.product_id == reservation.product_id)
                    .with_for_update()
                ).scalar_one()

                # 增加可用库存，扣减预占库存
                product_stock.available_stock += reservation.quantity
                product_stock.reserved_stock -= reservation.quantity
                
                # 更新预占状态
                reservation.status = ReservationStatus.RELEASED
                
                # 记录释放日志
                log = InventoryLog(
                    product_id=reservation.product_id,
                    order_id=order_id,
                    change_type=ChangeType.RELEASE,
                    quantity=reservation.quantity,
                    before_available=product_stock.available_stock - reservation.quantity,
                    after_available=product_stock.available_stock,
                    operator=f"order_service_{order_id}",
                    source="order_service"
                )
                self.db.add(log)
            
            self.db.commit()
            logger.info(f"释放库存成功: order_id={order_id}")
            
            # 失效相关商品的缓存
            if self.redis and product_ids:
                for product_id in product_ids:
                    self.redis.delete(f"stock:available:{product_id}")
                    logger.debug(f"Cache invalidated for product {product_id}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"释放库存失败: {str(e)}")
            raise
        finally:
            # 释放所有分布式锁
            if self.rlock and locks:
                for lock, _ in locks:
                    self.rlock.unlock(lock)
    
    def batch_get_stocks(self, product_ids: List[int]) -> dict:
        """批量获取库存（带缓存优化）"""
        if not product_ids:
            return {}
            
        results = {}
        uncached_ids = []
        
        # 先查缓存
        if self.redis:
            cache_keys = [f"stock:available:{pid}" for pid in product_ids]
            cached_values = self.redis.mget(cache_keys)
            
            # 处理缓存命中的项
            for i, (pid, cached) in enumerate(zip(product_ids, cached_values)):
                if cached is not None:
                    results[pid] = int(cached)
                    logger.debug(f"Batch cache hit for product {pid}")
                else:
                    uncached_ids.append(pid)
        else:
            uncached_ids = product_ids
        
        # 查询未缓存的库存
        if uncached_ids:
            stmt = select(ProductStock).where(ProductStock.product_id.in_(uncached_ids))
            result = self.db.execute(stmt)
            stocks = result.scalars().all()
            
            # 构建映射
            stock_map = {stock.product_id: stock.available_stock for stock in stocks}
            
            # 设置缓存并补充结果
            if self.redis:
                pipe = self.redis.pipeline()
                
            for pid in uncached_ids:
                available = stock_map.get(pid, 0)
                results[pid] = available
                
                # 设置缓存
                if self.redis:
                    pipe.setex(f"stock:available:{pid}", 300, available)
                    logger.debug(f"Batch cache set for product {pid}: {available}")
            
            if self.redis:
                pipe.execute()
        
        return results
    
    def cleanup_expired_reservations(self, batch_size: int = 500) -> int:
        """清理过期的库存预占记录（企业级实现）
        
        Args:
            db: 数据库会话
            batch_size: 批处理大小，默认500条
            
        Returns:
            清理的记录数量
        """
        total_cleaned = 0
        
        while True:
            try:
                # 批量查询过期的预占记录，使用 skip_locked 防止多worker竞争
                expired_reservations = self.db.execute(
                    select(InventoryReservation)
                    .where(
                        InventoryReservation.status == ReservationStatus.RESERVED,
                        InventoryReservation.expired_at <= datetime.utcnow()
                    )
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                ).scalars().all()
                
                if not expired_reservations:
                    break
                
                logger.info(f"本次清理 {len(expired_reservations)} 条过期预占记录")
                
                for reservation in expired_reservations:
                    try:
                        # 使用行级锁查询商品库存
                        product_stock = self.db.execute(
                            select(ProductStock)
                            .where(ProductStock.product_id == reservation.product_id)
                            .with_for_update()
                        ).scalar_one()
                        
                        # 归还库存：增加可用库存，减少预占库存
                        product_stock.available_stock += reservation.quantity
                        product_stock.reserved_stock -= reservation.quantity
                        
                        # 更新预占状态为已释放
                        reservation.status = ReservationStatus.RELEASED
                        
                        # 记录释放日志
                        log = InventoryLog(
                            product_id=reservation.product_id,
                            order_id=reservation.order_id,
                            change_type=ChangeType.RELEASE,
                            quantity=reservation.quantity,
                            before_available=product_stock.available_stock - reservation.quantity,
                            after_available=product_stock.available_stock,
                            operator="system_cleanup",
                            source="cleanup_job"
                        )
                        self.db.add(log)
                        
                        total_cleaned += 1
                        
                    except Exception as e:
                        logger.error(f"清理单条预占记录失败: order_id={reservation.order_id}, error={str(e)}")
                        self.db.rollback()
                        continue
                
                # 批次完成后失效相关商品的缓存
                if self.redis and expired_reservations:
                    product_ids = [r.product_id for r in expired_reservations]
                    for product_id in product_ids:
                        self.redis.delete(f"stock:available:{product_id}")
                        logger.debug(f"Cache invalidated for product {product_id} after cleanup")
                
                self.db.commit()
                logger.info(f"已完成批次清理，累计清理 {total_cleaned} 条记录")
                
                # 如果本次清理少于批处理大小，说明已经清理完所有过期记录
                if len(expired_reservations) < batch_size:
                    break
                    
            except Exception as e:
                logger.error(f"批处理清理过程中发生错误: {str(e)}")
                self.db.rollback()
                break
        
        logger.info(f"清理任务完成，总共清理 {total_cleaned} 条过期预占记录")
        
        return total_cleaned



