"""API 安全防护中间件 - 限流和参数校验"""

import time
import logging
from typing import Callable, Optional
from fastapi import Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """基于 Redis 的滑动窗口限流器
    
    支持：
    - 按 IP 限流
    - 按 API Key 限流
    - 滑动窗口算法
    """
    
    def __init__(
        self,
        redis_client: Redis = None,
        requests_per_second: int = 50,
        burst_size: int = 100
    ):
        self.redis = redis_client
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
    
    def _get_client_ip(self, request: Request) -> str:
        """获取客户端 IP"""
        # 优先获取 X-Forwarded-For（反向代理场景）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # 获取真实 IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # 获取客户端 IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_rate_limit_key(self, request: Request) -> str:
        """生成限流 key"""
        client_ip = self._get_client_ip(request)
        path = request.url.path
        return f"ratelimit:{client_ip}:{path}"
    
    def is_allowed(self, request: Request) -> tuple[bool, dict]:
        """检查请求是否允许
        
        Returns:
            (is_allowed, info)
            - is_allowed: 是否允许请求
            - info: 限流信息 {remaining, reset_time}
        """
        if not self.redis:
            # Redis 不可用，放行请求
            return True, {"remaining": self.burst_size, "reset_time": int(time.time()) + 1}
        
        key = self._get_rate_limit_key(request)
        current_time = int(time.time())
        window_key = f"{key}:{current_time}"
        
        try:
            pipe = self.redis.pipeline()
            
            # 使用滑动窗口：记录每个请求的时间戳
            # 清理过期的窗口
            pipe.zremrangebyscore(key, 0, current_time - 1)
            
            # 添加当前请求
            pipe.zadd(key, {str(current_time): current_time})
            
            # 设置过期时间（1秒）
            pipe.expire(key, 1)
            
            # 获取当前窗口内的请求数
            pipe.zcard(key)
            
            results = pipe.execute()
            request_count = results[-1]
            
            # 计算剩余请求数
            remaining = max(0, self.requests_per_second - request_count)
            reset_time = current_time + 1
            
            if request_count > self.requests_per_second:
                logger.warning(
                    f"限流触发: ip={self._get_client_ip(request)}, path={request.url.path}, "
                    f"count={request_count}, limit={self.requests_per_second}"
                )
                return False, {
                    "remaining": 0,
                    "reset_time": reset_time,
                    "limit": self.requests_per_second,
                    "retry_after": 1
                }
            
            return True, {
                "remaining": remaining,
                "reset_time": reset_time,
                "limit": self.requests_per_second
            }
            
        except Exception as e:
            logger.error(f"限流检查失败: {e}")
            # 限流检查失败时，放行请求
            return True, {"remaining": self.burst_size, "reset_time": int(time.time()) + 1}


class SecurityMiddleware(BaseHTTPMiddleware):
    """安全防护中间件
    
    功能：
    1. 请求限流
    2. 参数校验
    """
    
    def __init__(self, app, redis_client: Redis = None):
        super().__init__(app)
        self.redis = redis_client
        
        # 初始化限流器
        self.rate_limiter = RateLimiter(
            redis_client=redis_client,
            requests_per_second=50,  # 每秒 50 请求
            burst_size=100          # 突发容量
        )
        
        # 需要限流的路径
        self.ratelimited_paths = [
            "/api/inventory/reserve",
            "/api/inventory/confirm",
            "/api/inventory/release",
            "/api/inventory/increase",
            "/api/inventory/decrease",
            "/api/inventory/adjust",
            "/api/inventory/batch/reserve",
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要限流
        path = request.url.path
        needs_ratelimit = any(path.startswith(p) for p in self.ratelimited_paths)
        
        if needs_ratelimit:
            is_allowed, info = self.rate_limiter.is_allowed(request)
            
            if not is_allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "message": "请求过于频繁，请稍后再试",
                        "error": "rate_limit_exceeded",
                        "retry_after": info.get("retry_after", 1),
                        "limit": info.get("limit", 50)
                    },
                    headers={
                        "X-RateLimit-Limit": str(info.get("limit", 50)),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(info.get("reset_time", 0)),
                        "Retry-After": str(info.get("retry_after", 1))
                    }
                )
        
        # 继续处理请求
        response = await call_next(request)
        
        # 添加限流响应头
        if needs_ratelimit and self.redis:
            _, info = self.rate_limiter.is_allowed(request)
            response.headers["X-RateLimit-Limit"] = str(info.get("limit", 50))
            response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
            response.headers["X-RateLimit-Reset"] = str(info.get("reset_time", 0))
        
        return response


class ParameterValidator:
    """参数校验器
    
    校验：
    - product_id 是否存在
    - product_id 合法性：1 ~ 10,000,000
    - quantity > 0
    """
    
    # 商品ID合法范围
    MIN_PRODUCT_ID = 1
    MAX_PRODUCT_ID = 10_000_000
    
    def __init__(self, redis_client: Redis = None, bloom_filter=None):
        self.redis = redis_client
        self.bloom_filter = bloom_filter
    
    def validate_product_id_range(self, product_id: int) -> tuple[bool, str]:
        """校验 product_id 是否在合法范围内
        
        商品ID规则：1 ~ 10,000,000
        
        Returns:
            (is_valid, error_message)
        """
        if product_id is None:
            return False, "product_id 不能为空"
        
        if not isinstance(product_id, int):
            try:
                product_id = int(product_id)
            except (ValueError, TypeError):
                return False, "product_id 必须是整数"
        
        if product_id < self.MIN_PRODUCT_ID or product_id > self.MAX_PRODUCT_ID:
            return False, f"product_id 必须在 {self.MIN_PRODUCT_ID} ~ {self.MAX_PRODUCT_ID} 范围内"
        
        return True, ""
    
    def validate_product_id(self, warehouse_id: str, product_id: int) -> bool:
        """校验 product_id 是否存在
        
        使用 BloomFilter 快速判断，如果不存在则直接返回 False
        精确验证需要查询数据库
        """
        # 先用 BloomFilter 快速过滤（如果可用）
        if self.bloom_filter and hasattr(self.bloom_filter, 'contains'):
            if not self.bloom_filter.contains(product_id):
                logger.debug(f"product_id {product_id} 不在 BloomFilter 中")
                return False
        
        return True
    
    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """校验 quantity 是否有效
        
        Returns:
            (is_valid, error_message)
        """
        if quantity is None:
            return False, "quantity 不能为空"
        
        if quantity <= 0:
            return False, "quantity 必须大于 0"
        
        if quantity > 10000:
            return False, "quantity 不能超过 10000"
        
        return True, ""
    
    def validate_warehouse_id(self, warehouse_id: str) -> tuple[bool, str]:
        """校验 warehouse_id 是否有效"""
        if not warehouse_id:
            return False, "warehouse_id 不能为空"
        
        if len(warehouse_id) > 32:
            return False, "warehouse_id 长度不能超过 32"
        
        return True, ""
    
    def validate_order_id(self, order_id: str) -> tuple[bool, str]:
        """校验 order_id 是否有效"""
        if not order_id:
            return False, "order_id 不能为空"
        
        if len(order_id) > 64:
            return False, "order_id 长度不能超过 64"
        
        # 检查订单ID格式（防止注入）
        if not order_id.replace("_", "").replace("-", "").isalnum():
            return False, "order_id 格式不正确"
        
        return True, ""


def create_security_middleware(redis_client: Redis = None):
    """创建安全中间件工厂函数"""
    def middleware(app):
        return SecurityMiddleware(app, redis_client=redis_client)
    return middleware
