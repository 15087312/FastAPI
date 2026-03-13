import sys
import os
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 环境变量（必须在导入 config 之前）
try:
    from dotenv import load_dotenv
    # 优先加载 .env 文件，如果存在的话
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"Loaded .env file: {env_file}")
    else:
        print(".env file not found, using default environment variables")
except ImportError:
    print("python-dotenv not installed, skipping .env loading")

# 配置结构化日志（在导入其他模块之前）
from app.core.structured_logging import setup_logging, get_structured_logger
import os
log_format = os.getenv("LOG_FORMAT", "json")  # json 或 plain
log_file = os.getenv("LOG_FILE", None)  # 可选的日志文件路径
setup_logging(log_format=log_format, log_file=log_file)

from app.db.session import engine
from app.core.redis import async_redis
from app.routers import inventory_router, perf_router, system_monitor
from app.core.config import settings, find_available_port, is_port_available
from app.init_data import check_and_init_data

import uvicorn

# 使用结构化日志记录器
logger = get_structured_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时的初始化
    logger.info("Starting application...")
    
    # 检查端口占用情况
    actual_port = settings.PORT
    if not is_port_available(settings.HOST, settings.PORT):
        logger.warning(f"Port {settings.PORT} is occupied, trying to find available port...")
        try:
            actual_port = find_available_port(settings.HOST, settings.PORT + 1)
            logger.info(f"Found available port: {actual_port}")
        except RuntimeError as e:
            logger.error(f"Failed to find available port: {e}")
            raise
    
    logger.info(f"Server will run on {settings.HOST}:{actual_port}")
    
    # 数据库连接检查
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise
    
    # Redis 连接检查
    try:
        await async_redis.ping()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        logger.warning("Application will run without Redis caching")
    
    # 初始化测试数据
    check_and_init_data()
    
    # 加载商品 ID 到布隆过滤器
    try:
        from app.services.bloom_filter import product_bloom_filter
        from app.db.session import SessionLocal
        from app.models.product import Product
        
        db = SessionLocal()
        try:
            # 从数据库查询所有商品 ID
            product_ids = db.query(Product.id).all()
            product_ids = [pid[0] for pid in product_ids]
            
            if product_ids:
                product_bloom_filter.add_batch(product_ids)
                logger.info(f"布隆过滤器已加载 {len(product_ids)} 个商品 ID")
            else:
                logger.warning("数据库中没有商品数据，布隆过滤器未加载")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"布隆过滤器加载失败: {e}")
    
    # 预热 Redis 缓存（可选，批量加载库存数据到缓存）
    try:
        from app.services.inventory_cache import InventoryCacheService
        from app.core.redis import redis_client
        from app.models.product_stocks import ProductStock
        
        if redis_client:
            cache_service = InventoryCacheService(redis_client)
            db = SessionLocal()
            try:
                # 批量查询所有仓库的商品库存
                # 为了性能，按仓库分批
                warehouses = db.query(ProductStock.warehouse_id).distinct().all()
                warehouses = [w[0] for w in warehouses]
                
                total_cached = 0
                for warehouse_id in warehouses:
                    stocks = db.query(ProductStock).filter(
                        ProductStock.warehouse_id == warehouse_id
                    ).all()
                    
                    # 批量写入缓存
                    stock_map = {s.product_id: s.available_stock for s in stocks}
                    if stock_map:
                        cache_service.batch_set_cached_stocks(warehouse_id, stock_map)
                        total_cached += len(stock_map)
                
                if total_cached > 0:
                    logger.info(f"Redis 缓存预热完成，共缓存 {total_cached} 条库存记录")
                else:
                    logger.warning("数据库中没有库存数据，缓存未预热")
            finally:
                db.close()
        else:
            logger.warning("Redis 未连接，跳过缓存预热")
    except Exception as e:
        logger.warning(f"Redis 缓存预热失败: {e}")
    
    # 启动 Kafka 消费者（后台任务）
    try:
        import asyncio
        from app.services.kafka_consumer import start_kafka_consumer
        
        # 使用推荐的异步方式启动 Kafka 消费者
        try:
            # 尝试获取当前运行中的 loop
            loop = asyncio.get_running_loop()
            loop.create_task(start_kafka_consumer())
            logger.info("Kafka 消费者任务已启动（异步）")
        except RuntimeError:
            # 没有运行中的 loop，在新线程中运行
            import threading
            def run_kafka_consumer():
                asyncio.run(start_kafka_consumer())
            threading.Thread(target=run_kafka_consumer, daemon=True).start()
            logger.info("Kafka 消费者任务已启动（新线程）")
    except Exception as e:
        logger.warning(f"Kafka 消费者启动失败: {e}")
    
    yield
    
    # 应用关闭时的清理
    logger.info("Shutting down application...")

