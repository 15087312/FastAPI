"""
库存服务高性能 Tornado 版本
专注于极致的查询性能，适用于高并发场景

启动命令：
    python tornado_server.py
    
测试命令：
    wrk -t8 -c100 -d30s http://127.0.0.1:8001/api/v1/inventory/stock/980?warehouse_id=WH001
"""

import tornado.web
import tornado.ioloop
import tornado.gen
import redis
import json
import logging
from typing import Optional, Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== Redis 连接池（单例）====================
class RedisPool:
    """Redis 连接池单例"""
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_pool(cls, host='localhost', port=6379, db=0):
        if cls._pool is None:
            # 尝试连接 Docker 中的 Redis
            import os
            redis_host = os.getenv('REDIS_HOST', host)
            redis_port = int(os.getenv('REDIS_PORT', port))
            redis_db = int(os.getenv('REDIS_DB', db))
            
            logger.info(f"Connecting to Redis: {redis_host}:{redis_port}")
            cls._pool = redis.ConnectionPool(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                max_connections=100  # 最大连接数
            )
        return cls._pool
    
    @classmethod
    def get_client(cls, host='localhost', port=6379, db=0):
        return redis.Redis(connection_pool=cls.get_pool(host, port, db))


# ==================== 缓存服务（复用原有逻辑）====================
class InventoryCacheService:
    """库存缓存服务 - 纯 Redis 操作"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    def _get_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成库存缓存键"""
        return f"stock:available:{warehouse_id}:{product_id}"
    
    def _get_full_cache_key(self, warehouse_id: str, product_id: int) -> str:
        """生成完整库存信息缓存键"""
        return f"stock:full:{warehouse_id}:{product_id}"
    
    def get_cached_stock(self, warehouse_id: str, product_id: int) -> int:
        """获取缓存的可用库存"""
        cache_key = self._get_cache_key(warehouse_id, product_id)
        cached = self.redis.get(cache_key)
        
        if cached is not None:
            logger.debug(f"Cache hit: {cache_key} = {cached}")
            return int(cached)
        
        logger.debug(f"Cache miss: {cache_key}")
        return 0
    
    def get_cached_full_info_optimized(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息（使用 MGET 批量读取优化）"""
        # 构建所有需要的 key，一次性 MGET 读取
        keys = [
            f"stock:full:{warehouse_id}:{product_id}",      # 完整信息
            f"stock:available:{warehouse_id}:{product_id}",  # 可用库存
            f"stock:reserved:{warehouse_id}:{product_id}",   # 预占库存
            f"stock:frozen:{warehouse_id}:{product_id}",     # 冻结库存
            f"stock:safety:{warehouse_id}:{product_id}"      # 安全库存
        ]
        
        # 单次网络往返，批量读取所有字段
        values = self.redis.mget(keys)
        
        full_info_raw, available_raw, reserved_raw, frozen_raw, safety_raw = values
        
        # 优先使用完整信息缓存
        if full_info_raw:
            try:
                info = json.loads(full_info_raw)
                logger.debug(f"MGET 命中完整信息：{warehouse_id}:{product_id}")
                return info
            except json.JSONDecodeError:
                pass
        
        # 如果没有完整信息，尝试从各个字段构建
        available = int(available_raw) if available_raw else 0
        reserved = int(reserved_raw) if reserved_raw else 0
        frozen = int(frozen_raw) if frozen_raw else 0
        safety = int(safety_raw) if safety_raw else 0
        
        # 如果所有字段都是 0，说明数据不存在
        if available == 0 and reserved == 0 and frozen == 0 and safety == 0:
            logger.debug(f"MGET 未命中：{warehouse_id}:{product_id}")
            return None
        
        # 构建完整信息
        info = {
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "available_stock": available,
            "reserved_stock": reserved,
            "frozen_stock": frozen,
            "safety_stock": safety,
            "total_stock": available + reserved + frozen
        }
        
        logger.debug(f"MGET 构建完整信息：{warehouse_id}:{product_id}")
        return info


# ==================== 查询服务（复用原有逻辑）====================
class InventoryQueryService:
    """库存查询服务 - 纯 Redis 查询"""
    
    def __init__(self, cache_service: InventoryCacheService):
        self.cache_service = cache_service
    
    def get_product_stock(self, warehouse_id: str, product_id: int) -> int:
        """查询商品可用库存"""
        stock = self.cache_service.get_cached_stock(warehouse_id, product_id)
        logger.debug(f"查询库存：warehouse={warehouse_id}, product={product_id}, stock={stock}")
        return stock
    
    def get_full_stock_info(self, warehouse_id: str, product_id: int) -> Optional[Dict[str, Any]]:
        """获取完整库存信息"""
        info = self.cache_service.get_cached_full_info_optimized(warehouse_id, product_id)
        return info


# ==================== Tornado Request Handler ====================
class StockQueryHandler(tornado.web.RequestHandler):
    """库存查询接口 - 简单版本（仅返回可用库存）"""
    
    def initialize(self, query_service: InventoryQueryService):
        self.query_service = query_service
    
    @tornado.gen.coroutine
    def get(self, product_id: str):
        """
        查询商品库存
        GET /api/v1/inventory/stock/{product_id}?warehouse_id=WH001
        """
        try:
            # 1. 获取参数
            warehouse_id = self.get_argument("warehouse_id", "WH001")
            
            # 2. 查询库存（同步调用，但 Redis 操作本身很快）
            stock = self.query_service.get_product_stock(warehouse_id, int(product_id))
            
            # 3. 返回结果
            response = {
                "success": True,
                "warehouse_id": warehouse_id,
                "product_id": int(product_id),
                "available_stock": stock,
                "reserved_stock": 0,
                "frozen_stock": 0,
                "safety_stock": 0,
                "total_stock": stock
            }
            
            self.set_header("Content-Type", "application/json")
            self.write(response)
            
        except Exception as e:
            logger.error(f"查询失败：{e}")
            self.set_status(500)
            self.write({"success": False, "error": str(e)})


class FullStockQueryHandler(tornado.web.RequestHandler):
    """完整库存查询接口 - 返回所有字段"""
    
    def initialize(self, query_service: InventoryQueryService):
        self.query_service = query_service
    
    @tornado.gen.coroutine
    def get(self, product_id: str):
        """
        查询完整库存信息
        GET /api/v1/inventory/stock/{product_id}/full?warehouse_id=WH001
        """
        try:
            # 1. 获取参数
            warehouse_id = self.get_argument("warehouse_id", "WH001")
            
            # 2. 查询完整库存信息
            info = self.query_service.get_full_stock_info(warehouse_id, int(product_id))
            
            # 3. 返回结果
            if info:
                response = {
                    "success": True,
                    **info
                }
            else:
                response = {
                    "success": True,
                    "warehouse_id": warehouse_id,
                    "product_id": int(product_id),
                    "available_stock": 0,
                    "reserved_stock": 0,
                    "frozen_stock": 0,
                    "safety_stock": 0,
                    "total_stock": 0
                }
            
            self.set_header("Content-Type", "application/json")
            self.write(response)
            
        except Exception as e:
            logger.error(f"查询失败：{e}")
            self.set_status(500)
            self.write({"success": False, "error": str(e)})


class HealthCheckHandler(tornado.web.RequestHandler):
    """健康检查接口"""
    
    @tornado.gen.coroutine
    def get(self):
        """健康检查"""
        try:
            # 检查 Redis 连接
            redis_client = RedisPool.get_client()
            redis_client.ping()
            
            response = {
                "status": "healthy",
                "service": "inventory-tornado",
                "version": "1.0.0",
                "checks": {
                    "redis": "ok"
                }
            }
            
            self.set_header("Content-Type", "application/json")
            self.write(response)
            
        except Exception as e:
            self.set_status(503)
            self.write({
                "status": "unhealthy",
                "error": str(e)
            })


# ==================== Tornado 应用工厂 ====================
def make_app():
    """创建 Tornado 应用"""
    # 从环境变量读取 Redis 配置（优先）或默认值
    import os
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', 6379))
    redis_db = int(os.getenv('REDIS_DB', 0))
    
    # 初始化 Redis 和查询服务
    redis_client = RedisPool.get_client(redis_host, redis_port, redis_db)
    cache_service = InventoryCacheService(redis_client)
    query_service = InventoryQueryService(cache_service)
    
    # 路由配置
    handlers = [
        # 健康检查
        (r"/health", HealthCheckHandler),
        
        # 库存查询接口（两种风格）
        (r"/api/v1/inventory/stock/(\d+)", StockQueryHandler, {"query_service": query_service}),
        (r"/api/v1/inventory/stock/(\d+)/full", FullStockQueryHandler, {"query_service": query_service}),
        
        # API 根路径
        (r"/", tornado.web.RedirectHandler, {"url": "/docs"}),
    ]
    
    # 应用配置
    settings = {
        "debug": False,  # 生产环境关闭调试
        "autoreload": False,  # 关闭自动重载
        "compiled_template_cache": 1000,
        "static_hash_cache": 1000,
        
        # 抗并发配置（关键！）
        "max_buffer_size": 1024 * 1024 * 100,  # 限制请求体大小 100MB
        "idle_connection_timeout": 3,  # 空闲连接快速回收（秒）
        "xheaders": True,  # 识别 CDN 转发的真实 IP
        "compress_response": True,  # 启用响应压缩
    }
    
    return tornado.web.Application(handlers, **settings)


# ==================== 启动入口 ====================
def main():
    """主函数，用于启动 Tornado 服务"""
    import argparse
    
    parser = argparse.ArgumentParser(description="库存服务 Tornado 高性能版")
    parser.add_argument("--port", type=int, default=8001, help="监听端口（默认 8001，避免与 FastAPI 冲突）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    args = parser.parse_args()
    
    # 创建应用
    app = make_app()
    
    # 创建 HTTP 服务器（支持更多配置）
    from tornado.httpserver import HTTPServer
    http_server = HTTPServer(
        app,
        max_buffer_size=1024 * 1024 * 100,  # 限制请求体大小 100MB
        idle_connection_timeout=3,  # 空闲连接快速回收（秒）
        xheaders=True,  # 识别 CDN 转发的真实 IP
        decompress_request=True,  # 启用请求解压缩
        max_header_size=65536  # 最大请求头大小
    )
    
    # 绑定端口
    http_server.listen(args.port, address=args.host)
    
    logger.info(f"🚀 Tornado 服务器已启动 on http://{args.host}:{args.port}")
    logger.info(f"健康检查：http://{args.host}:{args.port}/health")
    logger.info(f"库存查询：http://{args.host}:{args.port}/api/v1/inventory/stock/980?warehouse_id=WH001")
    logger.info(f"按 Ctrl+C 停止服务")
    
    # 启动事件循环
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
