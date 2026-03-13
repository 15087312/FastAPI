"""结构化日志模块

提供 JSON 格式的结构化日志功能，支持：
- JSON 格式输出
- 自动收集上下文信息（trace_id, user_id 等）
- 日志级别过滤
- 多输出目标（控制台、文件）
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from functools import wraps
import uuid

# 配置
LOG_FORMAT_JSON = os.getenv("LOG_FORMAT_JSON", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_INCLUDE_STACKTRACE = os.getenv("LOG_INCLUDE_STACKTRACE", "false").lower() == "true"


class StructuredLogFormatter(logging.Formatter):
    """结构化日志格式化器 - 输出 JSON 格式"""
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """将日志记录格式化为 JSON"""
        # 构建基础日志结构
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加线程和进程信息
        if hasattr(record, 'thread_id'):
            log_data["thread_id"] = record.thread_id
        else:
            log_data["thread_id"] = record.thread
        
        log_data["process_id"] = record.process
        
        # 添加 extra 字段（自定义上下文）
        if self.include_extra:
            extra_keys = [
                "trace_id", "user_id", "order_id", "warehouse_id", "product_id",
                "request_id", "session_id", "ip_address", "user_agent"
            ]
            for key in extra_keys:
                if hasattr(record, key):
                    log_data[key] = getattr(record, key)
            
            # 添加其他 extra 字段
            if hasattr(record, 'extra_data'):
                log_data["extra"] = getattr(record, 'extra_data', {})
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }
            if LOG_INCLUDE_STACKTRACE:
                log_data["exception"]["stack_trace"] = traceback.format_exception(*record.exc_info)
        
        # 添加性能信息（如果有）
        if hasattr(record, 'duration_ms'):
            log_data["duration_ms"] = record.duration_ms
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class PlainLogFormatter(logging.Formatter):
    """普通日志格式化器 - 输出易读的文本格式"""
    
    def __init__(self):
        super().__init__(
            fmt="%(asctime)s | %(level)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


class StructuredLogger:
    """结构化日志记录器 - 便捷的结构化日志接口"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, LOG_LEVEL))
    
    def _log(self, level: int, message: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        """通用日志方法"""
        extra = {}
        if extra_data:
            extra["extra_data"] = extra_data
        
        # 添加其他上下文
        for key, value in kwargs.items():
            if value is not None:
                extra[key] = value
        
        self.logger.log(level, message, extra=extra, stacklevel=3)
    
    def debug(self, message: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self._log(logging.DEBUG, message, extra_data, **kwargs)
    
    def info(self, message: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self._log(logging.INFO, message, extra_data, **kwargs)
    
    def warning(self, message: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self._log(logging.WARNING, message, extra_data, **kwargs)
    
    def error(self, message: str, extra_data: Optional[Dict[str, Any]] = None, exc_info: bool = False, **kwargs):
        self.logger.error(message, extra={"extra_data": extra_data, **kwargs}, exc_info=exc_info, stacklevel=3)
    
    def critical(self, message: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self._log(logging.CRITICAL, message, extra_data, **kwargs)
    
    def log_performance(self, operation: str, duration_ms: float, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        """记录性能日志"""
        extra = {"duration_ms": duration_ms, "extra_data": extra_data or {}}
        extra.update(kwargs)
        self.logger.info(f"[PERF] {operation} took {duration_ms:.2f}ms", extra=extra)
    
    def log_api(self, method: str, path: str, status_code: int, duration_ms: float, 
                user_id: Optional[str] = None, ip_address: Optional[str] = None, extra_data: Optional[Dict[str, Any]] = None):
        """记录 API 请求日志"""
        log_data = {
            "api": {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
            "extra": extra_data or {}
        }
        self.logger.info(
            f"{method} {path} {status_code} {duration_ms:.2f}ms",
            extra={
                "trace_id": kwargs.get("trace_id", str(uuid.uuid4())),
                "user_id": user_id,
                "ip_address": ip_address,
                "extra_data": log_data
            }
        )


def get_structured_logger(name: str) -> StructuredLogger:
    """获取结构化日志记录器"""
    return StructuredLogger(name)


def setup_logging(
    log_level: str = None,
    log_format: str = "json",
    log_file: Optional[str] = None
):
    """配置日志系统
    
    Args:
        log_level: 日志级别
        log_format: 日志格式 ("json" 或 "plain")
        log_file: 日志文件路径（可选）
    """
    global LOG_LEVEL, LOG_FORMAT_JSON
    
    if log_level:
        LOG_LEVEL = log_level.upper()
    
    log_format_json = log_format.lower() == "json"
    
    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    
    if log_format_json:
        formatter = StructuredLogFormatter()
    else:
        formatter = PlainLogFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, LOG_LEVEL))
        file_handler.setFormatter(StructuredLogFormatter())
        root_logger.addHandler(file_handler)
    
    return root_logger


class LogContext:
    """日志上下文管理器 - 为代码块提供统一的日志上下文"""
    
    def __init__(self, logger: StructuredLogger, **context):
        self.logger = logger
        self.context = context
        self.old_extra = {}
    
    def __enter__(self):
        # 保存当前的 extra 状态
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(
                f"Exception in context: {exc_val}",
                extra_data={"exception_type": exc_type.__name__, **self.context},
                exc_info=(exc_type, exc_val, exc_tb)
            )
        return False


def log_function_call(logger: StructuredLogger):
    """装饰器：自动记录函数调用"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = datetime.now()
            
            logger.debug(
                f"Calling {func_name}",
                extra_data={
                    "function": func_name,
                    "args": str(args)[:200],
                    "kwargs": {k: str(v)[:100] for k, v in list(kwargs.items())[:5]}
                }
            )
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                logger.debug(
                    f"Completed {func_name}",
                    extra_data={
                        "function": func_name,
                        "duration_ms": duration_ms,
                        "status": "success"
                    }
                )
                return result
            except Exception as e:
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                logger.error(
                    f"Failed {func_name}: {str(e)}",
                    extra_data={
                        "function": func_name,
                        "duration_ms": duration_ms,
                        "status": "error",
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator
