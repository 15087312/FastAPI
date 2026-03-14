"""库存同步服务 - 负责 Redis 与数据库之间的数据同步"""

from sqlalchemy import select, insert, update
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging
import json

from app.models.product_stocks import ProductStock
from app.models.inventory_reservations import InventoryReservation
from app.models.inventory_logs import InventoryLog, ChangeType
from app.core.redis import redis_client

logger = logging.getLogger(__name__)


class InventorySyncService:
    """库存同步服务
    
    职责：
    1. 启动时：将数据库库存全量加载到 Redis
    2. 变更后：异步将 Redis 操作结果同步到数据库
    """
    
    def __init__(self, db: Session, redis=None):
        self.db = db
        self.redis = redis or redis_client
    
    def load_all_to_redis(self) -> int:
        """启动时将所有库存记录加载到 Redis
        
        Returns:
            加载的记录数
        """
        if not self.redis:
            logger.warning("Redis 客户端未初始化，跳过加载")
            return 0
        
        try:
            # 查询所有库存记录
            stmt = select(ProductStock)
            stocks = self.db.execute(stmt).scalars().all()
            
            count = 0
            pipe = self.redis.pipeline(transaction=False)
            
            for stock in stocks:
                cache_key = f"stock:available:{stock.warehouse_id}:{stock.product_id}"
                pipe.set(cache_key, stock.available_stock)
                
                full_key = f"stock:full:{stock.warehouse_id}:{stock.product_id}"
                full_data = {
                    "warehouse_id": stock.warehouse_id,
                    "product_id": stock.product_id,
                    "available_stock": stock.available_stock,
                    "reserved_stock": stock.reserved_stock,
                    "frozen_stock": stock.frozen_stock,
                    "safety_stock": stock.safety_stock,
                    "total_stock": stock.available_stock + stock.reserved_stock + stock.frozen_stock
                }
                pipe.set(full_key, json.dumps(full_data))
                count += 1
            
            pipe.execute()
            logger.info(f"✅ 已将 {count} 条库存记录加载到 Redis")
            return count
            
        except Exception as e:
            logger.error(f"❌ 加载库存到 Redis 失败：{e}")
            return 0
    
    def sync_reserve_to_db(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str,
        new_stock: int,
        ttl: int = 900
    ) -> bool:
        """将 Redis 预占操作同步到数据库
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            quantity: 预占数量
            order_id: 订单 ID
            new_stock: Redis 中扣减后的库存
            ttl: 预占记录过期时间（秒）
        
        Returns:
            是否成功
        """
        try:
            from datetime import datetime, timedelta
            
            # 1. 检查并获取库存记录（不带锁，直接读取）
            stock = self.db.execute(
                select(ProductStock).where(
                    ProductStock.warehouse_id == warehouse_id,
                    ProductStock.product_id == product_id
                )
            ).scalar_one_or_none()
            
            if not stock:
                logger.error(f"数据库找不到库存记录：{warehouse_id}:{product_id}")
                return False
            
            before_stock = stock.available_stock
            
            # 2. 验证库存是否足够（防止 Redis 和数据库不一致）
            if stock.available_stock < quantity:
                logger.error(f"数据库库存不足：{warehouse_id}:{product_id}, DB={stock.available_stock}, Redis={new_stock}")
                # 尝试修复：以 Redis 为准
                stock.available_stock = new_stock
            else:
                # 正常扣减
                stock.available_stock -= quantity
                stock.reserved_stock += quantity
            
            after_stock = stock.available_stock
            
            # 3. 创建预占记录
            from app.models.inventory_reservations import ReservationStatus
            
            reservation = InventoryReservation(
                warehouse_id=warehouse_id,
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                status=ReservationStatus.RESERVED,  # 使用枚举值
                expired_at=datetime.utcnow() + timedelta(seconds=ttl)
            )
            self.db.add(reservation)
            
            # 4. 记录日志
            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.RESERVE,
                quantity=-quantity,
                before_available=before_stock,
                after_available=after_stock,
                before_reserved=stock.reserved_stock - quantity,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                operator="redis_async"
            )
            self.db.add(log)
            
            # 5. 提交事务
            self.db.commit()
            
            logger.info(f"✅ 预占同步成功：order={order_id}, stock={before_stock}→{after_stock}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ 预占同步失败：{e}")
            return False
    
    def sync_release_to_db(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        order_id: str,
        new_stock: int
    ) -> bool:
        """将 Redis 释放操作同步到数据库
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            quantity: 释放数量
            order_id: 订单 ID
            new_stock: Redis 中增加后的库存
        
        Returns:
            是否成功
        """
        try:
            # 1. 获取库存记录（不带锁，直接读取）
            stock = self.db.execute(
                select(ProductStock).where(
                    ProductStock.warehouse_id == warehouse_id,
                    ProductStock.product_id == product_id
                )
            ).scalar_one_or_none()
            
            if not stock:
                logger.error(f"数据库找不到库存记录：{warehouse_id}:{product_id}")
                return False
            
            before_stock = stock.available_stock
            
            # 2. 更新库存
            stock.available_stock = new_stock
            stock.reserved_stock = max(0, stock.reserved_stock - quantity)
            
            # 3. 更新预占记录状态
            from app.models.inventory_reservations import ReservationStatus
            
            reservation = self.db.execute(
                select(InventoryReservation).where(
                    InventoryReservation.order_id == order_id,
                    InventoryReservation.warehouse_id == warehouse_id,
                    InventoryReservation.product_id == product_id,
                    InventoryReservation.status == ReservationStatus.RESERVED
                )
            ).scalar_one_or_none()
            
            if reservation:
                reservation.status = ReservationStatus.RELEASED
            else:
                logger.warning(f"未找到预占记录：{order_id}")
            
            # 4. 记录日志
            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.RELEASE,
                quantity=quantity,
                before_available=before_stock,
                after_available=new_stock,
                before_reserved=stock.reserved_stock + quantity,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                operator="redis_async"
            )
            self.db.add(log)
            
            # 5. 提交事务
            self.db.commit()
            
            logger.info(f"✅ 释放同步成功：order={order_id}, stock={before_stock}→{new_stock}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ 释放同步失败：{e}")
            return False
    
    def sync_increase_to_db(
        self,
        warehouse_id: str,
        product_id: int,
        quantity: int,
        new_stock: int,
        order_id: str = None,
        operator: str = "system"
    ) -> bool:
        """将 Redis 入库操作同步到数据库
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
            quantity: 入库数量
            new_stock: Redis 中增加后的库存
            order_id: 订单 ID（可选）
            operator: 操作员
        
        Returns:
            是否成功
        """
        try:
            # 1. 获取或创建库存记录
            stock = self.db.execute(
                select(ProductStock).where(
                    ProductStock.warehouse_id == warehouse_id,
                    ProductStock.product_id == product_id
                )
            ).scalar_one_or_none()
            
            if not stock:
                stock = ProductStock(
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    available_stock=0,
                    reserved_stock=0,
                    frozen_stock=0,
                    safety_stock=0
                )
                self.db.add(stock)
                self.db.flush()
            
            before_stock = stock.available_stock
            
            # 2. 更新库存（以 Redis 为准）
            stock.available_stock = new_stock
            
            # 3. 记录日志
            log = InventoryLog(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                change_type=ChangeType.INCREASE,
                quantity=quantity,
                before_available=before_stock,
                after_available=new_stock,
                before_reserved=stock.reserved_stock,
                after_reserved=stock.reserved_stock,
                before_frozen=stock.frozen_stock,
                after_frozen=stock.frozen_stock,
                operator=operator
            )
            self.db.add(log)
            
            # 4. 提交事务
            self.db.commit()
            
            logger.info(f"✅ 入库同步成功：stock={before_stock}→{new_stock}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ 入库同步失败：{e}")
            return False
