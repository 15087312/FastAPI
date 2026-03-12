"""Kafka 消费者服务 - 消费库存变更消息并更新数据库"""

import os
import json
import asyncio
import logging
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
CONSUMER_GROUP = "inventory-consumer-group"

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
    
    db = SessionLocal()
    try:
        # 根据事件类型处理
        if event_type == "RESERVE":
            await _handle_reserve(db, warehouse_id, product_id, quantity, order_id, before_stock, after_stock)
        elif event_type == "CONFIRM":
            await _handle_confirm(db, warehouse_id, product_id, quantity, order_id)
        elif event_type == "RELEASE":
            await _handle_release(db, warehouse_id, product_id, quantity, order_id)
        elif event_type == "INCREASE":
            await _handle_increase(db, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "DECREASE":
            await _handle_decrease(db, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "FREEZE":
            await _handle_freeze(db, warehouse_id, product_id, quantity, before_stock, after_stock)
        elif event_type == "UNFREEZE":
            await _handle_unfreeze(db, warehouse_id, product_id, quantity, before_stock, after_stock)
        else:
            logger.warning(f"未知事件类型: {event_type}")
    except Exception as e:
        logger.error(f"处理库存事件失败: {e}, event: {event}")
        db.rollback()
        raise
    finally:
        db.close()


async def _handle_reserve(db, warehouse_id, product_id, quantity, order_id, before_stock, after_stock):
    """处理预占事件"""
    # 查询库存记录
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock -= quantity
        stock.reserved_stock += quantity
        
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
        logger.info(f"预占事件处理完成: {order_id}, 库存扣减 {quantity}")


async def _handle_confirm(db, warehouse_id, product_id, quantity, order_id):
    """处理确认事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.reserved_stock -= quantity
        
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
        logger.info(f"确认事件处理完成: {order_id}")


async def _handle_release(db, warehouse_id, product_id, quantity, order_id):
    """处理释放事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock += quantity
        stock.reserved_stock -= quantity
        
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
        logger.info(f"释放事件处理完成: {order_id}, 库存归还 {quantity}")


async def _handle_increase(db, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理入库事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock += quantity
        
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
        logger.info(f"入库事件处理完成: 商品 {product_id}, 库存增加 {quantity}")


async def _handle_decrease(db, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理出库事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock -= quantity
        
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
        logger.info(f"出库事件处理完成: 商品 {product_id}, 库存减少 {quantity}")


async def _handle_freeze(db, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理冻结事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock -= quantity
        stock.frozen_stock += quantity
        
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
        logger.info(f"冻结事件处理完成: 商品 {product_id}, 冻结 {quantity}")


async def _handle_unfreeze(db, warehouse_id, product_id, quantity, before_stock, after_stock):
    """处理解冻事件"""
    stock = db.query(ProductStock).filter(
        ProductStock.warehouse_id == warehouse_id,
        ProductStock.product_id == product_id
    ).first()
    
    if stock:
        stock.available_stock += quantity
        stock.frozen_stock -= quantity
        
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
        logger.info(f"解冻事件处理完成: 商品 {product_id}, 解冻 {quantity}")


async def start_kafka_consumer():
    """启动 Kafka 消费者循环"""
    global _is_running
    _is_running = True
    
    consumer = await get_kafka_consumer()
    if not consumer:
        logger.error("无法启动 Kafka 消费者")
        return
    
    logger.info("Kafka 消费者开始处理消息...")
    
    try:
        async for message in consumer:
            if not _is_running:
                break
            try:
                event = message.value
                logger.debug(f"收到 Kafka 消息: {event}")
                await process_inventory_event(event)
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
    except asyncio.CancelledError:
        logger.info("Kafka 消费者任务被取消")
    except Exception as e:
        logger.error(f"Kafka 消费者异常: {e}")
    finally:
        await close_kafka_consumer()
