"""API 性能测试服务 - 为前端提供性能测试接口"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import statistics

# 导入 FastAPI 相关依赖
try:
    from fastapi import HTTPException
except ImportError:
    HTTPException = Exception


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    # 基础指标
    total_requests: int = 0  # 总请求数
    success_count: int = 0  # 成功数
    failure_count: int = 0  # 失败数
    success_rate: float = 0.0  # 成功率 (%)
    failure_rate: float = 0.0  # 失败率 (%)
    
    # 时间指标
    total_time: float = 0.0  # 总耗时 (秒)
    avg_latency_ms: float = 0.0  # 平均延迟 (毫秒)
    min_latency_ms: float = 0.0  # 最小延迟 (毫秒)
    max_latency_ms: float = 0.0  # 最大延迟 (毫秒)
    
    # 百分位延迟
    p50_latency_ms: float = 0.0  # P50 延迟 (毫秒)
    p75_latency_ms: float = 0.0  # P75 延迟 (毫秒)
    p90_latency_ms: float = 0.0  # P90 延迟 (毫秒)
    p95_latency_ms: float = 0.0  # P95 延迟 (毫秒)
    p99_latency_ms: float = 0.0  # P99 延迟 (毫秒)
    
    # 吞吐量指标
    qps: float = 0.0  # 每秒查询数
    tps: float = 0.0  # 每秒事务数
    
    # 错误统计
    error_types: Dict[str, int] = None  # 错误类型统计
    
    def __post_init__(self):
        if self.error_types is None:
            self.error_types = {}
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class TestConfig:
    """测试配置"""
    concurrency: int = 100  # 并发数
    total_requests: int = 1000  # 总请求数
    timeout: int = 30  # 超时时间 (秒)
    duration: int = None  # 测试持续时间 (秒)，如果设置则忽略 total_requests
    ramp_up: int = 0  # 爬坡时间 (秒)
    

class APITester:
    """单个 API 测试器"""
    
    def __init__(self, base_url: str, config: TestConfig):
        self.base_url = base_url
        self.config = config
        self.results: List[tuple] = []  # [(status, latency, error_type), ...]
        self.start_time: float = 0
        self.end_time: float = 0
        
    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> tuple:
        """发起单个请求"""
        url = f"{self.base_url}{path}"
        start = time.time()
        
        try:
            if method.upper() == "GET":
                async with session.get(url, timeout=self.config.timeout) as response:
                    await response.text()
                    latency = time.time() - start
                    return response.status, latency, None
                    
            elif method.upper() == "POST":
                async with session.post(
                    url, 
                    json=data, 
                    headers=headers or {"Content-Type": "application/json"},
                    timeout=self.config.timeout
                ) as response:
                    await response.text()
                    latency = time.time() - start
                    return response.status, latency, None
                    
            elif method.upper() == "PUT":
                async with session.put(
                    url, 
                    json=data,
                    timeout=self.config.timeout
                ) as response:
                    await response.text()
                    latency = time.time() - start
                    return response.status, latency, None
                    
            elif method.upper() == "DELETE":
                async with session.delete(url, timeout=self.config.timeout) as response:
                    await response.text()
                    latency = time.time() - start
                    return response.status, latency, None
                    
        except asyncio.TimeoutError:
            latency = time.time() - start
            return 0, latency, "timeout"
        except aiohttp.ClientError as e:
            latency = time.time() - start
            return 0, latency, "client_error"
        except Exception as e:
            latency = time.time() - start
            return 0, latency, "unknown"
    
    async def run_test(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        test_name: str = "API Test"
    ) -> PerformanceMetrics:
        """运行性能测试"""
        self.results = []
        
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(self.config.concurrency)
            
            async def bounded_request():
                async with semaphore:
                    result = await self._make_request(session, method, path, data)
                    self.results.append(result)
                    return result
            
            # 创建任务
            tasks = [bounded_request() for _ in range(self.config.total_requests)]
            
            # 执行
            self.start_time = time.time()
            await asyncio.gather(*tasks)
            self.end_time = time.time()
        
        return self._calculate_metrics()
    
    def _calculate_metrics(self) -> PerformanceMetrics:
        """计算性能指标"""
        total_time = self.end_time - self.start_time
        total_requests = len(self.results)
        
        # 分离状态码和延迟
        statuses = [r[0] for r in self.results]
        latencies = [r[1] * 1000 for r in self.results]  # 转换为毫秒
        errors = [r[2] for r in self.results]
        
        # 成功/失败统计
        success_count = sum(1 for s in statuses if 200 <= s < 300)
        failure_count = total_requests - success_count
        
        # 错误类型统计
        error_types = {}
        for error in errors:
            if error:
                error_types[error] = error_types.get(error, 0) + 1
        
        # 延迟统计
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        
        metrics = PerformanceMetrics(
            total_requests=total_requests,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=(success_count / total_requests * 100) if total_requests > 0 else 0,
            failure_rate=(failure_count / total_requests * 100) if total_requests > 0 else 0,
            total_time=total_time,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            p50_latency_ms=latencies_sorted[int(n * 0.50)] if n > 0 else 0,
            p75_latency_ms=latencies_sorted[int(n * 0.75)] if n > 0 else 0,
            p90_latency_ms=latencies_sorted[int(n * 0.90)] if n > 0 else 0,
            p95_latency_ms=latencies_sorted[int(n * 0.95)] if n > 0 else 0,
            p99_latency_ms=latencies_sorted[int(n * 0.99)] if n > 0 else 0,
            qps=total_requests / total_time if total_time > 0 else 0,
            tps=success_count / total_time if total_time > 0 else 0,
            error_types=error_types
        )
        
        return metrics


class PerformanceTestSuite:
    """性能测试套件 - 管理多个 API 测试"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_results: Dict[str, PerformanceMetrics] = {}
        
    async def run_single_test(
        self,
        api_name: str,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        config: Optional[TestConfig] = None
    ) -> PerformanceMetrics:
        """运行单个 API 测试"""
        if config is None:
            config = TestConfig()
        
        tester = APITester(self.base_url, config)
        result = await tester.run_test(method, path, data, api_name)
        
        self.test_results[api_name] = result
        return result
    
    async def run_inventory_tests(
        self,
        product_id: int = 1,
        warehouse_id: str = "WH01",
        config: Optional[TestConfig] = None
    ) -> Dict[str, PerformanceMetrics]:
        """运行库存相关 API 测试"""
        if config is None:
            config = TestConfig(concurrency=100, total_requests=1000)
        
        tests = [
            {
                "name": "库存查询",
                "method": "GET",
                "path": f"/api/v1/inventory/stock/{product_id}?warehouse_id={warehouse_id}",
                "data": None
            },
            {
                "name": "库存预占",
                "method": "POST",
                "path": "/api/v1/inventory/reserve",
                "data": {
                    "order_id": "PERF_TEST_ORDER",
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "quantity": 1
                }
            },
            {
                "name": "库存确认",
                "method": "POST",
                "path": "/api/v1/inventory/confirm",
                "data": {
                    "order_id": "PERF_TEST_ORDER"
                }
            },
            {
                "name": "库存释放",
                "method": "POST",
                "path": "/api/v1/inventory/release",
                "data": {
                    "order_id": "PERF_TEST_ORDER"
                }
            },
            {
                "name": "库存增加",
                "method": "POST",
                "path": "/api/v1/inventory/increase",
                "data": {
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "quantity": 10,
                    "operator": "perf_test"
                }
            },
            {
                "name": "健康检查",
                "method": "GET",
                "path": "/health",
                "data": None
            }
        ]
        
        results = {}
        for test in tests:
            print(f"\n📊 测试：{test['name']}")
            result = await self.run_single_test(
                api_name=test["name"],
                method=test["method"],
                path=test["path"],
                data=test["data"],
                config=config
            )
            results[test["name"]] = result
            self._print_summary(result)
        
        return results
    
    async def run_stress_test(
        self,
        path: str,
        method: str = "GET",
        data: Optional[Dict] = None,
        max_concurrency: int = 1000,
        step: int = 100
    ) -> List[Dict]:
        """阶梯式压力测试"""
        results = []
        
        for concurrency in range(step, max_concurrency + 1, step):
            config = TestConfig(concurrency=concurrency, total_requests=1000)
            tester = APITester(self.base_url, config)
            metric = await tester.run_test(method, path, data)
            
            results.append({
                "concurrency": concurrency,
                "metrics": metric.to_dict()
            })
            
            print(f"\n并发数：{concurrency} | QPS: {metric.qps:.2f} | P95: {metric.p95_latency_ms:.2f}ms")
        
        return results
    
    def _print_summary(self, metrics: PerformanceMetrics):
        """打印摘要信息"""
        print(f"  总请求：{metrics.total_requests}")
        print(f"  成功率：{metrics.success_rate:.2f}%")
        print(f"  QPS: {metrics.qps:.2f}")
        print(f"  平均延迟：{metrics.avg_latency_ms:.2f}ms")
        print(f"  P95 延迟：{metrics.p95_latency_ms:.2f}ms")
    
    def get_all_results(self) -> Dict[str, dict]:
        """获取所有测试结果"""
        return {name: metrics.to_dict() for name, metrics in self.test_results.items()}
    
    def generate_report(self) -> dict:
        """生成综合报告"""
        if not self.test_results:
            return {"error": "No tests run yet"}
        
        all_qps = [m.qps for m in self.test_results.values()]
        all_p95 = [m.p95_latency_ms for m in self.test_results.values()]
        all_success_rates = [m.success_rate for m in self.test_results.values()]
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "summary": {
                "total_tests": len(self.test_results),
                "avg_qps": statistics.mean(all_qps) if all_qps else 0,
                "max_qps": max(all_qps) if all_qps else 0,
                "avg_p95_latency_ms": statistics.mean(all_p95) if all_p95 else 0,
                "avg_success_rate": statistics.mean(all_success_rates) if all_success_rates else 0,
            },
            "tests": self.get_all_results()
        }
        
        return report