# 创建 FastAPI 应用
app = FastAPI(
    title="库存微服务 API",
    description=f"""专业的库存管理微服务，支持高并发环境下的库存安全管理，防止超卖问题。
                    
                    ## 🚀 核心特性
                    
                    - **防超卖保障** - PostgreSQL 行级锁确保并发安全
                    - **高性能缓存** - Redis 缓存层加速读取，支持批量操作
                    - **多层架构** - API / Celery / CLI 三种调用方式
                    - **完整审计** - 详细的操作日志和状态追踪
                    - **幂等保证** - 基于 Redis 的请求去重机制
                    - **优雅降级** - Redis 故障时自动降级到数据库模式
                    
                    ## 📚 文档说明
                    
                    - **基础路径**: `/api/v1`
                    - **健康检查**: `GET /health`
                    - **API 文档**: `GET /docs` (Swagger UI)
                    - **ReDoc 文档**: `GET /redoc` (ReDoc UI)
                    
                    ## 🔧 错误码说明
                    
                    - `200`: 请求成功
                    - `400`: 请求参数错误
                    - `404`: 资源未找到
                    - `422`: 请求验证失败
                    - `429`: 请求过于频繁
                    - `500`: 服务器内部错误
                    
                    ## 🌐 当前运行端口：{settings.PORT}
                    如果端口被占用，系统将自动尝试使用其他可用端口。""",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={
        "name": "库存微服务团队",
        "email": "inventory@example.com",
        "url": "https://github.com/your-org/inventory-service"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    servers=[
        {
            "url": f"http://localhost:{settings.PORT}",
            "description": "开发环境"
        },
        {
            "url": "https://api.example.com",
            "description": "生产环境"
        }
    ],
    terms_of_service="https://example.com/terms/",
    openapi_tags=[
        {
            "name": "库存管理",
            "description": "库存预占、确认、释放等核心操作"
        },
        {
            "name": "库存查询",
            "description": "库存数量查询接口"
        },
        {
            "name": "任务管理",
            "description": "清理任务和异步任务管理"
        }
    ]
)

# 添加 CORS 中间件
# 生产环境配置：允许从环境变量 ALLOWED_ORIGINS 读取域名列表，逗号分隔
# 示例：ALLOWED_ORIGINS="https://example.com,https://app.example.com"
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()] if allowed_origins_str else []

# 如果未配置且非调试模式，使用安全的默认值
if not allowed_origins and not settings.DEBUG:
    allowed_origins = ["https://example.com"]  # 生产环境默认域名
else:
    allowed_origins = allowed_origins or ["*"]  # 调试模式允许所有

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# 添加安全防护中间件（限流）
try:
    from app.core.security import SecurityMiddleware
    from app.services.bloom_filter import product_bloom_filter
    
    if settings.RATE_LIMIT_ENABLED and redis_client:
        app.add_middleware(
            SecurityMiddleware,
            redis_client=redis_client
        )
        logger.info("安全防护中间件已启用")
    else:
        logger.info("安全防护中间件未启用（Redis 不可用或已禁用）")
except ImportError as e:
    logger.warning(f"安全防护中间件导入失败: {e}")
except Exception as e:
    logger.warning(f"安全防护中间件初始化失败: {e}")

# 注册路由
app.include_router(inventory_router.router, prefix="/api/v1")
app.include_router(perf_router.router, prefix="/api/v1")
app.include_router(system_monitor.router, prefix="/api/v1")

# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "请求参数验证失败",
            "details": exc.errors()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    import traceback
    error_detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"Unexpected error: {exc}\n{error_detail}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"服务器内部错误: {str(exc)}",
            "detail": error_detail
        }
    )

# 健康检查端点
from pydantic import BaseModel
from typing import Dict, Any, Optional

class HealthStatus(BaseModel):
    """健康检查响应模型"""
    status: str
    service: str
    version: str
    timestamp: str
    checks: Dict[str, Any]

