# 🚀 快速启动和压力测试指南

## ⚡ 快速启动

### 方法一：使用启动脚本（推荐）

```bash
# Windows PowerShell
python start_server.py

# Linux/Mac
python3 start_server.py
```

**优点：**
- ✅ 自动检测 CPU 核心数
- ✅ 智能计算最优 workers 数量
- ✅ 显示详细的环境信息
- ✅ 支持环境变量配置

### 方法二：直接运行

```bash
# 多进程模式（生产环境）
python app/main.py

# 单进程模式（仅用于调试）
uvicorn app.main:app --reload
```

## 🔧 配置选项

### 1. 基本配置（.env 文件）

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置
# Windows: 用记事本打开 .env
# Linux/Mac: nano .env
```

### 2. 并发配置

在 `.env` 文件中设置：

```bash
# Workers 数量（可选，默认自动计算）
UVICORN_WORKERS=4

# 数据库连接池（可选）
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

### 3. 不同场景配置建议

#### 开发环境（笔记本/低配）
```bash
DEBUG=True
UVICORN_WORKERS=1
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

#### 生产环境（4 核 CPU）
```bash
DEBUG=False
UVICORN_WORKERS=4
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

#### 生产环境（8 核 CPU）
```bash
DEBUG=False
UVICORN_WORKERS=8
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=60
```

## 📊 压力测试

### 运行压力测试

```bash
# 执行 1000 并发测试
python load_test.py
```

### 测试结果解读

**优秀性能指标：**
```
✅ QPS ≥ 5000
✅ 成功率 ≥ 99.9%
✅ 平均响应时间 < 50ms
```

**良好性能指标：**
```
✅ QPS ≥ 1000
✅ 成功率 ≥ 99%
✅ 平均响应时间 < 100ms
```

**需要优化：**
```
⚠️  QPS < 500
⚠️  成功率 < 95%
⚠️  平均响应时间 > 200ms
```

## 🎯 性能优化清单

### 已完成的优化
- ✅ 多进程 uvicorn 支持
- ✅ 自动计算最优 workers 数量
- ✅ uvloop 和 httptools 性能优化
- ✅ 数据库连接池优化
- ✅ Redis 分布式锁支持
- ✅ 并发压力测试工具

### 可进一步优化的点
- [ ] 增加 Redis 缓存命中率
- [ ] 数据库查询优化（添加索引）
- [ ] 使用 Gunicorn 作为进程管理器（更稳定）
- [ ] Nginx 负载均衡（超高并发场景）
- [ ] 容器水平扩展（Kubernetes/Docker Swarm）

## 🐛 故障排查

### 问题 1：服务器启动失败

**检查端口占用：**
```bash
# Windows
netstat -ano | findstr :8000

# Linux/Mac
lsof -i :8000
```

**解决方法：**
```bash
# 修改 .env 中的 PORT
PORT=8001
```

### 问题 2：Workers 数量不生效

**检查 DEBUG 模式：**
```bash
# 确保生产环境设置为 False
DEBUG=False
```

### 问题 3：数据库连接不足

**症状：**
- 错误信息：`QueuePool limit of size X overflow Y reached`
- 响应时间突然变长

**解决方法：**
```bash
# 增加连接池大小
DB_POOL_SIZE=40
DB_MAX_OVERFLOW=80
```

### 问题 4：CPU 使用率低但 QPS 不高

**可能原因：**
- I/O 瓶颈（数据库/Redis 慢）
- 代码逻辑问题
- 网络延迟

**排查步骤：**
1. 检查数据库慢查询日志
2. 监控 Redis 响应时间
3. 使用 profiling 工具分析代码

## 📈 监控命令

### 查看服务器状态

```bash
# Windows PowerShell
Get-Process python | Select-Object CPU,WorkingSet,Threads

# Linux
top -p $(pgrep -f 'python.*main.py')

# 查看网络连接
netstat -an | grep :8000
```

### 查看 Docker 容器状态

```bash
# 查看所有容器
docker compose ps

# 查看资源使用
docker stats

# 查看应用日志
docker compose logs -f app
```

## 🎓 学习资源

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [Uvicorn 部署文档](https://www.uvicorn.org/deployment/)
- [高并发架构设计](https://github.com/donnemartin/system-design-primer)

---

**祝你的服务器能抗住 1000 并发！** 🎉

有问题？查看 `docs/高并发配置指南.md` 获取详细说明。