# ==================== 快速测试函数 ====================

async def quick_test(
    url: str = "http://localhost:8000",
    concurrency: int = 100,
    requests: int = 1000
) -> PerformanceMetrics:
    """快速测试健康检查接口"""
    config = TestConfig(concurrency=concurrency, total_requests=requests)
    tester = APITester(url, config)
    return await tester.run_test("GET", "/health")


# ==================== CLI 入口 ====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="API 性能测试工具")
    parser.add_argument("--url", default="http://localhost:8000", help="服务地址")
    parser.add_argument("--concurrency", type=int, default=100, help="并发数")
    parser.add_argument("--requests", type=int, default=1000, help="请求数")
    parser.add_argument("--test", choices=["health", "inventory", "stress"], 
                       default="inventory", help="测试类型")
    
    args = parser.parse_args()
    
    suite = PerformanceTestSuite(args.url)
    
    if args.test == "health":
        result = asyncio.run(quick_test(args.url, args.concurrency, args.requests))
        print("\n" + "="*60)
        print("健康检查性能测试")
        print("="*60)
        for key, value in result.to_dict().items():
            print(f"{key}: {value}")
    
    elif args.test == "inventory":
        print("\n🚀 开始库存 API 性能测试")
        results = asyncio.run(suite.run_inventory_tests(config=TestConfig(
            concurrency=args.concurrency,
            total_requests=args.requests
        )))
        
        print("\n" + "="*60)
        print("测试完成")
        print("="*60)
    
    elif args.test == "stress":
        print("\n🔥 开始阶梯压力测试")
        results = asyncio.run(suite.run_stress_test(
            path="/health",
            method="GET",
            max_concurrency=1000,
            step=100
        ))
