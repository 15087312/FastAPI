from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from typing import Generator
from sqlalchemy.orm import Session
import multiprocessing
import os

# 计算最优连接池大小
# 假设 PostgreSQL 默认 max_connections = 100
# 根据预估的 worker 数量计算每个 worker 的连接池大小
# 公式：recommended_pool_size = max(2, max_connections // max_workers)
# 预留一些连接给管理员和运维工具
cpu_count = multiprocessing.cpu_count()
estimated_workers = min(cpu_count * 2 + 1, 8)  # 最多 8 个 worker
postgresql_max_connections = 100  # PostgreSQL 默认 max_connections
reserved_connections = 10  # 预留连接给运维工具
available_for_app = postgresql_max_connections - reserved_connections
recommended_pool_size = max(2, available_for_app // estimated_workers)

# 从环境变量读取，如果未设置则使用计算出的推荐值
default_pool_size = int(os.getenv("DB_POOL_SIZE", str(recommended_pool_size)))
default_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", str(recommended_pool_size * 2)))

print(f"数据库连接池配置: pool_size={default_pool_size}, max_overflow={default_max_overflow}, estimated_workers={estimated_workers}")

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