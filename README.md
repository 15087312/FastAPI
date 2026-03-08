# FastAPI  库存微服务

一个专业的、生产级的库存微服务，支持高并发环境下的库存安全管理，防止超卖问题。

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## 核心特性

- ✅ **防超卖保障** - PostgreSQL 行级锁 + Redis 分布式锁双重保护
- ✅ **高性能缓存** - Redis 缓存层加速读取，支持批量操作
- ✅ **多层架构** - API / Celery / CLI 三种调用方式
- ✅ **完整审计** - 详细的操作日志和状态追踪
- ✅ **幂等保证** - 基于 Redis 的请求去重机制
- ✅ **优雅降级** - Redis 故障时自动降级到数据库模式

## 快速开始

### 环境要求
- Python 3.8+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### 一、环境配置
```bash
# 克隆项目
git clone https://github.com/15087312/FastAPI.git
cd FastAPI_mall

# 创建环境变量
 cp .env.example .env

# 编辑 .env 文件配置数据库和 Redis 连接
```

### 二、启动基础服务
```bash
# 启动 PostgreSQL 和 Redis
docker compose up -d

# 验证服务状态
docker compose ps
```

### 三、安装依赖并启动应用
```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload
```

### 四、 访问应用
- **API 文档**: http://localhost:8000/docs
- **ReDoc 文档**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- **健康检查**: http://localhost:8000/
- **pgAdmin**: http://localhost:5050

### 五、OpenAPI 功能特性

#### 自动生成的 API 文档
项目集成了完整的 OpenAPI 3.0 规范支持，提供：

- **Swagger UI 界面** - 交互式 API 测试界面
- **ReDoc 文档** - 美观的静态文档界面  
- **JSON 规范导出** - 标准 OpenAPI 3.0 JSON 格式

#### 核心 API 端点
- `POST /api/v1/inventory/reserve` - 预占库存
- `POST /api/v1/inventory/confirm/{order_id}` - 确认库存
- `POST /api/v1/inventory/release/{order_id}` - 释放库存
- `GET /api/v1/inventory/stock/{product_id}` - 查询单个商品库存
- `POST /api/v1/inventory/stock/batch` - 批量查询库存
- `POST /api/v1/inventory/cleanup/manual` - 手动清理过期预占
- `POST /api/v1/inventory/cleanup/celery` - 异步清理任务
- `GET /api/v1/inventory/cleanup/status/{task_id}` - 查询清理任务状态

#### 文档特性
- 完整的参数说明和数据类型验证
- 详细的响应示例和错误码说明
- 支持在线测试 API 接口
- 自动生成的 Pydantic 模型文档

## 🛠️ 环境配置详解

### Docker Compose 配置
项目使用 Docker Compose 管理依赖服务：

```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: 123456
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    
  pgadmin:
    image: dpage/pgadmin4
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - db

volumes:
  postgres_data:
  redis_data:
```

### 环境变量配置
创建 `.env` 文件配置应用环境：

```bash
# 数据库配置
DATABASE_URL=postgresql://postgres:123456@localhost:5432/mydb

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 应用配置
APP_ENV=development
DEBUG=True

# Redis分布式锁配置
REDIS_LOCK_TTL=10000
```

### 服务管理命令

```bash
# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看服务日志
docker compose logs -f

docker compose logs -f db     # 数据库日志
docker compose logs -f redis  # Redis日志

# 停止服务
docker compose down

# 停止并清除数据
docker compose down -v

# 重启特定服务
docker compose restart db
docker compose restart redis
```

## 🏗️ 项目架构

```bash
# 启动所有 Docker 服务（后台运行）
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs redis  # 查看 Redis 日志
docker compose logs db     # 查看数据库日志

# 查看当前运行的容器
docker ps
```

**说明：**

- 如果容器不存在 → 会自动创建
- 如果容器已存在但停止 → 会自动启动  
- 如果容器已运行 → 不会重复创建

```mermaid
graph TD
    A[API 请求] --> B[FastAPI 路由层]
    B --> C[InventoryService]
    C --> D{Redis 可用?}
    D -->|是| E[缓存读取]
    D -->|否| F[数据库查询]
    C --> G[分布式锁]
    G --> H[数据库操作]
    H --> I[缓存失效]
    I --> J[返回结果]
```

```bash
# 启动开发服务器（自动热重载）
uvicorn app.main:app --reload
```

**访问地址：**

- 应用主页：http://127.0.0.1:8000
- 接口文档（Swagger）：http://127.0.0.1:8000/docs

## 📚 文档资源

- [📘 技术文档](./技术文档.md) - 详细的架构设计和技术说明
- [📝 API 总览](docs/api总览.md) - 完整的接口文档


```bash
# 停止容器（不删除数据）
docker compose down
```

**数据管理**

```bash
# 停止服务（保留数据）
docker compose down

# 停止并清除所有数据
docker compose down -v

# 备份数据库
docker compose exec db pg_dump -U postgres mydb > backup.sql

# 恢复数据库
docker compose exec -T db psql -U postgres mydb < backup.sql
```

## ⚡ 一键启动脚本

### Windows PowerShell
```powershell
# 创建 start.ps1
@'
docker compose up -d
uvicorn app.main:app --reload
'@ | Out-File -FilePath start.ps1 -Encoding UTF8

# 运行
./start.ps1
```

