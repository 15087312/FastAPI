# FastAPI Docker 部署指南

## 📦 Docker 文件说明

### 已创建的文件

1. **Dockerfile** - 多阶段构建镜像
   - `base`: 基础镜像（安装依赖）
   - `development`: 开发环境（包含完整代码，支持热重载）
   - `production`: 生产环境（优化大小和安全性）

2. **docker-compose.prod.yml** - 完整的服务编排
   - PostgreSQL 数据库
   - Redis 缓存
   - FastAPI 应用
   - pgAdmin（可选）

3. **.dockerignore** - 排除不需要的文件

---

## 🚀 快速启动

### 方式一：使用 Docker Compose（推荐）

#### 开发环境

```powershell
# 一键启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f app

# 停止服务
docker-compose -f docker-compose.prod.yml down
```

#### 生产环境

编辑 `docker-compose.prod.yml`，将第 50 行改为：
```yaml
target: production
```

然后启动：
```powershell
docker-compose -f docker-compose.prod.yml up -d --build
```

---

### 方式二：单独构建和运行

#### 1. 构建镜像

```powershell
# 开发镜像
docker build -t fastapi-dev --target development .

# 生产镜像
docker build -t fastapi-prod --target production .
```

#### 2. 运行容器

```powershell
# 运行开发容器
docker run -d \
  -p 8000:8000 \
  -e POSTGRES_HOST=host.docker.internal \
  -e REDIS_HOST=host.docker.internal \
  --name fastapi-app \
  fastapi-dev

# 运行生产容器
docker run -d \
  -p 8000:8000 \
  -e POSTGRES_HOST=host.docker.internal \
  -e REDIS_HOST=host.docker.internal \
  --name fastapi-app \
  fastapi-prod
```

---

## 🔧 环境变量配置

创建 `.env` 文件（基于 `.env.example`）：

```env
# 数据库配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=123456
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mydb

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 应用配置
APP_PORT=8000
DEBUG=True

# pgAdmin 配置
PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=123456
PGADMIN_PORT=5050
```

---

## 📊 服务访问地址

启动后访问以下地址：

| 服务 | 地址 | 说明 |
|------|------|------|
| FastAPI 应用 | http://localhost:8000 | 主服务 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| ReDoc 文档 | http://localhost:8000/redoc | ReDoc |
| PostgreSQL | localhost:5432 | 数据库 |
| Redis | localhost:6379 | 缓存 |
| pgAdmin | http://localhost:5050 | 数据库管理工具 |

---

## 🛠️ 常用命令

### 容器管理

```powershell
# 查看所有容器状态
docker-compose -f docker-compose.prod.yml ps

# 重启应用
docker-compose -f docker-compose.prod.yml restart app

# 停止所有服务
docker-compose -f docker-compose.prod.yml down

# 删除所有数据卷（危险！）
docker-compose -f docker-compose.prod.yml down -v
```

### 日志查看

```powershell
# 查看所有服务日志
docker-compose -f docker-compose.prod.yml logs -f

# 只看应用日志
docker-compose -f docker-compose.prod.yml logs -f app

# 查看最近 100 行
docker-compose -f docker-compose.prod.yml logs --tail=100 app
```

### 进入容器

```powershell
# 进入应用容器
docker exec -it fastapi_app sh

# 进入数据库容器
docker exec -it fastapi_db psql -U postgres

# 进入 Redis 容器
docker exec -it fastapi_redis redis-cli
```

### 数据库迁移

```powershell
# 手动执行迁移
docker-compose -f docker-compose.prod.yml exec app alembic upgrade head

# 查看当前版本
docker-compose -f docker-compose.prod.yml exec app alembic current
```

---

## 🎯 生产环境优化建议

### 1. 使用 Gunicorn

修改 `Dockerfile` 生产环境部分：

```dockerfile
RUN pip install gunicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "app.main:app"]
```

### 2. 安全加固

- 修改默认密码
- 使用 secrets 管理敏感信息
- 限制容器网络访问
- 定期更新基础镜像

### 3. 性能优化

```yaml
# docker-compose.prod.yml
app:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 1G
      reservations:
        cpus: '0.5'
        memory: 512M
```

---

## 🐛 故障排查

### 应用无法启动

```powershell
# 查看详细日志
docker-compose -f docker-compose.prod.yml logs app

# 检查容器状态
docker ps -a | grep fastapi

# 重新构建
docker-compose -f docker-compose.prod.yml up -d --build --force-recreate
```

### 数据库连接失败

```powershell
# 检查数据库是否健康
docker-compose -f docker-compose.prod.yml ps db

# 测试数据库连接
docker-compose -f docker-compose.prod.yml exec db pg_isready -U postgres
```

### 端口被占用

修改 `.env` 文件中的端口配置：
```env
APP_PORT=8001
POSTGRES_PORT=5433
PGADMIN_PORT=5051
```

---

## 📈 监控和健康检查

### 健康检查端点

```powershell
# 检查服务健康状态
curl http://localhost:8000/health

# 在 Docker 中检查
docker inspect --format='{{.State.Health.Status}}' fastapi_app
```

### 资源使用监控

```powershell
# 查看容器资源使用
docker stats fastapi_app
```

---

## 🔄 持续集成/部署

### GitHub Actions 示例

创建 `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Docker

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Docker image
        run: docker build -t myapp:latest --target production .
      
      - name: Run tests
        run: docker run myapp:latest pytest
      
      - name: Deploy
        run: |
          docker-compose -f docker-compose.prod.yml up -d
```

---

## 💡 最佳实践

1. **使用多阶段构建** - 减小镜像大小
2. **使用非 root 用户** - 提高安全性
3. **添加健康检查** - 自动恢复故障
4. **合理设置资源限制** - 防止资源耗尽
5. **使用数据卷持久化** - 保护重要数据
6. **定期更新依赖** - 修复安全漏洞
7. **日志集中管理** - 便于问题排查

---

## 📝 总结

现在你的 FastAPI 项目已经完全 Docker 化！

✅ 开发环境：代码热重载，快速迭代  
✅ 生产环境：安全优化，性能卓越  
✅ 完整栈：数据库 + 缓存 + 应用 + 管理工具  
✅ 一键部署：Docker Compose 编排  

开始使用吧！🚀
