"""Kafka 消费者服务 - 消费库存变更消息并更新数据库"""

import os
import json
import asyncio
import logging
import time
from typing import Optional
from aiokafka import AIOKafkaConsumer
from datetime import datetime

from app.db.session import SessionLocal
from app.models.product_stocks import ProductStock
from app.models.inventory_logs import InventoryLog, ChangeType
from app.models.inventory_reservations import InventoryReservation, ReservationStatus

logger = logging.getLogger(__name__)

# Kafka 配置
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
INVENTORY_TOPIC = "inventory-changes"

# ========== 速率限制配置 ==========
# 每秒最大处理消息数（默认 100 条/秒）
KAFKA_MAX_MESSAGES_PER_SECOND = int(os.getenv("KAFKA_MAX_MESSAGES_PER_SECOND", "100"))
# 突发流量最大处理条数（允许短暂超过速率限制）
KAFKA_BURST_CAPACITY = int(os.getenv("KAFKA_BURST_CAPACITY", "200"))
# 批量处理大小（达到批量大小时一次性提交）
KAFKA_BATCH_SIZE = int(os.getenv("KAFKA_BATCH_SIZE", "10"))

# ========== 消息合并配置 ==========
# 消息合并窗口时间（毫秒），在窗口时间内相同的操作会被合并
KAFKA_MERGE_WINDOW_MS = int(os.getenv("KAFKA_MERGE_WINDOW_MS", "100"))
# 合并阈值，达到此数量的相同操作时强制合并
KAFKA_MERGE_THRESHOLD = int(os.getenv("KAFKA_MERGE_THRESHOLD", "5"))


class RateLimiter:
    """令牌桶速率限制器 - 实现平滑的速率控制"""
    
    def __init__(self, rate: int, burst: int = None):
        """
        Args:
            rate: 每秒生成的令牌数
            burst: 突发容量（可选，默认等于 rate）
        """
        self.rate = rate
        self.burst = burst or rate
        self.tokens = self.burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> float:
        """
        获取令牌，如果没有足够的令牌则等待
        
        Args:
            tokens: 需要获取的令牌数
            
        Returns:
            等待时间（秒）
        """
        async with self._lock:
            now = time.time()
            # 计算时间间隔内应该生成的令牌数
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            
            # 需要等待的时间
            wait_time = (tokens - self.tokens) / self.rate
            # 等待并补充令牌
            await asyncio.sleep(wait_time)
            self.tokens = 0
            return wait_time


class MessageBuffer:
    """消息缓冲区 - 批量处理消息"""
    
    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size
        self.buffer = []
    
    async def add(self, message):
        """添加消息到缓冲区"""
        self.buffer.append(message)
        if len(self.buffer) >= self.batch_size:
            return await self.flush()
        return None
    
    async def flush(self):
        """清空缓冲区并返回所有消息"""
        if not self.buffer:
            return None
        messages = self.buffer
        self.buffer = []
        return messages


# 全局速率限制器和缓冲区
_rate_limiter: Optional[RateLimiter] = None
_message_buffer: Optional[MessageBuffer] = None


