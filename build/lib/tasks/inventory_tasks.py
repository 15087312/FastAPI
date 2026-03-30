"""库存相关的 Celery 任务（企业级实现）"""

from celery_app import app
from app.db.session import SessionLocal
from app.services.inventory_service import InventoryService
from app.core.redis import redis_client
import logging

logger = logging.getLogger(__name__)

@app.task(name='tasks.inventory.process_reservation')
def process_reservation(order_id: str, product_items: list):
    """处理库存预占的异步任务
    
    Args:
        order_id: 订单ID
        product_items: 商品项列表 [{"warehouse_id": "WH01", "product_id": 1, "quantity": 2}, ...]
    """
    db = SessionLocal()
    try:
        service = InventoryService(db, redis_client)
        # 调用批量预占逻辑
        result = service.reserve_batch(order_id, product_items)
        db.commit()
        logger.info(f"处理订单预占: {order_id}, result: {result}")
        return {"status": "success", "order_id": order_id, "result": result}
    except Exception as e:
        logger.error(f"处理订单预占失败: {order_id}, error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

@app.task(name='tasks.inventory.cleanup_expired_reservations')  
def cleanup_expired_reservations(batch_size: int = 500):
    """清理过期的预占记录（企业级实现）
    
    Args:
        batch_size: 批处理大小，默认500条
    
    Returns:
        清理的记录数量描述
    """
    db = SessionLocal()
    try:
        service = InventoryService(db, redis_client)
        count = service.cleanup_expired_reservations(batch_size)
        db.commit()
        result = f"成功清理 {count} 条过期预占记录"
        logger.info(result)
        return result
    except Exception as e:
        logger.error(f"清理过期预占任务执行失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

@app.task(name='tasks.inventory.sync_redis_to_db')
def sync_redis_to_db(warehouse_id: str = None):
    """同步数据库库存到 Redis 缓存（定时任务）
    
    按仓库全量同步数据库中的库存数据到 Redis。
    用于在 Redis 数据丢失或不一致时恢复缓存。
    
    Args:
        warehouse_id: 可选，指定仓库ID。为 None 时同步所有仓库。
    
    Returns:
        同步结果描述
    """
    from app.models.product_stocks import ProductStock
    from app.services.inventory_cache import InventoryCacheService
    
    db = SessionLocal()
    try:
        if not redis_client:
            logger.warning("Redis 不可用，跳过同步")
            return {"status": "skipped", "reason": "Redis unavailable"}
        
        cache_service = InventoryCacheService(redis_client)
        
        # 查询需要同步的仓库
        if warehouse_id:
            warehouses = [(warehouse_id,)]
        else:
            warehouses = db.query(ProductStock.warehouse_id).distinct().all()
        
        total_synced = 0
        for wh in warehouses:
            wh_id = wh[0]
            
            # 查询该仓库的所有库存
            stocks = db.query(ProductStock).filter(
                ProductStock.warehouse_id == wh_id
            ).all()
            
            if not stocks:
                continue
            
            # 构建库存映射
            stock_map = {s.product_id: s.available_stock for s in stocks}
            
            # 批量写入 Redis
            cache_service.batch_set_cached_stocks(wh_id, stock_map)
            total_synced += len(stock_map)
            
            logger.info(f"仓库 {wh_id} 同步完成: {len(stock_map)} 条记录")
        
        result = f"Redis 同步完成，共 {total_synced} 条记录"
        logger.info(result)
        return {"status": "success", "synced_count": total_synced, "warehouses": len(warehouses)}
    
    except Exception as e:
        logger.error(f"Redis 同步任务失败: {str(e)}")
        raise
    finally:
        db.close()


@app.task(name='tasks.inventory.verify_redis_db_consistency')
def verify_redis_db_consistency(warehouse_id: str = None, sample_size: int = 100):
    """校验 Redis 与数据库一致性（定时任务）
    
    抽样对比 Redis 和数据库的库存数据，
    发现不一致时自动修复并记录日志。
    
    Args:
        warehouse_id: 可选，指定仓库ID。为 None 时校验所有仓库。
        sample_size: 抽样大小，默认 100 条
    
    Returns:
        校验结果
    """
    from app.models.product_stocks import ProductStock
    from app.services.inventory_cache import InventoryCacheService
    import random
    
    db = SessionLocal()
    try:
        if not redis_client:
            logger.warning("Redis 不可用，跳过校验")
            return {"status": "skipped", "reason": "Redis unavailable"}
        
        cache_service = InventoryCacheService(redis_client)
        
        # 查询需要校验的仓库
        if warehouse_id:
            warehouses = [(warehouse_id,)]
        else:
            warehouses = db.query(ProductStock.warehouse_id).distinct().all()
        
        inconsistent_count = 0
        fixed_count = 0
        
        for wh in warehouses:
            wh_id = wh[0]
            
            # 查询该仓库的库存（可抽样）
            if sample_size > 0:
                stocks = db.query(ProductStock).filter(
                    ProductStock.warehouse_id == wh_id
                ).limit(sample_size).all()
            else:
                stocks = db.query(ProductStock).filter(
                    ProductStock.warehouse_id == wh_id
                ).all()
            
            for stock in stocks:
                # 从 Redis 获取缓存值
                redis_value = cache_service.get_cached_stock(wh_id, stock.product_id)
                db_value = stock.available_stock
                
                # 比较一致性
                if redis_value is not None and redis_value != db_value:
                    inconsistent_count += 1
                    logger.warning(
                        f"发现不一致: warehouse={wh_id}, product={stock.product_id}, "
                        f"Redis={redis_value}, DB={db_value}"
                    )
                    
                    # 自动修复：使用数据库值覆盖 Redis
                    cache_service.set_cached_stock(wh_id, stock.product_id, db_value)
                    fixed_count += 1
        
        result = f"一致性校验完成: 发现 {inconsistent_count} 条不一致，已修复 {fixed_count} 条"
        logger.info(result)
        return {
            "status": "success", 
            "inconsistent_count": inconsistent_count,
            "fixed_count": fixed_count
        }
    
    except Exception as e:
        logger.error(f"一致性校验任务失败: {str(e)}")
        raise
    finally:
        db.close()

# 导出任务
__all__ = [
    'process_reservation',
    'cleanup_expired_reservations', 
    'sync_redis_to_db',
    'verify_redis_db_consistency'
]