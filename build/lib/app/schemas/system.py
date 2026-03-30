"""系统监控相关的 Schema 模型"""

from typing import Dict, Any, Optional
from pydantic import BaseModel


class SystemMetricsResponse(BaseModel):
    """系统指标响应"""
    success: bool = True
    timestamp: str = ""
    data: Dict[str, Any] = {}


class CpuResponse(BaseModel):
    """CPU 使用率响应"""
    success: bool = True
    timestamp: str = ""
    cpu_percent: float = 0.0
    cpu_count: int = 0
    cpu_freq: Optional[Dict[str, Any]] = None
    per_cpu: Optional[list] = None


class MemoryResponse(BaseModel):
    """内存使用率响应"""
    success: bool = True
    timestamp: str = ""
    total: int = 0
    available: int = 0
    used: int = 0
    percent: float = 0.0


class DiskResponse(BaseModel):
    """磁盘使用率响应"""
    success: bool = True
    timestamp: str = ""
    total: int = 0
    used: int = 0
    free: int = 0
    percent: float = 0.0


class NetworkResponse(BaseModel):
    """网络流量响应"""
    success: bool = True
    timestamp: str = ""
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    errin: int = 0
    errout: int = 0


class DatabasePoolResponse(BaseModel):
    """数据库连接池响应"""
    success: bool = True
    timestamp: str = ""
    pool_size: int = 0
    checked_in: int = 0
    checked_out: int = 0
    overflow: int = 0
    invalid: int = 0


class RedisConnectionResponse(BaseModel):
    """Redis 连接响应"""
    success: bool = True
    timestamp: str = ""
    connected_clients: int = 0
    used_memory: int = 0
    used_memory_human: str = ""
    total_connections_received: int = 0
    total_commands_processed: int = 0
    uptime_seconds: int = 0
    version: str = ""