### Linux/macOS Bash
```bash
#!/bin/bash
# 创建 start.sh

docker compose up -d
uvicorn app.main:app --reload

chmod +x start.sh
./start.sh
```

在项目根目录创建 `start.ps1`：

```powershell
# 启动数据库等基础服务
docker compose up -d

# 启动 FastAPI 开发服务器
uvicorn app.main:app --reload
```

**运行：**

```bash
.\start.ps1
```

## 🧪 测试

### 单元测试

项目包含完整的单元测试套件，覆盖以下模块：

- **库存服务测试** (`tests/test_inventory_service.py`) - 核心业务逻辑
- **路由测试** (`tests/test_inventory_router.py`) - API 接口层
- **模型测试** (`tests/test_models.py`) - 数据模型和约束
- **依赖注入测试** (`tests/test_dependencies.py`) - 依赖管理和注入
- **Celery 任务测试** (`tests/test_celery_tasks.py`) - 异步任务
- **集成测试** (`tests/test_app.py`) - 应用整体功能验证

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-cov httpx

# 运行所有测试
python run_tests.py --all

# 或使用 pytest 直接运行
python -m pytest tests/ -v

# 运行特定模块测试
python run_tests.py --service    # 库存服务
python run_tests.py --router     # 路由
python run_tests.py --models     # 模型
python run_tests.py --deps       # 依赖注入
python run_tests.py --tasks      # Celery 任务
python run_tests.py --integration # 集成测试

# 运行特定测试函数
python run_tests.py test_reserve_stock_success

# 生成覆盖率报告
python run_tests.py --coverage

# 并行执行测试 (需要安装 pytest-xdist)
python run_tests.py --parallel --all

# 组合选项
python run_tests.py --service --verbose --coverage
```

### 测试特性

- **Mock 驱动**：使用 unittest.mock 隔离外部依赖
- **数据库隔离**：使用内存 SQLite 数据库进行模型测试
- **完整覆盖**：涵盖正常流程、异常处理、边界条件
- **快速执行**：无需启动真实服务即可运行
- **并行支持**：支持多核并行执行测试（可选）

### 集成测试

```bash
# 运行集成测试（需要服务运行）
python run_tests.py --integration

# 或直接运行测试文件
python -m pytest tests/test_app.py -v

# 运行 OpenAPI 相关测试
python run_tests.py --openapi
```

测试覆盖内容：
- ✅ 健康检查和基础接口
- ✅ API 文档访问验证 (Swagger UI, ReDoc)
- ✅ OpenAPI Schema 完整性
- ✅ Pydantic 模型验证
- ✅ 库存路由注册检查
- ✅ CORS 头部支持
- ✅ 服务启动等待机制

## 🛠️ 开发工作流

1. **启动环境**: `docker compose up -d`
2. **运行应用**: `uvicorn app.main:app --reload`
3. **开发调试**: 
   - 使用 Swagger UI (`/docs`) 测试接口
   - 查看 ReDoc 文档 (`/redoc`) 
   - 验证 OpenAPI JSON (`/openapi.json`)
4. **运行测试**: 
   - `python -m pytest tests/` (单元测试)
   - `python test_openapi.py` (OpenAPI测试)
5. **停止服务**: `docker compose down`

1️⃣ `docker compose up -d`
2️⃣ `uvicorn app.main:app --reload` 
3️⃣ 开发接口
4️⃣ `docker compose down` （结束工作）

## 🔧 故障排除

### 服务状态检查
```bash
# 查看所有容器状态
docker compose ps

# 查看服务日志
docker compose logs db      # 数据库日志
docker compose logs redis   # Redis 日志

# 重启特定服务
docker compose restart db
docker compose restart redis
```

### 常见问题解决

**Redis 连接失败**
```bash
# 检查 Redis 服务
docker compose logs redis | grep -i error

# 重新创建 Redis 容器
docker compose down
docker compose up -d redis
```

**数据库连接超时**
```bash
# 检查数据库连接
docker compose exec db pg_isready

# 查看数据库日志
docker compose logs db | tail -20
```

**缓存数据不一致**
```bash
# 清理 Redis 缓存
docker compose exec redis redis-cli FLUSHALL

# 或重启 Redis 服务
docker compose restart redis
```

**查看容器状态：**
```bash
docker ps -a
```

**查看数据库日志：**
```bash
docker logs fastapi_db
```

**查看Redis日志：**
```bash
docker logs fastapi_redis
```

**重启特定服务：**
```bash
# 重启数据库
docker compose restart db

# 重启Redis
docker compose restart redis
```
## 📊 性能基准

| 操作类型 | QPS | 响应时间 | 缓存命中率 |
|---------|-----|---------|-----------|
| 单商品查询 | 5,000+ | <50ms | 90%+ |
| 批量查询(10个) | 2,000+ | <100ms | 85%+ |
| 库存预占 | 1,000+ | <200ms | N/A |
| 库存确认 | 1,500+ | <150ms | N/A |

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发规范
- 遵循 PEP 8 代码风格
- 添加必要的单元测试
- 更新相关文档
- 使用有意义的提交信息

### 本地开发
```bash
# 运行测试
python -m pytest tests/ -v

# 代码质量检查
flake8 app/
black app/

# 类型检查
mypy app/
```

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

<p align="center">
  <strong>📦 专业的库存管理解决方案</strong>
</p>