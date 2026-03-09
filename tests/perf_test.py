"""库存微服务性能测试工具"""

import asyncio
import aiohttp
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict
import statistics


@dataclass
class TestResult:
    """测试结果"""
    total_requests: int
    success_count: int
    failure_count: int
    success_rate: float
    failure_rate: float
    total_time: float
    qps: float
    avg_latency: float
    min_latency: float
    max_latency: float
    p50_latency: float
    p95_latency: float
    p99_latency: float


class InventoryPerformanceTester:
    """库存服务性能测试器"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[float] = []

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            "Content-Type": "application/json"
        }

    async def _single_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data: dict = None
    ) -> tuple:
        """发起单个请求"""
        url = f"{self.base_url}{path}"
        start_time = time.time()

        try:
            if method.upper() == "GET":
                async with session.get(url) as response:
                    await response.text()
                    latency = time.time() - start_time
                    return response.status, latency
            elif method.upper() == "POST":
                async with session.post(url, json=data, headers=self._build_headers()) as response:
                    await response.text()
                    latency = time.time() - start_time
                    return response.status, latency
        except Exception as e:
            latency = time.time() - start_time
            return 0, latency  # 0 表示请求失败

    async def _run_concurrent_requests(
        self,
        method: str,
        path: str,
        data: dict,
        concurrency: int,
        total_requests: int
    ) -> TestResult:
        """并发执行请求"""
        self.results = []

        async with aiohttp.ClientSession() as session:
            # 创建信号量控制并发数
            semaphore = asyncio.Semaphore(concurrency)

            async def bounded_request():
                async with semaphore:
                    status, latency = await self._single_request(
                        session, method, path, data
                    )
                    self.results.append((status, latency))
                    return status, latency

            # 创建所有任务
            tasks = [bounded_request() for _ in range(total_requests)]

            # 执行
            start_time = time.time()
            await asyncio.gather(*tasks)
            total_time = time.time() - start_time

        # 统计结果
        success_count = sum(1 for status, _ in self.results if 200 <= status < 300)
        failure_count = total_requests - success_count

        latencies = [latency for _, latency in self.results]

        return self._calculate_results(
            total_requests, success_count, failure_count,
            total_time, latencies
        )

    def _calculate_results(
        self,
        total_requests: int,
        success_count: int,
        failure_count: int,
        total_time: float,
        latencies: List[float]
    ) -> TestResult:
        """计算测试结果"""
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        return TestResult(
            total_requests=total_requests,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_count / total_requests * 100,
            failure_rate=failure_count / total_requests * 100,
            total_time=total_time,
            qps=total_requests / total_time if total_time > 0 else 0,
            avg_latency=statistics.mean(latencies) if latencies else 0,
            min_latency=min(latencies) if latencies else 0,
            max_latency=max(latencies) if latencies else 0,
            p50_latency=latencies_sorted[int(n * 0.5)] if n > 0 else 0,
            p95_latency=latencies_sorted[int(n * 0.95)] if n > 0 else 0,
            p99_latency=latencies_sorted[int(n * 0.99)] if n > 0 else 0,
        )

    def _print_results(self, result: TestResult, test_name: str):
        """打印测试结果"""
        print("\n" + "=" * 60)
        print(f"📊 {test_name}")
        print("=" * 60)
        print(f"总请求数:     {result.total_requests}")
        print(f"成功请求:     {result.success_count}")
        print(f"失败请求:     {result.failure_count}")
        print(f"成功率:       {result.success_rate:.2f}%")
        print(f"失败率:       {result.failure_rate:.2f}%")
        print("-" * 60)
        print(f"总耗时:       {result.total_time:.2f}s")
        print(f"QPS:          {result.qps:.2f} req/s")
        print("-" * 60)
        print(f"平均延迟:     {result.avg_latency*1000:.2f}ms")
        print(f"最小延迟:     {result.min_latency*1000:.2f}ms")
        print(f"最大延迟:     {result.max_latency*1000:.2f}ms")
        print(f"P50 延迟:     {result.p50_latency*1000:.2f}ms")
        print(f"P95 延迟:     {result.p95_latency*1000:.2f}ms")
        print(f"P99 延迟:     {result.p99_latency*1000:.2f}ms")
        print("=" * 60)

    # ==================== 测试场景 ====================

    async def test_stock_query(
        self,
        product_id: int = 1,
        warehouse_id: str = "WH01",
        concurrency: int = 100,
        total_requests: int = 1000
    ):
        """测试库存查询性能"""
        path = f"/api/v1/inventory/stock/{product_id}?warehouse_id={warehouse_id}"
        result = await self._run_concurrent_requests(
            method="GET",
            path=path,
            data=None,
            concurrency=concurrency,
            total_requests=total_requests
        )
        self._print_results(result, "库存查询测试")
        return result

    async def test_stock_reserve(
        self,
        product_id: int = 1,
        warehouse_id: str = "WH01",
        quantity: int = 1,
        order_prefix: str = "PERF_TEST",
        concurrency: int = 100,
        total_requests: int = 1000
    ):
        """测试库存预占性能"""
        # 每个请求使用不同的 order_id
        results = []

        async def reserve_request(session, idx):
            order_id = f"{order_prefix}_{idx}_{int(time.time()*1000)}"
            data = {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "quantity": quantity,
                "order_id": order_id
            }
            return await self._single_request(session, "POST", "/api/v1/inventory/reserve", data)

        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(concurrency)

            async def bounded_request(idx):
                async with semaphore:
                    return await reserve_request(session, idx)

            tasks = [bounded_request(i) for i in range(total_requests)]

            start_time = time.time()
            self.results = await asyncio.gather(*tasks)
            total_time = time.time() - start_time

        success_count = sum(1 for status, _ in self.results if 200 <= status < 300)
        failure_count = total_requests - success_count
        latencies = [latency for _, latency in self.results]

        result = self._calculate_results(
            total_requests, success_count, failure_count,
            total_time, latencies
        )
        self._print_results(result, "库存预占测试")
        return result

    async def test_stock_increase(
        self,
        product_id: int = 1,
        warehouse_id: str = "WH01",
        quantity: int = 10,
        concurrency: int = 100,
        total_requests: int = 1000
    ):
        """测试库存增加性能"""
        data = {
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "quantity": quantity,
            "operator": "perf_test"
        }
        result = await self._run_concurrent_requests(
            method="POST",
            path="/api/v1/inventory/increase",
            data=data,
            concurrency=concurrency,
            total_requests=total_requests
        )
        self._print_results(result, "库存增加测试")
        return result

    async def test_batch_reserve(
        self,
        items: List[Dict] = None,
        concurrency: int = 50,
        total_requests: int = 500
    ):
        """测试批量预占性能"""
        if items is None:
            items = [
                {"warehouse_id": "WH01", "product_id": 1, "quantity": 1},
                {"warehouse_id": "WH01", "product_id": 2, "quantity": 1},
            ]

        results = []

        async def batch_request(session, idx):
            order_id = f"BATCH_TEST_{idx}_{int(time.time()*1000)}"
            data = {
                "order_id": order_id,
                "items": items
            }
            return await self._single_request(session, "POST", "/api/v1/inventory/reserve-batch", data)

        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(concurrency)

            async def bounded_request(idx):
                async with semaphore:
                    return await batch_request(session, idx)

            tasks = [bounded_request(i) for i in range(total_requests)]

            start_time = time.time()
            self.results = await asyncio.gather(*tasks)
            total_time = time.time() - start_time

        success_count = sum(1 for status, _ in self.results if 200 <= status < 300)
        failure_count = total_requests - success_count
        latencies = [latency for _, latency in self.results]

        result = self._calculate_results(
            total_requests, success_count, failure_count,
            total_time, latencies
        )
        self._print_results(result, "批量预占测试")
        return result

    async def run_full_suite(
        self,
        concurrency: int = 100,
        total_requests: int = 1000
    ):
        """运行完整测试套件"""
        print("\n" + "🚀 " * 30)
        print("开始性能测试套件")
        print("并发数:", concurrency)
        print("总请求数:", total_requests)
        print("🚀 " * 30)

        # 1. 先增加库存（确保有足够库存）
        print("\n📦 准备测试数据...")
        await self.test_stock_increase(
            product_id=1,
            warehouse_id="WH01",
            quantity=100000,  # 预先增加大量库存
            concurrency=1,
            total_requests=1
        )

        # 2. 查询测试
        print("\n🔍 测试1: 库存查询")
        await self.test_stock_query(
            product_id=1,
            warehouse_id="WH01",
            concurrency=concurrency,
            total_requests=total_requests
        )

        # 3. 预占测试
        print("\n📝 测试2: 库存预占")
        await self.test_stock_reserve(
            product_id=1,
            warehouse_id="WH01",
            quantity=1,
            order_prefix="PERF_TEST",
            concurrency=concurrency,
            total_requests=total_requests
        )

        # 4. 批量预占测试
        print("\n📚 测试3: 批量预占")
        await self.test_batch_reserve(
            items=[
                {"warehouse_id": "WH01", "product_id": 1, "quantity": 1},
                {"warehouse_id": "WH01", "product_id": 2, "quantity": 1},
            ],
            concurrency=concurrency // 2,
            total_requests=total_requests // 2
        )

        print("\n" + "🎉 " * 30)
        print("测试完成!")
        print("🎉 " * 30)


# ==================== 主程序 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="库存微服务性能测试")
    parser.add_argument("--url", default="http://localhost:8000", help="服务基础 URL")
    parser.add_argument("--concurrency", type=int, default=100, help="并发数")
    parser.add_argument("--requests", type=int, default=1000, help="总请求数")
    parser.add_argument("--test", choices=["query", "reserve", "increase", "batch", "full"],
                       default="full", help="测试类型")

    args = parser.parse_args()

    tester = InventoryPerformanceTester(base_url=args.url)

    if args.test == "query":
        asyncio.run(tester.test_stock_query(concurrency=args.concurrency, total_requests=args.requests))
    elif args.test == "reserve":
        asyncio.run(tester.test_stock_reserve(concurrency=args.concurrency, total_requests=args.requests))
    elif args.test == "increase":
        asyncio.run(tester.test_stock_increase(concurrency=args.concurrency, total_requests=args.requests))
    elif args.test == "batch":
        asyncio.run(tester.test_batch_reserve(concurrency=args.concurrency, total_requests=args.requests))
    elif args.test == "full":
        asyncio.run(tester.run_full_suite(concurrency=args.concurrency, total_requests=args.requests))
