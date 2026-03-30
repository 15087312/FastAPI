"""库存清理本地执行脚本（企业级实现）"""

import argparse
import logging
from app.db.session import SessionLocal
from app.services.inventory_service import InventoryService
from app.core.redis import redis_client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_cleanup(batch_size: int = 500, dry_run: bool = False):
    """执行库存清理
    
    Args:
        batch_size: 批处理大小
        dry_run: 是否为试运行模式（不实际执行清理）
    """
    db = SessionLocal()
    try:
        if dry_run:
            # 试运行模式：只统计待清理记录数量
            from sqlalchemy import select
            from app.models.inventory_reservations import InventoryReservation, ReservationStatus
            from datetime import datetime
            
            expired_count = db.execute(
                select(InventoryReservation)
                .where(
                    InventoryReservation.status == ReservationStatus.RESERVED,
                    InventoryReservation.expired_at <= datetime.utcnow()
                )
            ).count()
            
            logger.info(f"试运行模式：发现 {expired_count} 条过期预占记录待清理")
            return expired_count
        else:
            # 实际执行清理
            service = InventoryService(db, redis_client)
            count = service.cleanup_expired_reservations(batch_size)
            db.commit()
            logger.info(f"清理完成：成功清理 {count} 条过期预占记录")
            return count
            
    except Exception as e:
        logger.error(f"清理执行失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='库存过期预占清理工具')
    parser.add_argument(
        '--batch-size', 
        type=int, 
        default=500,
        help='批处理大小 (默认: 500)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='试运行模式，只统计不执行清理'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='详细输出模式'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        result = run_cleanup(args.batch_size, args.dry_run)
        if args.dry_run:
            print(f"📊 试运行结果：发现 {result} 条过期记录")
        else:
            print(f"✅ 清理完成：处理了 {result} 条记录")
    except Exception as e:
        print(f"❌ 执行失败: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())