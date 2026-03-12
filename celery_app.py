"""Celery 配置文件"""

import os
from celery import Celery
from celery.schedules import crontab

# 创建 Celery 应用实例
app = Celery('inventory_worker')

# 从环境变量获取 Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

# 配置 Redis 作为 broker 和 backend
app.conf.broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
app.conf.result_backend = f"redis://{REDIS_HOST}:{REDIS_PORT}/2"

# 任务序列化配置
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# 时区配置
app.conf.timezone = 'Asia/Shanghai'
app.conf.enable_utc = True

# 任务路由配置（可选）
app.conf.task_routes = {
    'tasks.inventory.*': {'queue': 'inventory'},
    'tasks.notification.*': {'queue': 'notification'},
}

# Worker 配置
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# 定时任务配置（Celery Beat）
app.conf.beat_schedule = {
    # 每小时同步一次 Redis 缓存
    'sync-redis-every-hour': {
        'task': 'tasks.inventory.sync_redis_to_db',
        'schedule': 3600.0,  # 1 小时
        'options': {
            'queue': 'inventory',
        }
    },
    # 每小时校验一次 Redis 与数据库一致性
    'verify-consistency-every-hour': {
        'task': 'tasks.inventory.verify_redis_db_consistency',
        'schedule': 3600.0,  # 1 小时
        'options': {
            'queue': 'inventory',
        }
    },
    # 每天凌晨 3 点清理过期预占
    'cleanup-expired-reservations-daily': {
        'task': 'tasks.inventory.cleanup_expired_reservations',
        'schedule': crontab(hour=3, minute=0),  # 每天凌晨 3 点
        'options': {
            'queue': 'inventory',
        }
    },
}

# 导出应用实例
__all__ = ['app']