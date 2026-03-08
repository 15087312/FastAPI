import os
from dotenv import load_dotenv
import socket
from pydantic_settings import BaseSettings

# 加载 .env 文件
load_dotenv()

class Settings(BaseSettings):
    # 应用配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # 数据库配置（从环境变量读取）
    # ⚠️ Docker 环境：POSTGRES_HOST 默认为 "db"（Docker 服务名）
    # ⚠️ 本地环境：在 .env 文件中设置 POSTGRES_HOST=localhost
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "123456")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")  # Docker 环境默认使用 db
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "mydb")
    
    # Redis 配置（从环境变量读取）
    # ⚠️ Docker 环境：REDIS_HOST 默认为 "redis"（Docker 服务名）
    # ⚠️ 本地环境：在 .env 文件中设置 REDIS_HOST=localhost
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # Docker 环境默认使用 redis
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

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