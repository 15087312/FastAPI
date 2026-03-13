# 健康检查使用指南

## 📋 概述

本项目提供完整的健康检查端点，用于监控服务运行状态和关键组件健康状况。

**端点**: `GET /health`  
**响应格式**: JSON  
**状态码**: 
- `200`: 服务健康
- `503`: 服务不健康

---

## 🔍 健康检查项

### 1. 数据库连接检查
- **检查内容**: PostgreSQL 数据库连接可用性
- **实现方式**: 执行 `SELECT 1` 查询
- **失败原因**: 数据库未启动、网络问题、认证失败

### 2. Redis 连接检查
- **检查内容**: Redis 缓存服务连接可用性
- **实现方式**: 执行 `PING` 命令
- **失败原因**: Redis 未启动、网络问题、密码错误

### 3. 数据库连接池状态
- **检查内容**: SQLAlchemy 连接池使用情况
- **监控指标**:
  - `size`: 连接池总大小
  - `checked_in`: 空闲连接数
  - `checked_out`: 已借出连接数
  - `overflow`: 溢出连接数
- **告警条件**: `checked_out >= size` 且 `overflow <= 0`

### 4. 系统资源监控
- **检查内容**: CPU 和内存使用率
- **依赖库**: psutil
- **告警条件**: 
  - CPU 使用率 > 95%
  - 内存使用率 > 95%
- **监控指标**:
  - `cpu_percent`: CPU 使用率 (%)
  - `memory_percent`: 内存使用率 (%)
  - `memory_available_mb`: 可用内存 (MB)

### 5. Kafka 消费者状态
- **检查内容**: Kafka 消费者运行状态
- **状态值**:
  - `running`: 运行中
  - `not started`: 未启动
  - `warning: ...`: 异常状态

---

## 📊 响应示例

### 成功响应 (服务健康)

```json
{
  "status": "healthy",
  "service": "inventory-microservice",
  "version": "1.0.0",
  "timestamp": "2026-03-12T22:19:51.738015",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "db_pool": {
      "size": 11,
      "checked_in": 1,
      "checked_out": 0,
      "overflow": -10
    },
    "db_pool_status": "ok",
    "system": {
      "cpu_percent": 27.4,
      "memory_percent": 86.0,
      "memory_available_mb": 2249.76
    },
    "system_status": "ok",
    "kafka_consumer": "running"
  }
}
```

### 失败响应 (服务不健康)

```json
{
  "status": "unhealthy",
  "service": "inventory-microservice",
  "version": "1.0.0",
  "timestamp": "2026-03-12T22:25:00.000000",
  "checks": {
    "database": "error: connection refused",
    "redis": "ok",
    "db_pool": "error: pool exhausted",
    "db_pool_status": "warning: pool exhausted",
    "system": {
      "cpu_percent": 98.5,
      "memory_percent": 96.2,
      "memory_available_mb": 128.5
    },
    "system_status": "warning: high resource usage",
    "kafka_consumer": "warning: connection timeout"
  }
}
```

---

## 🛠️ 使用方法

### 1. 命令行调用

#### cURL
```bash
curl http://localhost:8000/health
```

#### PowerShell
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" | ConvertTo-Json
```

#### Bash (Linux/Mac)
```bash
wget -qO- http://localhost:8000/health | python -m json.tool
```

---

### 2. Python 调用

#### 基础用法
```python
import requests

response = requests.get('http://localhost:8000/health')
if response.status_code == 200:
    health = response.json()
    print(f"服务状态：{health['status']}")
    print(f"数据库：{health['checks']['database']}")
    print(f"Redis: {health['checks']['redis']}")
else:
    print(f"服务不健康！状态码：{response.status_code}")
```

#### 完整监控脚本
```python
#!/usr/bin/env python3
"""服务健康监控脚本"""

import requests
import sys
from datetime import datetime