def get_rate_limiter() -> RateLimiter:
    """获取或创建速率限制器（单例）"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            rate=KAFKA_MAX_MESSAGES_PER_SECOND,
            burst=KAFKA_BURST_CAPACITY
        )
        logger.info(
            f"速率限制器初始化: 最大 {KAFKA_MAX_MESSAGES_PER_SECOND} 条/秒, "
            f"突发容量 {KAFKA_BURST_CAPACITY} 条"
        )
    return _rate_limiter


def get_message_buffer() -> MessageBuffer:
    """获取或创建消息缓冲区（单例）"""
    global _message_buffer
    if _message_buffer is None:
        _message_buffer = MessageBuffer(batch_size=KAFKA_BATCH_SIZE)
        logger.info(f"消息缓冲区初始化: 批量大小 {KAFKA_BATCH_SIZE}")
    return _message_buffer


class MessageMerger:
    """消息合并器 - 将相同商品的相同操作合并
    
    例如：5 个 +1 操作合并为 1 个 +5 操作
    """
    
    def __init__(self, merge_window_ms: int = 100, merge_threshold: int = 5):
        """
        Args:
            merge_window_ms: 合并窗口时间（毫秒），超过此时间则强制合并
            merge_threshold: 合并阈值，达到此数量时强制合并
        """
        self.merge_window_ms = merge_window_ms / 1000.0  # 转换为秒
        self.merge_threshold = merge_threshold
        self.pending_messages: dict = {}  # key: (warehouse_id, product_id, event_type)
        self.last_flush_time = time.time()
        self._lock = asyncio.Lock()
        self._total_merged = 0  # 统计合并的消息数
    
    def _get_message_key(self, event: dict) -> tuple:
        """获取消息的唯一标识键"""
        return (
            event.get("warehouse_id"),
            event.get("product_id"),
            event.get("event_type")
        )
    
    async def add(self, event: dict) -> Optional[list]:
        """
        添加消息到合并缓冲区
        
        Args:
            event: 库存变更事件
            
        Returns:
            如果有需要处理的合并后消息，返回列表；否则返回 None
        """
        async with self._lock:
            key = self._get_message_key(event)
            event_type = event.get("event_type")
            quantity = event.get("quantity", 0)
            
            current_time = time.time()
            time_elapsed = current_time - self.last_flush_time
            
            # 检查是否需要强制刷新（超过窗口时间）
            should_flush = time_elapsed >= self.merge_window_ms
            
            if key not in self.pending_messages:
                # 新消息
                self.pending_messages[key] = {
                    "events": [event],
                    "total_quantity": quantity,
                    "first_time": current_time,
                    "last_time": current_time,
                    "count": 1
                }
            else:
                # 已有消息，累加数量
                pending = self.pending_messages[key]
                pending["events"].append(event)
                pending["total_quantity"] += quantity
                pending["last_time"] = current_time
                pending["count"] += 1
                
                # 检查是否达到合并阈值
                if pending["count"] >= self.merge_threshold:
                    should_flush = True
            
            # 如果需要强制刷新，返回所有合并后的消息
            if should_flush:
                return await self.flush()
            
            return None
    
    async def flush(self) -> list:
        """强制刷新合并缓冲区，返回所有合并后的消息"""
        async with self._lock:
            if not self.pending_messages:
                return []
            
            merged_messages = []
            
            for key, pending in self.pending_messages.items():
                warehouse_id, product_id, event_type = key
                
                # 构建合并后的消息
                merged_event = {
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "event_type": event_type,
                    "quantity": pending["total_quantity"],
                    "before_stock": pending["events"][0].get("before_stock", 0),
                    "after_stock": pending["events"][-1].get("after_stock", 0),
                    "order_id": f"merged_{int(pending['first_time'] * 1000)}",
                    "_merged_count": pending["count"],  # 记录合并了多少条
                    "_merge_info": f"{pending['count']} 个 {event_type} 操作已合并"
                }
                
                merged_messages.append(merged_event)
                self._total_merged += pending["count"]
            
            logger.info(
                f"消息合并完成: 原始 {len(self.pending_messages)} 条 -> 合并后 {len(merged_messages)} 条, "
                f"共减少 {self._total_merged} 条原始消息"
            )
            
            self.pending_messages = {}
            self.last_flush_time = time.time()
            
            return merged_messages
    
    def get_stats(self) -> dict:
        """获取合并统计信息"""
        return {
            "pending_count": len(self.pending_messages),
            "total_merged": self._total_merged
        }


# 全局消息合并器
_message_merger: Optional[MessageMerger] = None


def get_message_merger() -> MessageMerger:
    """获取或创建消息合并器（单例）"""
    global _message_merger
    if _message_merger is None:
        _message_merger = MessageMerger(
            merge_window_ms=KAFKA_MERGE_WINDOW_MS,
            merge_threshold=KAFKA_MERGE_THRESHOLD
        )
        logger.info(
            f"消息合并器初始化: 窗口时间 {KAFKA_MERGE_WINDOW_MS}ms, "
            f"合并阈值 {KAFKA_MERGE_THRESHOLD}"
        )
    return _message_merger


# 全局消费者实例
_consumer: Optional[AIOKafkaConsumer] = None
_is_running = False


async def get_kafka_consumer() -> Optional[AIOKafkaConsumer]:
    """获取 Kafka 消费者"""
    global _consumer
    if _consumer is None:
        try:
            _consumer = AIOKafkaConsumer(
                INVENTORY_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            await _consumer.start()
            logger.info(f"Kafka 消费者已启动: {KAFKA_BOOTSTRAP_SERVERS}, Topic: {INVENTORY_TOPIC}")
        except Exception as e:
            logger.error(f"Kafka 消费者启动失败: {e}")
            _consumer = None
    return _consumer


async def close_kafka_consumer():
    """关闭 Kafka 消费者"""
    global _consumer, _is_running
    _is_running = False
    if _consumer:
        await _consumer.stop()
        _consumer = None
        logger.info("Kafka 消费者已关闭")


async def process_inventory_event(event: dict):
    """处理库存变更事件
    
    Args:
        event: 库存变更事件
    """
    event_type = event.get("event_type")
    warehouse_id = event.get("warehouse_id")
    product_id = event.get("product_id")
    quantity = event.get("quantity")
    order_id = event.get("order_id")
    before_stock = event.get("before_stock", 0)
    after_stock = event.get("after_stock", 0)
    
    # 幂等性检查：防止消息重复消费
    db = SessionLocal()
    redis_client = None
    cache_service = None
    
    try:
        # 初始化 Redis 客户端
        from app.core.redis import redis_client as _redis_client
        redis_client = _redis_client
        if redis_client:
            from app.services.inventory_cache import InventoryCacheService
            cache_service = InventoryCacheService(redis_client)
        
        # 检查是否已处理过
        idempotent_key = f"kafka:idempotent:{event_type}:{order_id}:{warehouse_id}:{product_id}"
        if redis_client:
            is_processed = redis_client.get(idempotent_key)
            if is_processed:
                logger.info(f"消息已处理过，跳过: event_type={event_type}, order_id={order_id}")
                return
            
            # 标记为已处理，设置 24 小时过期
            redis_client.setex(idempotent_key, 86400, "1")
        
        # 根据事件类型处理（带行级锁）
        if event_type == "RESERVE":
            await _handle_reserve(db, cache_service, warehouse_id, product_id, quantity, order_id, before_stock, after_stock)
        elif event_type == "CONFIRM":
            await _handle_confirm(db, cache_service, warehouse_id, product_id, quantity, order_id)
        elif event_type == "RELEASE":
            await _handle_release(db, cache_service, warehouse_id, product_id, quantity, order_id)
        elif event_type == "INCREASE":
            await _handle_increase(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "DECREASE":
            await _handle_decrease(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "FREEZE":
            await _handle_freeze(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "UNFREEZE":
            await _handle_unfreeze(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock)
        else:
            logger.warning(f"未知事件类型: {event_type}")
    except Exception as e:
        logger.error(f"处理库存事件失败: {e}, event: {event}")
        db.rollback()
        raise
    finally:
        db.close()


async def _handle_reserve(db, cache_service, warehouse_id, product_id, quantity, order_id, before_stock, after_stock):
    """处理预占事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁防止并发问题
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock -= quantity
        stock.reserved_stock += quantity
        current_available = stock.available_stock
        
        # 记录日志
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_id=order_id,
            change_type=ChangeType.RESERVE,
            quantity=-quantity,
            before_available=before_stock,
            after_available=stock.available_stock,
            before_reserved=stock.reserved_stock - quantity,
            after_reserved=stock.reserved_stock,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步预占: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"预占事件处理完成: {order_id}, 库存扣减 {quantity}")


