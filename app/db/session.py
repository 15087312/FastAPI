from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from typing import Generator
from sqlalchemy.orm import Session
import multiprocessing
import os

# 计算最优连接池大小
# 公式：workers × 2 + 1（参考 uvicorn workers 计算）
# 如果设置了环境变量，优先使用环境变量
default_pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
default_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "40"))

engine = create_engine(
    settings.database_url,
    pool_size=default_pool_size,      # 连接池大小，默认 20
    max_overflow=default_max_overflow,  # 最大溢出连接数，默认 40
    pool_pre_ping=True,               # 自动检测失效连接
    pool_recycle=1800,                # 30 分钟回收连接
    pool_timeout=30,                  # 获取连接超时时间
    echo=settings.DEBUG,              # 开发环境开启 SQL 日志
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# 依赖注入函数
def get_db() -> Generator[Session, None, None]:
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()