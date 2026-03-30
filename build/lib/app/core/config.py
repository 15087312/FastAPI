import os
import re
from dotenv import load_dotenv
import socket
from pydantic_settings import BaseSettings
from pydantic import field_validator

# 加载 .env 文件
load_dotenv()

class Settings(BaseSettings):
    # 应用配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # 数据库配置（从环境变量读取）
    # ⚠️ Docker 环境：POSTGRES_HOST 默认为 "db"（Docker 服务名）
    # ⚠️ 本地环境：在 .env 文件中设置 POSTGRES_HOST=localhost
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD")  # 必须从环境变量读取，不提供默认值
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")  # Docker 环境默认使用 db
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "mydb")
    
    # Redis 配置（从环境变量读取）
    # ⚠️ Docker 环境：REDIS_HOST 默认为 "redis"（Docker 服务名）
    # ⚠️ 本地环境：在 .env 文件中设置 REDIS_HOST=localhost
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # Docker 环境默认使用 redis
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")  # Redis 密码（可选）
    
    # 限流配置
    RATE_LIMIT_REQUESTS_PER_SECOND: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_SECOND", "50"))
    RATE_LIMIT_BURST_SIZE: int = int(os.getenv("RATE_LIMIT_BURST_SIZE", "100"))
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    
    # pgAdmin 配置
    PGADMIN_EMAIL: str = os.getenv("PGADMIN_EMAIL", "admin@example.com")
    PGADMIN_PASSWORD: str = os.getenv("PGADMIN_PASSWORD", "")  # 可选配置
    
    # 数据库连接池配置
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))  # 默认 10，根据 worker 数动态调整
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))  # 默认 20
    
    @field_validator('POSTGRES_PASSWORD')
    @classmethod
    def validate_postgres_password(cls, v):
        """验证数据库密码强度（生产环境应使用强密码）"""
        if not v:
            raise ValueError('POSTGRES_PASSWORD 环境变量必须设置')
        # 测试环境允许简单密码，生产环境建议使用强密码
        if len(v) < 6:
            raise ValueError('数据库密码长度至少 6 位')
        return v
    
    @field_validator('PGADMIN_PASSWORD')
    @classmethod
    def validate_pgadmin_password(cls, v):
        """验证 pgAdmin 密码强度"""
        # 允许空字符串
        return v if v else ""
    
        @field_validator('REDIS_PASSWORD')
        @classmethod
        def validate_redis_password(cls, v):
            """验证 Redis 密码（可选）"""
            # 允许空字符串
            return v if v else ""
        
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://" 
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

settings = Settings()

def is_port_available(host: str, port: int) -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False

def find_available_port(host: str, start_port: int, max_attempts: int = 10) -> int:
    """查找可用的端口，从 start_port 开始尝试"""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"无法在 {host} 上找到可用端口 (范围：{start_port}-{start_port + max_attempts - 1})")