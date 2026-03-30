"""系统监控 API 路由器 - 提供系统资源监控接口"""

import os
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["系统监控"])

# 尝试导入 psutil，处理不存在的情况
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil 未安装，系统监控功能将受限。请运行：pip install psutil")

from app.schemas.system import (
    SystemMetricsResponse,
    CpuResponse,
    MemoryResponse,
    DiskResponse,
    NetworkResponse,
    DatabasePoolResponse,
    RedisConnectionResponse
)

def _format_bytes(bytes_value: int) -> str:
    """格式化字节数为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def _get_timestamp() -> str:
    """获取当前时间戳"""
    return datetime.now().isoformat()


@router.get("/cpu", response_model=CpuResponse, summary="获取 CPU 使用率")
async def get_cpu_usage():
    """
    获取 CPU 使用率信息
    
    返回 CPU 总体使用率、核心数、频率等信息
    """
    if not PSUTIL_AVAILABLE:
        raise HTTPException(status_code=503, detail="psutil 库未安装，无法获取 CPU 信息")
    
    try:
        # 获取 CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        
        # 获取 CPU 频率
        cpu_freq = None
        try:
            freq = psutil.cpu_freq()
            if freq:
                cpu_freq = {
                    "current": round(freq.current, 2),
                    "min": round(freq.min, 2) if freq.min else None,
                    "max": round(freq.max, 2) if freq.max else None
                }
        except Exception:
            pass
        
        # 获取每个 CPU 核心的使用率
        per_cpu = None
        try:
            per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
        except Exception:
            pass
        
        return CpuResponse(
            success=True,
            timestamp=_get_timestamp(),
            cpu_percent=round(cpu_percent, 2),
            cpu_count=cpu_count,
            cpu_freq=cpu_freq,
            per_cpu=[round(x, 2) for x in per_cpu] if per_cpu else None
        )
    except Exception as e:
        logger.error(f"获取 CPU 使用率失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 CPU 使用率失败: {str(e)}")


@router.get("/memory", response_model=MemoryResponse, summary="获取内存使用率")
async def get_memory_usage():
    """
    获取内存使用率信息
    
    返回内存总量、可用内存、已使用内存和使用率
    """
    if not PSUTIL_AVAILABLE:
        raise HTTPException(status_code=503, detail="psutil 库未安装，无法获取内存信息")
    
    try:
        memory = psutil.virtual_memory()
        
        return MemoryResponse(
            success=True,
            timestamp=_get_timestamp(),
            total=memory.total,
            available=memory.available,
            used=memory.used,
            percent=round(memory.percent, 2)
        )
    except Exception as e:
        logger.error(f"获取内存使用率失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取内存使用率失败: {str(e)}")


@router.get("/disk", response_model=DiskResponse, summary="获取磁盘使用率")
async def get_disk_usage():
    """
    获取磁盘使用率信息
    
    返回磁盘总量、已使用空间、可用空间和使用率
    """
    if not PSUTIL_AVAILABLE:
        raise HTTPException(status_code=503, detail="psutil 库未安装，无法获取磁盘信息")
    
    try:
        disk = psutil.disk_usage('/')
        
        return DiskResponse(
            success=True,
            timestamp=_get_timestamp(),
            total=disk.total,
            used=disk.used,
            free=disk.free,
            percent=round(disk.percent, 2)
        )
    except Exception as e:
        logger.error(f"获取磁盘使用率失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取磁盘使用率失败: {str(e)}")


@router.get("/network", response_model=NetworkResponse, summary="获取网络流量")
async def get_network_traffic():
    """
    获取网络流量信息
    
    返回发送/接收的字节数、数据包数、错误数等
    """
    if not PSUTIL_AVAILABLE:
        raise HTTPException(status_code=503, detail="psutil 库未安装，无法获取网络信息")
    
    try:
        net_io = psutil.net_io_counters()
        
        return NetworkResponse(
            success=True,
            timestamp=_get_timestamp(),
            bytes_sent=net_io.bytes_sent,
            bytes_recv=net_io.bytes_recv,
            packets_sent=net_io.packets_sent,
            packets_recv=net_io.packets_recv,
            errin=net_io.errin,
            errout=net_io.errout
        )
    except Exception as e:
        logger.error(f"获取网络流量失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取网络流量失败: {str(e)}")


@router.get("/db-pool", response_model=DatabasePoolResponse, summary="获取数据库连接池状态")
async def get_db_pool_status():
    """
    获取数据库连接池状态
    
    返回连接池大小、已借出连接数、溢出连接数等信息
    """
    try:
        from app.db.session import engine
        
        # 获取连接池状态
        pool = engine.pool
        
        # 获取详细信息
        pool_status = {
            "pool_size": pool.size(),  # 总连接池大小
            "checked_in": pool.checkedin(),  # 空闲连接数
            "checked_out": pool.checkedout(),  # 已借出连接数
            "overflow": pool.overflow(),  # 溢出连接数
            "invalid": pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else 0  # 失效连接数
        }
        
        return DatabasePoolResponse(
            success=True,
            timestamp=_get_timestamp(),
            **pool_status
        )
    except Exception as e:
        logger.error(f"获取数据库连接池状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取数据库连接池状态失败: {str(e)}")


@router.get("/redis", response_model=RedisConnectionResponse, summary="获取 Redis 连接信息")
async def get_redis_info():
    """
    获取 Redis 连接信息
    
    返回 Redis 客户端连接数、内存使用、运行时间等信息
    """
    try:
        from app.core.redis import sync_redis
        
        # 获取 Redis info
        info = sync_redis.info()
        
        return RedisConnectionResponse(
            success=True,
            timestamp=_get_timestamp(),
            connected_clients=info.get("connected_clients", 0),
            used_memory=info.get("used_memory", 0),
            used_memory_human=info.get("used_memory_human", "0B"),
            total_connections_received=info.get("total_connections_received", 0),
            total_commands_processed=info.get("total_commands_processed", 0),
            uptime_seconds=info.get("uptime_in_seconds", 0),
            version=info.get("redis_version", "unknown")
        )
    except Exception as e:
        logger.error(f"获取 Redis 信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 Redis 信息失败: {str(e)}")


@router.get("/metrics", response_model=SystemMetricsResponse, summary="获取所有系统指标")
async def get_all_metrics():
    """
    获取所有系统监控指标
    
    一次性返回 CPU、内存、磁盘、网络、数据库连接池、Redis 连接等信息
    """
    result = {
        "timestamp": _get_timestamp()
    }
    
    # CPU 使用率
    if PSUTIL_AVAILABLE:
        try:
            result["cpu"] = {
                "percent": round(psutil.cpu_percent(interval=0.1), 2),
                "count": psutil.cpu_count()
            }
        except Exception as e:
            result["cpu"] = {"error": str(e)}
    
    # 内存使用率
    if PSUTIL_AVAILABLE:
        try:
            memory = psutil.virtual_memory()
            result["memory"] = {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": round(memory.percent, 2)
            }
        except Exception as e:
            result["memory"] = {"error": str(e)}
    
    # 磁盘使用率
    if PSUTIL_AVAILABLE:
        try:
            disk = psutil.disk_usage('/')
            result["disk"] = {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": round(disk.percent, 2)
            }
        except Exception as e:
            result["disk"] = {"error": str(e)}
    
    # 网络流量
    if PSUTIL_AVAILABLE:
        try:
            net_io = psutil.net_io_counters()
            result["network"] = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception as e:
            result["network"] = {"error": str(e)}
    
    # 数据库连接池
    try:
        from app.db.session import engine
        pool = engine.pool
        result["database_pool"] = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow()
        }
    except Exception as e:
        result["database_pool"] = {"error": str(e)}
    
    # Redis 连接
    try:
        from app.core.redis import sync_redis
        info = sync_redis.info()
        result["redis"] = {
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "version": info.get("redis_version", "unknown")
        }
    except Exception as e:
        result["redis"] = {"error": str(e)}
    
    return SystemMetricsResponse(
        success=True,
        timestamp=_get_timestamp(),
        data=result
    )