async def _handle_confirm(db, cache_service, warehouse_id, product_id, quantity, order_id):
    """处理确认事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.reserved_stock -= quantity
        current_available = stock.available_stock
        
        # 更新预占记录状态
        reservations = db.query(InventoryReservation).filter(
            InventoryReservation.order_id == order_id,
            InventoryReservation.product_id == product_id,
            InventoryReservation.status == ReservationStatus.RESERVED
        ).all()
        
        for res in reservations:
            res.status = ReservationStatus.CONFIRMED
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_id=order_id,
            change_type=ChangeType.CONFIRM,
            quantity=0,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存（确认不改变可用库存，只改变预占库存）
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步确认: warehouse={warehouse_id}, product={product_id}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"确认事件处理完成: {order_id}")


async def _handle_release(db, cache_service, warehouse_id, product_id, quantity, order_id):
    """处理释放事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock += quantity
        stock.reserved_stock -= quantity
        current_available = stock.available_stock
        
        # 更新预占记录状态
        reservations = db.query(InventoryReservation).filter(
            InventoryReservation.order_id == order_id,
            InventoryReservation.product_id == product_id,
            InventoryReservation.status == ReservationStatus.RESERVED
        ).all()
        
        for res in reservations:
            res.status = ReservationStatus.RELEASED
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_id=order_id,
            change_type=ChangeType.RELEASE,
            quantity=quantity,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步释放: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"释放事件处理完成: {order_id}, 库存归还 {quantity}")


async def _handle_increase(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理入库事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock += quantity
        current_available = stock.available_stock
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            change_type=ChangeType.INCREASE,
            quantity=quantity,
            before_available=before_stock,
            after_available=stock.available_stock,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步入库: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"入库事件处理完成: 商品 {product_id}, 库存增加 {quantity}")


async def _handle_decrease(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理出库事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock -= quantity
        current_available = stock.available_stock
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            change_type=ChangeType.DECREASE,
            quantity=-quantity,
            before_available=before_stock,
            after_available=stock.available_stock,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步出库: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"出库事件处理完成: 商品 {product_id}, 库存减少 {quantity}")


async def _handle_freeze(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理冻结事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock -= quantity
        stock.frozen_stock += quantity
        current_available = stock.available_stock
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            change_type=ChangeType.FREEZE,
            quantity=-quantity,
            before_available=before_stock,
            after_available=stock.available_stock,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步冻结: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"冻结事件处理完成: 商品 {product_id}, 冻结 {quantity}")


