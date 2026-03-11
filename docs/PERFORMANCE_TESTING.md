# API 性能测试模块使用指南

## 📦 模块介绍

性能测试模块提供了完整的 API 性能测试功能，支持多种测试场景和详细的性能指标分析。

## 🚀 快速开始

### 1. 访问 API 文档

启动服务后，访问 Swagger UI 查看完整 API 文档：
```
http://localhost:8000/docs
```

找到 **性能测试** 标签下的所有接口。

### 2. 核心 API 端点

#### 2.1 获取性能指标说明
```bash
GET http://localhost:8000/api/v1/perf/metrics/summary
```

返回所有性能指标的详细说明和评判标准。

#### 2.2 健康检查性能测试
```bash
GET http://localhost:8000/api/v1/perf/health?concurrency=100&requests=1000
```

参数：
- `concurrency`: 并发数（默认 100）
- `requests`: 总请求数（默认 1000）

#### 2.3 库存 API 性能测试套件 ⭐
```bash
POST http://localhost:8000/api/v1/perf/inventory
Content-Type: application/json

{
  "product_id": 1,
  "warehouse_id": "WH01",
  "concurrency": 100,
  "total_requests": 1000
}
```

测试包括：
- ✅ 库存查询
- ✅ 库存预占
- ✅ 库存确认
- ✅ 库存释放
- ✅ 库存增加
- ✅ 健康检查

#### 2.4 单个 API 性能测试
```bash
POST http://localhost:8000/api/v1/perf/single
Content-Type: application/json

{
  "api_name": "库存查询",
  "method": "GET",
  "path": "/api/v1/inventory/stock/1?warehouse_id=WH01",
  "concurrency": 100,
  "total_requests": 1000,
  "timeout": 30
}
```

#### 2.5 阶梯式压力测试 🔥
```bash
POST http://localhost:8000/api/v1/perf/stress
Content-Type: application/json

{
  "path": "/health",
  "method": "GET",
  "start_concurrency": 100,
  "max_concurrency": 1000,
  "step": 100
}
```

从低并发到高并发逐步增加，观察系统性能变化。

#### 2.6 自定义组合测试
```bash
POST http://localhost:8000/api/v1/perf/custom
Content-Type: application/json

{
  "tests": [
    {
      "api_name": "查询测试",
      "method": "GET",
      "path": "/api/v1/inventory/stock/1",
      "concurrency": 100,
      "total_requests": 500
    },
    {
      "api_name": "预占测试",
      "method": "POST",
      "path": "/api/v1/inventory/reserve",
      "concurrency": 50,
      "total_requests": 200
    }
  ]
}
```

## 📊 性能指标说明

### 基础指标
- **total_requests**: 总请求数
- **success_count**: 成功请求数
- **failure_count**: 失败请求数
- **success_rate**: 成功率 (%)
- **failure_rate**: 失败率 (%)

### 时间指标
- **total_time**: 总耗时 (秒)
- **avg_latency_ms**: 平均延迟 (毫秒)
- **min_latency_ms**: 最小延迟 (毫秒)
- **max_latency_ms**: 最大延迟 (毫秒)

### 百分位延迟
- **p50_latency_ms**: P50 延迟 - 50% 请求的延迟低于此值
- **p75_latency_ms**: P75 延迟 - 75% 请求的延迟低于此值
- **p90_latency_ms**: P90 延迟 - 90% 请求的延迟低于此值
- **p95_latency_ms**: P95 延迟 - 95% 请求的延迟低于此值
- **p99_latency_ms**: P99 延迟 - 99% 请求的延迟低于此值

### 吞吐量指标
- **qps**: 每秒查询数 (Queries Per Second)
- **tps**: 每秒事务数 (Transactions Per Second)

### 错误统计
- **error_types**: 错误类型统计（timeout, client_error, unknown）

## 🎯 性能评判标准

### 优秀 (Excellent)
- QPS > 1000
- P95 延迟 < 100ms
- 成功率 > 99.9%

### 良好 (Good)
- QPS: 500 - 1000
- P95 延迟: 100 - 500ms
- 成功率: 99% - 99.9%

### 可接受 (Acceptable)
- QPS: 100 - 500
- P95 延迟: 500ms - 1s
- 成功率: 95% - 99%

### 较差 (Poor)
- QPS < 100
- P95 延迟 > 1s
- 成功率 < 95%

## 💾 测试结果管理

### 获取历史测试结果列表
```bash
GET http://localhost:8000/api/v1/perf/results
```

### 获取特定测试结果
```bash
GET http://localhost:8000/api/v1/perf/results/{filename}
```

### 删除测试结果
```bash
DELETE http://localhost:8000/api/v1/perf/results/{filename}
```

所有测试结果保存在 `test_results/` 目录下。

## 🔧 Python 命令行使用

### 方式 1：使用测试脚本
```bash
cd tests
python api_perf_test.py --url http://localhost:8000 --concurrency 100 --requests 1000 --test inventory
```

可用测试类型：
- `health`: 健康检查测试
- `inventory`: 库存 API 套件测试
- `stress`: 阶梯压力测试

### 方式 2：直接导入模块
```python
from tests.api_perf_test import PerformanceTestSuite, TestConfig
import asyncio

async def run_test():
    suite = PerformanceTestSuite("http://localhost:8000")
    
    # 运行库存 API 测试套件
    results = await suite.run_inventory_tests(
        product_id=1,
        warehouse_id="WH01",
        config=TestConfig(concurrency=100, total_requests=1000)
    )
    
    # 生成报告
    report = suite.generate_report()
    print(report)

asyncio.run(run_test())
```

## 📈 前端集成示例

### Vue/React 示例
```javascript
// 运行库存性能测试
async function runInventoryTest() {
  const response = await fetch('/api/v1/perf/inventory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      concurrency: 100,
      total_requests: 1000,
      product_id: 1,
      warehouse_id: 'WH01'
    })
  });
  
  const result = await response.json();
  console.log('QPS:', result.summary.avg_qps);
  console.log('P95 延迟:', result.summary.avg_p95_latency_ms);
  console.log('成功率:', result.summary.avg_success_rate);
}

// 获取性能指标说明
async function getMetricsInfo() {
  const response = await fetch('/api/v1/perf/metrics/summary');
  const metrics = await response.json();
  return metrics;
}
```

## ⚠️ 注意事项

1. **测试环境**: 建议在测试环境运行，避免影响生产数据
2. **并发控制**: 根据服务器性能调整并发数，避免过载
3. **数据清理**: 定期清理 `test_results/` 目录下的测试结果
4. **网络延迟**: 本地测试和网络测试的结果会有差异
5. **数据库影响**: 写操作测试会影响数据库数据，请谨慎使用

## 🎉 最佳实践

1. **基准测试**: 每次代码变更前运行相同的测试用例
2. **压力测试**: 定期运行阶梯压力测试，了解系统瓶颈
3. **监控对比**: 保存历史测试结果，对比性能变化
4. **多维度测试**: 结合多种测试场景，全面评估系统性能
5. **实时监控**: 测试时监控系统资源使用情况

---

**技术支持**: 如有问题，请查看 API 文档或联系开发团队。