def check_health(base_url='http://localhost:8000'):
    """检查服务健康状态"""
    try:
        response = requests.get(f'{base_url}/health', timeout=5)
        
        if response.status_code != 200:
            print(f"❌ 服务不健康：HTTP {response.status_code}")
            return False
        
        health = response.json()
        
        print(f"✅ 服务健康检查报告 - {datetime.now()}")
        print(f"{'='*60}")
        print(f"总体状态：{health['status']}")
        print(f"服务版本：{health['version']}")
        print(f"时间戳：{health['timestamp']}")
        print(f"{'='*60}")
        
        # 详细检查项
        checks = health['checks']
        
        # 数据库
        db_status = checks.get('database', 'unknown')
        if db_status == 'ok':
            print(f"✅ 数据库：正常")
        else:
            print(f"❌ 数据库：{db_status}")
        
        # Redis
        redis_status = checks.get('redis', 'unknown')
        if redis_status == 'ok':
            print(f"✅ Redis: 正常")
        else:
            print(f"❌ Redis: {redis_status}")
        
        # 连接池
        db_pool = checks.get('db_pool', {})
        if isinstance(db_pool, dict):
            print(f"📊 连接池:")
            print(f"   总大小：{db_pool.get('size', 0)}")
            print(f"   空闲：{db_pool.get('checked_in', 0)}")
            print(f"   使用中：{db_pool.get('checked_out', 0)}")
            print(f"   溢出：{db_pool.get('overflow', 0)}")
            
            pool_status = checks.get('db_pool_status', 'unknown')
            if 'warning' in pool_status:
                print(f"⚠️  连接池告警：{pool_status}")
            else:
                print(f"✅ 连接池：正常")
        
        # 系统资源
        system = checks.get('system', {})
        if isinstance(system, dict):
            cpu = system.get('cpu_percent', 0)
            memory = system.get('memory_percent', 0)
            memory_avail = system.get('memory_available_mb', 0)
            
            print(f"💻 系统资源:")
            print(f"   CPU: {cpu}%")
            print(f"   内存：{memory}% (可用：{memory_avail:.2f}MB)")
            
            system_status = checks.get('system_status', 'unknown')
            if 'warning' in system_status:
                print(f"⚠️  系统资源告警：{system_status}")
            else:
                print(f"✅ 系统资源：正常")
        
        # Kafka 消费者
        kafka = checks.get('kafka_consumer', 'unknown')
        if kafka == 'running':
            print(f"✅ Kafka 消费者：运行中")
        elif 'warning' in kafka:
            print(f"⚠️  Kafka 消费者：{kafka}")
        else:
            print(f"ℹ️  Kafka 消费者：{kafka}")
        
        print(f"{'='*60}")
        
        # 综合判断
        if health['status'] == 'healthy':
            print("✅ 所有检查项通过！")
            return True
        else:
            print("❌ 存在异常检查项，请查看上方详细信息！")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时（5 秒）")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务")
        return False
    except Exception as e:
        print(f"❌ 检查失败：{e}")
        return False


if __name__ == '__main__':
    success = check_health()
    sys.exit(0 if success else 1)
```

---

### 3. 定时监控（Crontab）

#### Linux Crontab 配置
```bash
# 每 5 分钟检查一次服务健康状态
*/5 * * * * /path/to/health_check.py >> /var/log/health_check.log 2>&1
```

#### Windows Task Scheduler
```powershell
# 创建计划任务（每 5 分钟执行一次）
$action = New-ScheduledTaskAction -Execute "python" -Argument "D:\torch\FastAPI\health_check.py"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "HealthCheck" -Action $action -Trigger $trigger -User "SYSTEM"
```

---

## 🚨 告警集成

### 1. Prometheus + Grafana

**Exporter 配置** (`prometheus.yml`):
```yaml
scrape_configs:
  - job_name: 'inventory-service'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/health'
    scrape_interval: 30s
```

**Grafana 告警规则**:
```yaml
groups:
  - name: health_check
    rules:
      - alert: ServiceUnhealthy
        expr: health_status == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "服务不健康"
          description: "{{ $labels.instance }} 健康检查失败"
      
      - alert: HighResourceUsage
        expr: cpu_percent > 80 or memory_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "资源使用率过高"
          description: "CPU: {{ $value.cpu_percent }}%, Memory: {{ $value.memory_percent }}%"
```

---

### 2. 钉钉告警

**Python 脚本集成**:
```python
import requests
import json

def send_dingtalk_alert(message):
    """发送钉钉告警"""
    webhook = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": "服务健康告警",
            "text": f"## 🚨 服务健康告警\n\n{message}"
        }
    }
    
    response = requests.post(webhook, headers=headers, data=json.dumps(data))
    return response.status_code == 200


# 在健康检查中使用
if not check_health():
    health = get_health_status()
    alert_msg = f"""
### 服务信息
- 服务：{health['service']}
- 版本：{health['version']}
- 时间：{health['timestamp']}

### 异常项
- 数据库：{health['checks'].get('database', 'unknown')}
- Redis: {health['checks'].get('redis', 'unknown')}
- CPU: {health['checks'].get('system', {}).get('cpu_percent', 0)}%
- 内存：{health['checks'].get('system', {}).get('memory_percent', 0)}%
"""
    send_dingtalk_alert(alert_msg)
```

---

### 3. 企业微信告警

**Python 脚本集成**:
```python
import requests
import json

def send_wechat_alert(message):
    """发送企业微信告警"""
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"## 🚨 服务健康告警\n{message}"
        }
    }
    
    response = requests.post(webhook, headers=headers, data=json.dumps(data))
    return response.status_code == 200