async def _handle_unfreeze(db, cache_service, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理解冻事件（带行级锁）+ Redis 同步"""
    from sqlalchemy import select
    
    # 使用行级锁
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        ).with_for_update()
    ).scalar_one_or_none()
    
    if stock:
        stock.available_stock += quantity
        stock.frozen_stock -= quantity
        current_available = stock.available_stock
        
        log = InventoryLog(
            warehouse_id=warehouse_id,
            product_id=product_id,
            change_type=ChangeType.UNFREEZE,
            quantity=quantity,
            before_available=before_stock,
            after_available=stock.available_stock,
            operator="kafka_consumer"
        )
        db.add(log)
        db.commit()
        
        # 同步更新 Redis 缓存
        if cache_service:
            try:
                cache_service.set_cached_stock(warehouse_id, product_id, current_available)
                logger.debug(f"Redis 已同步解冻: warehouse={warehouse_id}, product={product_id}, stock={current_available}")
            except Exception as e:
                logger.warning(f"Redis 同步失败（不影响主流程）: {e}")
        
        logger.info(f"解冻事件处理完成: 商品 {product_id}, 解冻 {quantity}")


async def start_kafka_consumer():
    """启动 Kafka 消费者循环（带速率限制和消息合并）"""
    global _is_running
    _is_running = True
    
    consumer = await get_kafka_consumer()
    if not consumer:
        logger.error("无法启动 Kafka 消费者")
        return
    
    # 获取速率限制器和消息合并器
    rate_limiter = get_rate_limiter()
    message_merger = get_message_merger()
    
    # 统计信息
    total_processed = 0
    total_merged = 0
    start_time = time.time()
    
    logger.info(
        f"Kafka 消费者开始处理消息... "
        f"速率限制: {KAFKA_MAX_MESSAGES_PER_SECOND} 条/秒, "
        f"合并窗口: {KAFKA_MERGE_WINDOW_MS}ms, "
        f"合并阈值: {KAFKA_MERGE_THRESHOLD}"
    )
    
    try:
        async for message in consumer:
            if not _is_running:
                break
            
            try:
                event = message.value
                logger.debug(f"收到 Kafka 消息: {event}")
                
                # 速率限制：获取令牌，控制处理速度
                wait_time = await rate_limiter.acquire()
                if wait_time > 0:
                    logger.debug(f"速率限制生效，等待 {wait_time:.3f} 秒")
                
                # 添加到消息合并器
                merged_events = await message_merger.add(event)
                
                if merged_events:
                    # 有合并后的消息需要处理
                    for merged_event in merged_events:
                        # 处理合并后的消息
                        await process_inventory_event(merged_event)
                        total_processed += 1
                        total_merged += merged_event.get("_merged_count", 1)
                        logger.debug(
                            f"处理合并消息: {merged_event.get('_merge_info')}, "
                            f"quantity={merged_event.get('quantity')}"
                        )
                else:
                    # 没有达到合并阈值，继续等待
                    pass
                
                # 定期输出统计信息
                if total_processed % 1000 == 0:
                    elapsed = time.time() - start_time
                    actual_rate = total_processed / elapsed if elapsed > 0 else 0
                    merge_stats = message_merger.get_stats()
                    logger.info(
                        f"Kafka 消费统计: 已处理 {total_processed} 条消息, "
                        f"合并减少 {total_merged} 条, "
                        f"实际速率: {actual_rate:.1f} 条/秒"
                    )
                
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
                
    except asyncio.CancelledError:
        logger.info("Kafka 消费者任务被取消")
    except Exception as e:
        logger.error(f"Kafka 消费者异常: {e}")
    finally:
        # 刷新剩余的合并消息
        remaining = await message_merger.flush()
        if remaining:
            for event in remaining:
                try:
                    await process_inventory_event(event)
                    total_processed += 1
                except Exception as e:
                    logger.error(f"处理剩余消息失败: {e}")
        
        # 输出最终统计
        elapsed = time.time() - start_time
        actual_rate = total_processed / elapsed if elapsed > 0 else 0
        logger.info(
            f"Kafka 消费者已停止: 共处理 {total_processed} 条消息, "
            f"合并减少 {total_merged} 条原始消息, "
            f"平均速率: {actual_rate:.1f} 条/秒, 运行时间: {elapsed:.1f} 秒"
        )
        await close_kafka_consumer()
        elapsed = time.time() - start_time
        actual_rate = total_processed / elapsed if elapsed > 0 else 0
        logger.info(
            f"Kafka 消费者已停止: 共处理 {total_processed} 条消息, "
            f"平均速率: {actual_rate:.1f} 条/秒, 运行时间: {elapsed:.1f} 秒"
        )
        await close_kafka_consumer()
