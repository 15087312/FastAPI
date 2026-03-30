"""数据库会话管理 - 支持HTTP接口和Kafka消费者"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import multiprocessing
import os

print("数据库模块已加载...")

# 强制使用高连接池配置（确保支持高并发）
# 如果环境变量设置了较低的值，这里强制覆盖
DB_POOL_SIZE = 50  # 强制使用50
DB_MAX_OVERFLOW = 100  # 强制使用100

# 创建主数据库引擎（HTTP接口和启动预热使用）
print(f"创建主数据库连接池: pool_size={DB_POOL_SIZE}, max_overflow={DB_MAX_OVERFLOW}")
engine = create_engine(
    settings.database_url,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
print(f"✅ 主数据库连接池已初始化：pool_size={DB_POOL_SIZE}, max_overflow={DB_MAX_OVERFLOW}")