```

---

## 📈 监控仪表板

### Grafana Dashboard JSON 模板

```json
{
  "dashboard": {
    "title": "库存服务健康监控",
    "panels": [
      {
        "title": "服务健康状态",
        "targets": [
          {
            "expr": "health_status",
            "legendFormat": "Health Status"
          }
        ],
        "thresholds": [
          {"value": 0, "color": "red"},
          {"value": 1, "color": "green"}
        ]
      },
      {
        "title": "CPU 使用率",
        "targets": [
          {
            "expr": "cpu_percent",
            "legendFormat": "CPU %"
          }
        ],
        "thresholds": [
          {"value": 80, "color": "orange"},
          {"value": 95, "color": "red"}
        ]
      },
      {
        "title": "内存使用率",
        "targets": [
          {
            "expr": "memory_percent",
            "legendFormat": "Memory %"
          }
        ],
        "thresholds": [
          {"value": 80, "color": "orange"},
          {"value": 95, "color": "red"}
        ]
      },
      {
        "title": "数据库连接池",
        "targets": [
          {
            "expr": "db_pool_size",
            "legendFormat": "Pool Size"
          },
          {
            "expr": "db_pool_checked_out",
            "legendFormat": "Checked Out"
          }
        ]
      }
    ]
  }
}
```

---

## 🔧 故障排查

### 常见问题及解决方案

#### 1. 数据库连接失败
**现象**: `checks.database = "error: connection refused"`

**排查步骤**:
1. 检查 PostgreSQL 是否运行：`docker compose ps`
2. 检查数据库端口：`netstat -an | grep 5432`
3. 检查连接配置：`.env` 文件中的 `POSTGRES_HOST`, `POSTGRES_PORT`
4. 检查防火墙规则

**解决方案**:
```bash
# 重启数据库
docker compose restart db

# 检查日志
docker compose logs db
```

---

#### 2. Redis 连接失败
**现象**: `checks.redis = "error: connection refused"`

**排查步骤**:
1. 检查 Redis 是否运行：`docker compose ps`
2. 检查 Redis 端口：`netstat -an | grep 6379`
3. 检查密码配置：`.env` 文件中的 `REDIS_PASSWORD`

**解决方案**:
```bash
# 重启 Redis
docker compose restart redis

# 测试连接
redis-cli ping
```

---

#### 3. 连接池耗尽
**现象**: `db_pool_status = "warning: pool exhausted"`

**排查步骤**:
1. 检查当前连接数：`checked_out >= size`
2. 检查是否有慢查询
3. 检查是否有连接泄漏

**解决方案**:
```python
# 临时增加连接池大小
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 40

# 长期方案：优化 SQL 查询，减少连接占用时间
```

---

#### 4. 高 CPU 使用率
**现象**: `cpu_percent > 95%`

**排查步骤**:
1. 检查是否有死循环代码
2. 检查是否有大量并发请求
3. 使用 profiling 工具分析性能瓶颈

**解决方案**:
```bash
# 查看进程 CPU 使用
ps aux | grep python

# 使用 py-spy 分析
pip install py-spy
py-spy top --pid <process_id>
```

---

#### 5. 高内存使用率
**现象**: `memory_percent > 95%`

**排查步骤**:
1. 检查是否有内存泄漏
2. 检查缓存数据量是否过大
3. 检查是否有大对象未释放

**解决方案**:
```python
# 使用 tracemalloc 分析内存
import tracemalloc
tracemalloc.start()

# ... 运行代码 ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

---

## 📚 最佳实践

### 1. 健康检查频率建议

| 环境 | 检查频率 | 超时时间 |
|------|----------|----------|
| 开发环境 | 每 30 秒 | 5 秒 |
| 测试环境 | 每 15 秒 | 3 秒 |
| 生产环境 | 每 10 秒 | 2 秒 |

---

### 2. 告警级别设置

| 级别 | 条件 | 通知方式 | 响应时间 |
|------|------|----------|----------|
| P0 - 严重 | 服务不可用 | 电话 + 短信 | 5 分钟 |
| P1 - 紧急 | 核心功能异常 | 钉钉/企微 | 15 分钟 |
| P2 - 警告 | 非核心功能异常 | 邮件 | 1 小时 |
| P3 - 提示 | 性能下降 | 日报 | 24 小时 |

---

### 3. 健康检查优化建议

1. **轻量级原则**: 健康检查应该快速返回，避免复杂计算
2. **独立性原则**: 各项检查应该相互独立，一项失败不影响其他项
3. **幂等性原则**: 健康检查不应该改变系统状态
4. **可配置原则**: 检查阈值应该可配置

---

## 🔗 相关文档

- [性能测试报告](./PERFORMANCE_TEST_REPORT.md)
- [系统监控 API](../app/routers/system_monitor.py)
- [健康检查实现](../app/main.py)
- [压力测试脚本](../stress_test.py)

---

**文档版本**: v1.0  
**更新时间**: 2026-03-12  
**维护者**: AI Assistant