@app.get(
    "/health",
    response_model=HealthStatus,
    summary="完整健康检查",
    description="检查服务是否正常运行，包括数据库、Redis、连接池等所有组件",
    responses={
        200: {
            "description": "服务健康",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "service": "inventory-microservice",
                        "version": "1.0.0",
                        "timestamp": "2024-01-01T00:00:00",
                        "checks": {
                            "database": "ok",
                            "redis": "ok",
                            "db_pool": {"size": 10, "checked_out": 2, "overflow": 0}
                        }
                    }
                }
            }
        },
        503: {
            "description": "服务不健康",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "service": "inventory-microservice",
                        "version": "1.0.0",
                        "timestamp": "2024-01-01T00:00:00",
                        "checks": {
                            "database": "error: connection refused",
                            "redis": "ok",
                            "db_pool": "error: pool exhausted"
                        }
                    }
                }
            }
        }
    }
)
async def health_check():
    """完整健康检查接口
    
    检查所有关键组件的状态：
    - 数据库连接
    - Redis 连接
    - 数据库连接池状态
    - 系统资源（如果可用）
    """
    from datetime import datetime
    import psutil
    
    checks = {}
    is_healthy = True
    
    # 1. 数据库连接检查
    try:
        from app.db.session import engine
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        is_healthy = False
    
    # 2. Redis 连接检查
    try:
        from app.core.redis import async_redis
        await async_redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        is_healthy = False
    
    # 3. 数据库连接池检查
    try:
        from app.db.session import engine
        pool = engine.pool
        checks["db_pool"] = {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow()
        }
        # 检查连接池是否耗尽
        if pool.checkedout() >= pool.size() and pool.overflow() <= 0:
            checks["db_pool_status"] = "warning: pool exhausted"
        else:
            checks["db_pool_status"] = "ok"
    except Exception as e:
        checks["db_pool"] = f"error: {str(e)}"
        is_healthy = False
    
    # 4. 系统资源检查（如果安装了 psutil）
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        checks["system"] = {
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_available_mb": round(memory.available / 1024 / 1024, 2)
        }
        # CPU 或内存使用率超过 95% 视为不健康
        if cpu_percent > 95 or memory.percent > 95:
            checks["system_status"] = "warning: high resource usage"
        else:
            checks["system_status"] = "ok"
    except Exception as e:
        checks["system"] = f"warning: {str(e)} (psutil may not be installed)"
    
    # 5. Kafka 消费者检查（可选）
    try:
        from app.services.kafka_consumer import kafka_consumer
        # 简单检查，实际应该检查消费者状态
        checks["kafka_consumer"] = "running" if kafka_consumer else "not started"
    except Exception as e:
        checks["kafka_consumer"] = f"warning: {str(e)}"
    
    status = "healthy" if is_healthy else "unhealthy"
    
    return HealthStatus(
        status=status,
        service="inventory-microservice",
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
        checks=checks
    )

@app.get(
    "/",
    response_model=dict,
    summary="API 根路径",
    description="API 服务的根路径信息",
    responses={
        200: {
            "description": "成功返回",
            "content": {
                "application/json": {
                    "example": {
                        "message": "欢迎使用库存微服务",
                        "docs": "/docs",
                        "health": "/health"
                    }
                }
            }
        }
    }
)
async def read_root():
    """API 根路径
    
    提供 API 服务的基本信息和入口链接。
    """
    return {
        "message": "欢迎使用库存微服务", 
        "docs": "/docs",
        "health": "/health",
        "port": settings.PORT,
        "host": settings.HOST,
        "api_base_url": f"http://localhost:{settings.PORT}/api/v1"
    }




if __name__ == "__main__":
    # 检查端口是否可用，如果不可用则查找可用端口
    host = settings.HOST
    port = settings.PORT
    
    if not is_port_available(host, port):
        logger.warning(f"Port {port} is occupied, trying to find available port...")
        try:
            port = find_available_port(host, port + 1)
            logger.info(f"Found available port: {port}")
        except RuntimeError as e:
            logger.error(f"Failed to find available port: {e}")
            raise
    
    # 生产环境配置：使用多进程 uvicorn
    # workers 数量建议：CPU 核心数 * 2 + 1
    # 开发环境：workers=1 或 2
    # 生产环境：根据 CPU 核心数调整，一般 4-8 个
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    workers = min(cpu_count * 2 + 1, 8)  # 最多 8 个 worker
    
    logger.info(f"Starting server with {workers} workers (CPU cores: {cpu_count})")
    
    # 注意：reload=True 时 workers 参数不生效，开发环境建议使用单进程
    # 生产环境设置 DEBUG=False 以启用多进程
    if settings.DEBUG and workers > 1:
        logger.warning("DEBUG mode enabled: reload will override workers, using single process")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=1 if settings.DEBUG else workers,  # DEBUG 模式强制使用 1 个 worker
        reload=settings.DEBUG,
        access_log=True,
        log_level="info"
    )