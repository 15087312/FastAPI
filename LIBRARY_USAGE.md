# 库存微服务库 - 使用指南

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install inventory-service
```

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/your-org/inventory-service.git
cd inventory-service

# 安装
pip install .

# 或者开发模式安装
pip install -e .
```

### 带额外依赖安装

```bash
# 开发环境
pip install inventory-service[dev]

# Docker 支持
pip install inventory-service[docker]

# 完整安装
pip install "inventory-service[dev,docker]"
```

---

## 快速开始

### 1. 作为 FastAPI 应用运行

#### 方式一：使用命令行工具

```bash
# 启动服务
inventory-server

# 指定主机和端口
inventory-server --host 0.0.0.0 --port 8000

# 生产环境（多进程）
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
```

#### 方式二：在代码中导入

```python
from fastapi import FastAPI
from app.routers import inventory_router, inventory_query

# 创建 FastAPI 应用
app = FastAPI(
    title="库存服务",
    description="库存管理 API",
    version="1.0.0"
)

# 注册路由
app.include_router(inventory_router.router, prefix="/api/v1")
app.include_router(inventory_query.router, prefix="/api/v1")

# 运行
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### 2. 初始化数据库

```bash
# 运行 Alembic 迁移
alembic upgrade head

# 或者使用初始化工具
inventory-init
```

---

### 3. 配置环境变量

创建 `.env` 文件：

```bash
# 数据库配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=inventory_db

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Kafka 配置（可选）
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_ENABLED=true
KAFKA_TOPIC=inventory-changes

# 应用配置
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

---

## 核心功能使用

### 库存预占

```python
import httpx

async def reserve_inventory():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/inventory/reserve",
            json={
                "warehouse_id": "WH001",
                "product_id": 980,
                "quantity": 5,
                "order_id": "ORDER-2024-001"
            }
        )
        return response.json()
```

### 库存查询

```python
async def query_inventory():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/inventory/stock/WH001/980"
        )
        return response.json()
```

### 批量操作

```python
async def batch_reserve():
    """批量预占库存"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/inventory/batch/reserve",
            json=[
                {
                    "warehouse_id": "WH001",
                    "product_id": 980,
                    "quantity": 5,
                    "order_id": "ORDER-001"
                },
                {
                    "warehouse_id": "WH001",
                    "product_id": 981,
                    "quantity": 3,
                    "order_id": "ORDER-002"
                }
            ]
        )
        return response.json()
```

---

## 高级用法

### 1. 自定义中间件

```python
from fastapi import FastAPI, Request
from app.main import app

@app.middleware("http")
async def custom_middleware(request: Request, call_next):
    # 添加自定义逻辑
    response = await call_next(request)
    return response
```

### 2. 扩展服务层

```python
from app.services.inventory_service import InventoryService
from app.db.session import SessionLocal

class CustomInventoryService(InventoryService):
    async def custom_operation(self, product_id: int):
        # 自定义业务逻辑
        pass

# 使用
service = CustomInventoryService(SessionLocal())
```

### 3. 集成 Celery 任务

```python
from celery_app import celery_app
from tasks.inventory_tasks import cleanup_expired_reservations

# 调用异步任务
result = cleanup_expired_reservations.delay()
```

---

## Docker 部署

### 使用 Docker Compose

```bash
# 启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down
```

### 单独构建镜像

```bash
# 构建应用镜像
docker build -t inventory-service:latest .

# 运行容器
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name inventory \
  inventory-service:latest
```

---

## API 文档

启动服务后访问：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_inventory_service.py

# 带覆盖率报告
pytest --cov=app --cov-report=html

# 性能测试
python stress_test.py
```

---

## 故障排查

### 常见问题

**1. Redis 连接失败**
```bash
# 检查 Redis 是否运行
redis-cli ping

# 应该返回 PONG
```

**2. 数据库连接失败**
```bash
# 检查 PostgreSQL 是否运行
psql -h localhost -U postgres -c "SELECT 1"
```

**3. Kafka 不可用**
```bash
# Kafka 是可选的，如果不需要可以设置
# KAFKA_ENABLED=false
```

---

## 技术栈

- **Web 框架**: FastAPI
- **数据库**: PostgreSQL + SQLAlchemy
- **缓存**: Redis (Lua 脚本)
- **消息队列**: Kafka (aiokafka)
- **异步任务**: Celery
- **数据验证**: Pydantic
- **迁移工具**: Alembic

---

## 贡献指南

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

---

## 许可证

MIT License - 详见 LICENSE 文件

---

## 联系方式

- 项目主页：https://github.com/your-org/inventory-service
- 问题反馈：https://github.com/your-org/inventory-service/issues
- 团队邮箱：inventory@example.com
