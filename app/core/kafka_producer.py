"""Kafka 生产者模块 - 用于发送库存变更消息"""

import os
import json
import asyncio
import logging
from typing import Optional
from datetime import datetime
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

# Kafka 配置
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
INVENTORY_TOPIC = "inventory-changes"

# 全局生产者实例
_producer: Optional[AIOKafkaProducer] = None
_kafka_available = False


async def get_kafka_producer() -> Optional[AIOKafkaProducer]:
    """获取 Kafka 生产者单例"""
    global _producer, _kafka_available
    
    if _producer is None and not _kafka_available:
        try:
            _producer = AIOKafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )
            await asyncio.wait_for(_producer.start(), timeout=5.0)
            _kafka_available = True
            logger.info(f"Kafka 生产者已启动: {KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.warning(f"Kafka 生产者启动失败: {e}")
            _kafka_available = False
            _producer = None
    
    return _producer


async def close_kafka_producer():
    """关闭 Kafka 生产者"""
    global _producer, _kafka_available
    if _producer:
        try:
            await _producer.stop()
        except Exception as e:
            logger.warning(f"关闭 Kafka 生产者时出错: {e}")
        _producer = None
        _kafka_available = False
        logger.info("Kafka 生产者已关闭")


async def send_inventory_event(
    event_type: str,
    warehouse_id: str,
    product_id: int,
    quantity: int,
    order_id: str,
    before_stock: int = 0,
    after_stock: int = 0,
    remark: str = None
):
    """发送库存变更事件
    
    Args:
        event_type: 事件类型 (RESERVE, CONFIRM, RELEASE, INCREASE, DECREASE)
        warehouse_id: 仓库 ID
        product_id: 商品 ID
        quantity: 变更数量
        order_id: 订单 ID
        before_stock: 变更前库存
        after_stock: 变更后库存
        remark: 备注
    """
    event = {
        "event_type": event_type,
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "quantity": quantity,
        "order_id": order_id,
        "before_stock": before_stock,
        "after_stock": after_stock,
        "remark": remark,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        producer = await get_kafka_producer()
        if producer:
            # 使用 order_id 作为消息 key，保证同一订单的消息有序
            key = f"{warehouse_id}:{product_id}:{order_id}"
            await producer.send_and_wait(INVENTORY_TOPIC, event, key=key)
            logger.info(f"Kafka 消息已发送: {event_type} - {order_id}")
        else:
            logger.warning("Kafka 生产者未初始化，消息未发送")
    except Exception as e:
        # 记录错误但不影响主业务
        logger.error(f"Kafka 消息发送失败: {e}")


# 事件类型常量
class InventoryEventType:
    RESERVE = "RESERVE"       # 预占
    CONFIRM = "CONFIRM"       # 确认
    RELEASE = "RELEASE"       # 释放
    INCREASE = "INCREASE"     # 入库
    DECREASE = "DECREASE"     # 出库
    FREEZE = "FREEZE"         # 冻结
    UNFREEZE = "UNFREEZE"     # 解冻
