# 库存微服务性能测试指南

## 测试前准备

### 1. 确保服务已启动
```bash
# 启动 FastAPI 服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. 确保数据库和 Redis 可用
```bash
# 测试数据库连接
docker exec -it postgres_container psql -U postgres -d mydb -c "SELECT 1"

# 测试 Redis 连接
redis-cli ping
```

---

## 方案一：Python 脚本测试（推荐）

### 安装依赖
```bash
pip install aiohttp
```

### 运行测试

```bash
# 完整测试套件（默认 100 并发，1000 请求）
python tests/perf_test.py

# 自定义参数
python tests/perf_test.py --concurrency 200 --requests 5000

# 单独测试
python tests/perf_test.py --test query --concurrency 100 --requests 2000
python tests/perf_test.py --test reserve --concurrency 50 --requests 500
python tests/perf_test.py --test batch --concurrency 50 --requests 500
```

### 输出指标说明
- **QPS**: 每秒请求数
- **P50/P95/P99**: 响应时间百分位数
- **成功率/失败率**: 请求成功和失败的比例

---

## 方案二：wrk 压测工具

### 安装 wrk（Linux/Mac/WSL）
```bash
# Ubuntu/Debian
sudo apt-get install wrk

# Mac
brew install wrk
```

### 常用命令

```bash
# 1. 库存查询测试（GET 请求）
wrk -t4 -c100 -d30s "http://localhost:8000/api/v1/inventory/stock/1?warehouse_id=WH01"

# 2. 库存预占测试（POST 请求，需要 Lua 脚本）
wrk -t4 -c100 -d30s -s post_stock_reserve.lua http://localhost:8000/api/v1/inventory/reserve

# 参数说明：
# -t4: 4 个线程
# -c100: 100 个连接（并发）
# -d30s: 持续 30 秒
```

### wrk Lua 脚本示例

#### post_stock_reserve.lua
```lua
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"

counter = 0

request = function()
    counter = counter + 1
    local body = string.format([[{
        "warehouse_id": "WH01",
        "product_id": 1,
        "quantity": 1,
        "order_id": "WRK_TEST_%d"
    }]], counter)
    return wrk.format(nil, nil, nil, body)
end
```

---

## 方案三：Apache Bench (ab)

### 安装
```bash
# Ubuntu/Debian
sudo apt-get install apache2-utils

# Mac (已内置)
# Windows 可下载二进制
```

### 常用命令

```bash
# 1. 库存查询测试
ab -n 1000 -c 100 "http://localhost:8000/api/v1/inventory/stock/1?warehouse_id=WH01"

# 2. 库存预占测试（POST）
ab -n 1000 -c 100 -p post_data.json -T application/json \
   "http://localhost:8000/api/v1/inventory/reserve?warehouse_id=WH01&product_id=1&quantity=1&order_id=AB_TEST"

# 参数说明：
# -n 1000: 总请求数
# -c 100: 并发数
# -p: POST 数据文件
# -T: Content-Type
```

---

## 方案四：Locust 分布式压测（适合大规模测试）

### 安装
```bash
pip install locust
```

### 创建 locustfile.py
```python
from locust import HttpUser, task, between

class InventoryUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def query_stock(self):
        self.client.get("/api/v1/inventory/stock/1?warehouse_id=WH01")

    @task(1)
    def reserve_stock(self):
        import random
        order_id = f"LOCUST_TEST_{random.randint(1, 100000)}"
        self.client.post(
            f"/api/v1/inventory/reserve?warehouse_id=WH01&product_id=1&quantity=1&order_id={order_id}"
        )

    @task(1)
    def increase_stock(self):
        self.client.post(
            "/api/v1/inventory/increase",
            json={
                "warehouse_id": "WH01",
                "product_id": 1,
                "quantity": 10,
                "operator": "locust_test"
            }
        )
```

### 运行
```bash
# 单机模式
locust -f locustfile.py --host=http://localhost:8000

# 分布式模式（主节点）
locust -f locustfile.py --master --host=http://localhost:8000

# 分布式模式（工作节点）
locust -f locustfile.py --worker --master-host=localhost
```

---

## 测试场景建议

### 1. 基础性能测试
```bash
# 100 并发，1000 请求
python tests/perf_test.py --concurrency 100 --requests 1000
```

### 2. 极限压力测试
```bash
# 500 并发，10000 请求
python tests/perf_test.py --concurrency 500 --requests 10000
```

### 3. 持续压测
```bash
# 200 并发，持续 5 分钟
python tests/perf_test.py --concurrency 200 --requests 50000
```

### 4. 库存预占专项测试（超卖防护）
```bash
# 高并发预占测试（测试防超卖）
python tests/perf_test.py --test reserve --concurrency 200 --requests 500
```

---

## 关键指标解读

| 指标 | 说明 | 合格标准 |
|------|------|----------|
| QPS | 每秒处理请求数 | > 500 |
| P99 延迟 | 99% 请求响应时间 | < 200ms |
| 成功率 | 请求成功比例 | > 99.9% |
| 错误率 | 请求失败比例 | < 0.1% |

---

## 注意事项

1. **测试数据准备**: 预占测试前确保有足够的库存
2. **数据库状态**: 测试后清理测试数据
3. **网络延迟**: 本地测试比生产环境快
4. **瓶颈分析**: 
   - CPU 高 → Python/Gunicorn 需要优化
   - 数据库高 → 增加缓存、优化查询
   - Redis 高 → 检查缓存命中率
