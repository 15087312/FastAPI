from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine
from app.core.redis import async_redis
from app.routers import inventory_router

import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时的初始化
    logger.info("Starting application...")
    
    # 数据库连接检查
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error("❌ Database connection failed: %s", e)
        raise
    
    # Redis 连接检查
    try:
        await async_redis.ping()
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.warning(f"⚠️  Redis connection failed: {e}")
        logger.warning("⚠️  Application will run without Redis caching")

    yield
    
    # 应用关闭时的清理
    logger.info("Shutting down application...")

# 创建 FastAPI 应用
app = FastAPI(
    title="库存微服务 API",
    description="""专业的库存管理微服务，支持高并发环境下的库存安全管理，防止超卖问题。

## 🚀 核心特性

- **防超卖保障** - PostgreSQL 行级锁 + Redis 分布式锁双重保护
- **高性能缓存** - Redis 缓存层加速读取，支持批量操作
- **多层架构** - API / Celery / CLI 三种调用方式
- **完整审计** - 详细的操作日志和状态追踪
- **幂等保证** - 基于 Redis 的请求去重机制
- **优雅降级** - Redis 故障时自动降级到数据库模式

## 📚 文档说明

- **基础路径**: `/api/v1`
- **健康检查**: `GET /health`
- **API文档**: `GET /docs` (Swagger UI)
- **ReDoc文档**: `GET /redoc` (ReDoc UI)

## 🔧 错误码说明

- `200`: 请求成功
- `400`: 请求参数错误
- `404`: 资源未找到
- `422`: 请求验证失败
- `429`: 请求过于频繁
- `500`: 服务器内部错误
""",
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
            "url": "http://localhost:8000/api/v1",
            "description": "开发环境"
        },
        {
            "url": "https://api.example.com/api/v1",
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(inventory_router.router, prefix="/api/v1")

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
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "服务器内部错误"
        }
    )

# 健康检查端点
@app.get(
    "/health",
    response_model=dict,
    summary="健康检查",
    description="检查服务是否正常运行",
    responses={
        200: {
            "description": "服务健康",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "service": "inventory-microservice",
                        "version": "1.0.0"
                    }
                }
            }
        }
    }
)
async def health_check():
    """健康检查接口
    
    返回服务的基本健康状态信息。
    """
    return {
        "status": "healthy",
        "service": "inventory-microservice",
        "version": "1.0.0"
    }

@app.get(
    "/",
    response_model=dict,
    summary="API 根路径",
    description="API服务的根路径信息",
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
    
    提供API服务的基本信息和入口链接。
    """
    return {
        "message": "欢迎使用库存微服务", 
        "docs": "/docs",
        "health": "/health"
    }




if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )