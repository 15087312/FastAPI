"""服务层切面模块 - AOP 统一处理

提供统一的：
- 性能监控
- 异常处理
- 日志记录
- 缓存失效
"""

import logging
import time
from functools import wraps
from typing import Optional, Callable, Any, Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# 性能监控阈值配置（毫秒）
PERFORMANCE_THRESHOLD_WARNING = 50  # 警告阈值
PERFORMANCE_THRESHOLD_CRITICAL = 100  # 严重阈值


def performance_monitor(func: Callable) -> Callable:
    """性能监控装饰器
    
    监控函数执行时间，记录性能指标
    - 超过临界值：WARNING 级别日志
    - 超过警告值：INFO 级别日志  
    - 正常范围：DEBUG 级别日志
    - 异常：ERROR 级别日志
    
    Args:
        func: 被装饰的函数
        
    Returns:
        包装后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # 记录性能指标
            if elapsed_ms > PERFORMANCE_THRESHOLD_CRITICAL:
                logger.warning(
                    f"[PERF-CRITICAL] {func.__name__} took {elapsed_ms:.2f}ms",
                    extra={
                        'performance_critical': True,
                        'function': func.__name__,
                        'duration_ms': elapsed_ms
                    }
                )
            elif elapsed_ms > PERFORMANCE_THRESHOLD_WARNING:
                logger.info(
                    f"[PERF-WARNING] {func.__name__} took {elapsed_ms:.2f}ms",
                    extra={
                        'performance_warning': True,
                        'function': func.__name__,
                        'duration_ms': elapsed_ms
                    }
                )
            else:
                logger.debug(f"[PERF-OK] {func.__name__} took {elapsed_ms:.2f}ms")
            
            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[PERF-ERROR] {func.__name__} failed after {elapsed_ms:.2f}ms: {str(e)}",
                extra={
                    'performance_error': True,
                    'function': func.__name__,
                    'duration_ms': elapsed_ms,
                    'error': str(e)
                }
            )
            raise
    return wrapper


def log_operation(operation_name: str, success_level: int = logging.INFO):
    """操作日志记录装饰器
    
    记录操作的开始和结束，支持自定义日志级别
    
    Args:
        operation_name: 操作名称
        success_level: 成功时的日志级别，默认 INFO
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"开始执行：{operation_name}")
            try:
                result = func(*args, **kwargs)
                logger.log(success_level, f"执行成功：{operation_name}")
                return result
            except Exception as e:
                logger.error(f"执行失败：{operation_name}, error={str(e)}")
                raise
        return wrapper
    return decorator


def handle_exception(default_return: Any = None, reraise: bool = True):
    """异常处理装饰器
    
    统一处理函数执行过程中的异常
    
    Args:
        default_return: 异常时的默认返回值
        reraise: 是否重新抛出异常，默认 True
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{func.__name__} 执行异常：{str(e)}")
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


class CacheInvalidationAspect:
    """缓存失效切面
    
    统一管理缓存失效逻辑，避免每个 service 重复实现
    """
    
    def __init__(self, cache_service):
        """初始化缓存失效切面
        
        Args:
            cache_service: 缓存服务实例
        """
        self.cache_service = cache_service
    
    def invalidate_single(self, warehouse_id: str, product_id: int):
        """失效单个商品的库存缓存
        
        Args:
            warehouse_id: 仓库 ID
            product_id: 商品 ID
        """
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)
    
    def invalidate_batch(self, items: List[Dict[str, Any]]):
        """批量失效缓存
        
        Args:
            items: 包含 warehouse_id 和 product_id 的字典列表
        """
        if not self.cache_service or not items:
            return
        
        for item in items:
            warehouse_id = item.get("warehouse_id")
            product_id = item.get("product_id")
            if warehouse_id and product_id:
                self.cache_service.invalidate_cache(warehouse_id, product_id)
    
    def invalidate_by_order(self, reservations: List[Any]):
        """根据预占记录批量失效缓存
        
        Args:
            reservations: 预占记录列表，需要有 warehouse_id 和 product_id 属性
        """
        if not self.cache_service or not reservations:
            return
        
        for r in reservations:
            warehouse_id = getattr(r, 'warehouse_id', None)
            product_id = getattr(r, 'product_id', None)
            if warehouse_id and product_id:
                self.cache_service.invalidate_cache(warehouse_id, product_id)


class TransactionAspect:
    """事务管理切面
    
    统一管理数据库事务的提交和回滚
    """
    
    def __init__(self, db_session):
        """初始化事务切面
        
        Args:
            db_session: SQLAlchemy 数据库会话
        """
        self.db = db_session
    
    def execute_with_transaction(self, operation: Callable, on_success: Optional[Callable] = None):
        """执行带事务的操作
        
        Args:
            operation: 要执行的操作函数
            on_success: 成功后执行的回调函数（在 commit 之前）
            
        Returns:
            operation 的返回值
            
        Raises:
            执行失败时抛出异常
        """
        try:
            result = operation()
            if on_success:
                on_success()
            self.db.commit()
            return result
        except Exception as e:
            logger.error(f"事务执行失败：{str(e)}")
            self.db.rollback()
            raise
    
    def commit_or_rollback(self, should_commit: bool = True):
        """提交或回滚事务
        
        Args:
            should_commit: 是否提交，False 则回滚
        """
        try:
            if should_commit:
                self.db.commit()
            else:
                self.db.rollback()
        except Exception as e:
            logger.error(f"事务提交/回滚失败：{str(e)}")
            self.db.rollback()
            raise


class LoggingAspect:
    """日志记录切面
    
    统一的日志记录模式
    """
    
    @staticmethod
    def log_operation_start(operation: str, details: Optional[Dict] = None):
        """记录操作开始
        
        Args:
            operation: 操作名称
            details: 附加详情信息
        """
        if details:
            logger.info(f"开始执行：{operation}", extra=details)
        else:
            logger.info(f"开始执行：{operation}")
    
    @staticmethod
    def log_operation_success(operation: str, duration_ms: Optional[float] = None, extra_data: Optional[Dict] = None):
        """记录操作成功
        
        Args:
            operation: 操作名称
            duration_ms: 执行耗时（毫秒）
            extra_data: 附加数据
        """
        data = extra_data or {}
        if duration_ms is not None:
            data['duration_ms'] = duration_ms
        
        logger.info(f"执行成功：{operation}", extra=data)
    
    @staticmethod
    def log_operation_failure(operation: str, error: Exception, duration_ms: Optional[float] = None):
        """记录操作失败
        
        Args:
            operation: 操作名称
            error: 异常对象
            duration_ms: 执行耗时（毫秒）
        """
        data = {'error': str(error)}
        if duration_ms is not None:
            data['duration_ms'] = duration_ms
        
        logger.error(f"执行失败：{operation}", extra=data)


# 导出
__all__ = [
    "performance_monitor",
    "log_operation",
    "handle_exception",
    "CacheInvalidationAspect",
    "TransactionAspect",
    "LoggingAspect",
    "PERFORMANCE_THRESHOLD_WARNING",
    "PERFORMANCE_THRESHOLD_CRITICAL",
]
