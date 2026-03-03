# Docker 部署配置经验总结

## 📋 问题背景

在将 FastAPI 项目容器化部署时，遇到了数据库连接失败的问题。通过排查和修复，总结了以下关键配置经验。

---

## 🔍 遇到的问题

### **症状**
- FastAPI 容器不断重启
- 日志显示：`connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused`
- 无法连接到 PostgreSQL 数据库

### **根本原因**
项目在多个地方硬编码了 `localhost` 作为数据库主机名，而在 Docker 环境中应该使用服务名 `db`。

---

## ✅ 解决方案

需要修改以下配置文件：

### **1. app/core/config.py**

**问题代码：**
```python
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")  # ❌ 默认值 localhost
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")        # ❌ 默认值 localhost
```

**修复后：**
```python
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")         # ✅ Docker 服务名
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")            # ✅ Docker 服务名
```

**说明：**
- 在 Docker Compose 中，容器间通信使用**服务名**作为主机名
- `db` 是 PostgreSQL 容器的服务名
- `redis` 是 Redis 容器的服务名

---

### **2. alembic.ini**

**问题代码：**
```ini
sqlalchemy.url = postgresql+psycopg://postgres:123456@localhost:5432/mydb  # ❌ localhost
```

**修复后：**
```ini
sqlalchemy.url = postgresql+psycopg://postgres:123456@db:5432/mydb  # ✅ db 服务名
```

**说明：**
- Alembic 迁移脚本直接从 ini 文件读取配置，不使用环境变量
- 必须显式修改为 Docker 服务名

---

### **3. docker-compose.prod.yml**

**确保环境变量正确配置：**
```yaml
app:
  environment:
    # 数据库配置
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=123456
    - POSTGRES_HOST=db              # ✅ 明确指定
    - POSTGRES_PORT=5432
    - POSTGRES_DB=mydb
    # Redis 配置
    - REDIS_HOST=redis              # ✅ 明确指定
    - REDIS_PORT=6379
    - REDIS_DB=0
```

**说明：**
- 显式指定所有环境变量，避免依赖默认值
- 使用 Docker 服务名作为主机地址

---

## ⚠️ 重要注意事项

### **1. Docker Compose 网络**

```yaml
services:
  app:
    # ...
  db:
    image: postgres:15-alpine
    # ...
  redis:
    image: redis:7-alpine
    # ...
```

- `app` 容器访问 `db` 容器：使用主机名 `db`
- `app` 容器访问 `redis` 容器：使用主机名 `redis`
- **不能**使用 `localhost` 或 `127.0.0.1`

---

### **2. 开发环境 vs 生产环境**

#### **本地开发（直接运行）**
```env
POSTGRES_HOST=localhost
REDIS_HOST=localhost
```

#### **Docker 容器环境**
```env
POSTGRES_HOST=db
REDIS_HOST=redis
```

**最佳实践：**
- 通过环境变量区分环境
- 代码中的默认值应该适合目标部署环境
- 使用 `.env` 文件管理不同环境的配置

---

### **3. volumes 挂载的影响**

**开发模式（代码热重载）：**
```yaml
volumes:
  - ./app:/app/app  # ⚠️ 会覆盖镜像中的代码
```

**生产模式（使用镜像代码）：**
```yaml
volumes: []
  # - ./app:/app/app  # 已注释，不使用挂载
```

**警告：**
- volumes 挂载会用本地代码覆盖镜像中的代码
- 如果本地代码未更新，会导致修复不生效
- 生产部署应使用构建好的镜像，不挂载代码

---

## 🛠️ 排查步骤

### **1. 查看容器日志**
```powershell
docker logs fastapi_app --tail 50
```

### **2. 检查容器状态**
```powershell
docker ps --filter "name=fastapi"
```

### **3. 验证环境变量**
```powershell
docker exec fastapi_app env | Select-String -Pattern "POSTGRES|REDIS"
```

### **4. 测试数据库连接**
```powershell
docker exec fastapi_app python -c "from app.core.config import settings; print(settings.POSTGRES_HOST)"
```

### **5. 检查镜像中的代码**
```powershell
docker run --rm fastapi-app cat /app/app/core/config.py | Select-String -Pattern "POSTGRES_HOST"
```

---

## 📊 配置对比表

| 配置文件 | 本地开发 | Docker 容器 | 说明 |
|---------|---------|-----------|------|
| **config.py** | `localhost` | `db` / `redis` | 默认值需适配目标环境 |
| **alembic.ini** | `localhost` | `db` | 数据库迁移配置 |
| **docker-compose.yml** | N/A | 服务名 | 定义容器间网络 |
| **.env** | `localhost` | `db` / `redis` | 环境变量管理 |

---

## 🎯 最佳实践建议

### **1. 使用环境变量**
```python
# ✅ 推荐：从环境变量读取，提供合理的默认值
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")
```

### **2. 区分环境配置**
```bash
# .env.development
POSTGRES_HOST=localhost

# .env.docker
POSTGRES_HOST=db

# .env.production
POSTGRES_HOST=prod-db.example.com
```

### **3. 避免硬编码**
```python
# ❌ 禁止：硬编码主机名
DATABASE_URL = "postgresql://user:pass@localhost:5432/db"

# ✅ 推荐：从配置读取
DATABASE_URL = os.getenv("DATABASE_URL")
```

### **4. 添加健康检查**
```yaml
app:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### **5. 使用 Docker 多阶段构建**
```dockerfile
# 开发环境
FROM python:3.11-slim as development
COPY . .

# 生产环境
FROM python:3.11-slim as production
# 优化镜像大小和安全性
```

---

## 🔗 相关资源

- [Docker Compose 网络](https://docs.docker.com/compose/networking/)
- [FastAPI 配置管理](https://fastapi.tiangolo.com/advanced/settings/)
- [Alembic 配置指南](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

---

## 💡 总结

容器化部署的关键点：

1. ✅ **理解 Docker 网络**：容器间使用服务名通信
2. ✅ **检查所有配置**：包括代码、配置文件、迁移脚本
3. ✅ **避免硬编码**：使用环境变量管理配置
4. ✅ **注意 volumes 影响**：挂载会覆盖镜像内容
5. ✅ **多环境测试**：确保配置在不同环境都有效

通过这些调整，FastAPI 应用可以顺利在 Docker 容器中运行，并正确连接到数据库和缓存服务。
