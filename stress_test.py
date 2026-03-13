#!/usr/bin/env python3
"""
库存服务超级压力性能测试脚本

功能：
1. 多轮次递增压力测试（从 10 并发到 1000 并发）
2. 混合场景测试（查询 + 预占 + 确认 + 释放）
3. 极限压力测试（持续高并发直到系统崩溃）
4. 健康检查监控（实时监控服务健康状态）
5. 自动降级检测（检测到服务不可用时自动停止）

使用方式：
    python stress_test.py
    
注意：
- 确保服务已启动并运行在 http://localhost:8000
- 测试前请确保有足够的测试数据
- 极限测试可能导致服务崩溃，请谨慎使用
"""

import asyncio
import aiohttp
import time
import statistics
import json
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import psutil


@dataclass
class TestResult:
    """测试结果数据结构"""
    test_name: str
    concurrency: int
    total_requests: int
    success_count: int
    fail_count: int
    success_rate: float
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p50_response_time_ms: float
    p90_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    qps: float
    duration_seconds: float
    timestamp: str


@dataclass
class StressTestReport:
    """压力测试报告"""
    start_time: str
    end_time: str
    total_duration_seconds: float
    test_scenarios: List[TestResult]
    max_concurrency_tested: int
    system_limit_reached: bool
    failure_point: Optional[int]


class InventoryStressTester:
    """库存服务压力测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_data = {
            "warehouse_id": "WH01",
            "product_id": 1,
            "quantity": 1,
            "order_id_prefix": "STRESS_TEST"
        }
        self.health_check_interval = 1.0  # 秒
        self.last_health_status = {}
        self.should_stop = False
        
    async def init_session(self):
        """初始化 HTTP 会话"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
    async def close_session(self):
        """关闭 HTTP 会话"""
        if self.session:
            await self.session.close()
            
    async def health_check(self) -> Dict:
        """健康检查"""
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    self.last_health_status = data
                    return data
                else:
                    return {"status": "unhealthy", "error": f"Status code: {response.status}"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def query_stock(self, product_id: int) -> Tuple[bool, float]:
        """查询库存"""
        start_time = time.time()
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/inventory/stock/{product_id}"
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                return response.status == 200, elapsed
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed
    
    async def reserve_stock(self, order_id: str) -> Tuple[bool, float]:
        """预占库存"""
        start_time = time.time()
        try:
            # 使用查询参数而不是 JSON body
            params = {
                "warehouse_id": self.test_data["warehouse_id"],
                "product_id": self.test_data["product_id"],
                "quantity": self.test_data["quantity"],
                "order_id": order_id
            }
            async with self.session.post(
                f"{self.base_url}/api/v1/inventory/reserve",
                params=params
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                return response.status in [200, 201], elapsed
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed
    
    async def confirm_stock(self, order_id: str) -> Tuple[bool, float]:
        """确认库存"""
        start_time = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/inventory/confirm/{order_id}"
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                return response.status in [200, 201], elapsed
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed
    
    async def release_stock(self, order_id: str) -> Tuple[bool, float]:
        """释放库存"""
        start_time = time.time()
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/inventory/release/{order_id}"
            ) as response:
                elapsed = (time.time() - start_time) * 1000
                return response.status in [200, 201], elapsed
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return False, elapsed
    
    async def mixed_scenario(self, order_id: str) -> Tuple[bool, float]:
        """混合场景：查询 -> 预占 -> 确认 -> 释放"""
        start_time = time.time()
        try:
            # 1. 查询库存
            success, _ = await self.query_stock(self.test_data["product_id"])
            if not success:
                elapsed = (time.time() - start_time) * 1000
                return False, elapsed
            
            # 2. 预占库存
            success, _ = await self.reserve_stock(order_id)
            if not success:
                # print(f"预占失败：{order_id}")  # 调试信息
                elapsed = (time.time() - start_time) * 1000
                return False, elapsed
            
            # 3. 确认库存
            success, _ = await self.confirm_stock(order_id)
            if not success:
                # print(f"确认失败：{order_id}")  # 调试信息
                elapsed = (time.time() - start_time) * 1000
                return False, elapsed
            
            # 4. 释放库存（模拟退货）
            success, _ = await self.release_stock(order_id)
            elapsed = (time.time() - start_time) * 1000
            return success, elapsed
            
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            # print(f"混合场景异常：{e}")  # 调试信息
            return False, elapsed
    
    async def run_concurrent_test(
        self,
        concurrency: int,
        requests_per_worker: int,
        scenario: str = "mixed"
    ) -> TestResult:
        """运行并发测试"""
        
        async def worker(worker_id: int):
            """工作线程"""
            results = []
            for i in range(requests_per_worker):
                if self.should_stop:
                    break
                    
                order_id = f"{self.test_data['order_id_prefix']}_{worker_id}_{i}_{int(time.time())}"
                
                if scenario == "query":
                    success, elapsed = await self.query_stock(self.test_data["product_id"])
                elif scenario == "reserve":
                    success, elapsed = await self.reserve_stock(order_id)
                elif scenario == "confirm":
                    success, elapsed = await self.confirm_stock(order_id)
                elif scenario == "release":
                    success, elapsed = await self.release_stock(order_id)
                else:  # mixed
                    success, elapsed = await self.mixed_scenario(order_id)
                
                results.append((success, elapsed))
                
                # 短暂延迟，防止过快
                if scenario != "query":
                    await asyncio.sleep(0.01)
            
            return results
        
        # 启动所有工作线程
        workers = [asyncio.create_task(worker(i)) for i in range(concurrency)]
        
        # 等待所有任务完成
        all_results = []
        start_time = time.time()
        
        for worker_task in workers:
            worker_results = await worker_task
            all_results.extend(worker_results)
        
        duration = time.time() - start_time
        
        # 统计结果
        total_requests = len(all_results)
        success_count = sum(1 for success, _ in all_results if success)
        fail_count = total_requests - success_count
        success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0
        
        response_times = [elapsed for _, elapsed in all_results if elapsed > 0]
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p50 = statistics.median(response_times)
            p90 = sorted(response_times)[int(len(response_times) * 0.9)] if len(response_times) > 1 else max_response_time
            p95 = sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) > 1 else max_response_time
            p99 = sorted(response_times)[int(len(response_times) * 0.99)] if len(response_times) > 1 else max_response_time
        else:
            avg_response_time = min_response_time = p50 = p90 = p95 = p99 = 0
            max_response_time = 0
        
        qps = total_requests / duration if duration > 0 else 0
        
        return TestResult(
            test_name=f"stress_test_concurrency_{concurrency}",
            concurrency=concurrency,
            total_requests=total_requests,
            success_count=success_count,
            fail_count=fail_count,
            success_rate=round(success_rate, 2),
            avg_response_time_ms=round(avg_response_time, 2),
            min_response_time_ms=round(min_response_time, 2),
            max_response_time_ms=round(max_response_time, 2),
            p50_response_time_ms=round(p50, 2),
            p90_response_time_ms=round(p90, 2),
            p95_response_time_ms=round(p95, 2),
            p99_response_time_ms=round(p99, 2),
            qps=round(qps, 2),
            duration_seconds=round(duration, 2),
            timestamp=datetime.now().isoformat()
        )
    
    async def monitor_health_during_test(self, duration: float):
        """测试期间监控健康状态"""
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.should_stop:
                break
                
            health = await self.health_check()
            status = health.get("status", "unknown")
            
            if status == "unhealthy":
                print(f"\n❌ 检测到服务不健康：{health}")
                self.should_stop = True
                break
            
            await asyncio.sleep(self.health_check_interval)
    
    async def run_stress_test_suite(self):
        """运行完整的压力测试套件"""
        print("=" * 80)
        print("🚀 库存服务超级压力测试".center(80))
        print("=" * 80)
        
        await self.init_session()
        
        # 初始健康检查
        print("\n📊 初始健康检查...")
        health = await self.health_check()
        print(f"   健康状态：{health.get('status', 'unknown')}")
        if health.get('status') != 'healthy':
            print(f"   ❌ 服务不健康，无法开始测试：{health}")
            await self.close_session()
            return
        
        print(f"   ✓ 服务健康，可以开始测试")
        
        # 测试场景配置
        test_configs = [
            # (并发数，每 worker 请求数，场景)
            (10, 50, "mixed"),      # 低并发
            (50, 100, "mixed"),     # 中并发
            (100, 200, "mixed"),    # 高并发
            (200, 300, "mixed"),    # 超高并发
            (500, 500, "mixed"),    # 极限并发
            (1000, 1000, "mixed"),  # 疯狂并发
        ]
        
        all_results = []
        max_concurrency = 0
        failure_point = None
        system_limit_reached = False
        
        start_time = datetime.now()
        
        for concurrency, requests_per_worker, scenario in test_configs:
            print(f"\n{'='*80}")
            print(f"📈 开始测试：并发={concurrency}, 场景={scenario}")
            print(f"{'='*80}")
            
            # 启动健康监控
            monitor_task = asyncio.create_task(
                self.monitor_health_during_test(60)  # 监控 60 秒
            )
            
            # 运行测试
            result = await self.run_concurrent_test(concurrency, requests_per_worker, scenario)
            
            # 停止监控
            self.should_stop = False
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            all_results.append(result)
            max_concurrency = max(max_concurrency, concurrency)
            
            # 打印结果
            self.print_test_result(result)
            
            # 检查是否达到系统极限
            if result.success_rate < 90:
                print(f"\n⚠️  检测到系统性能下降！成功率：{result.success_rate}%")
                if failure_point is None:
                    failure_point = concurrency
                
                if result.success_rate < 50:
                    print(f"🛑 系统已达到极限，停止测试")
                    system_limit_reached = True
                    break
            
            # 检查健康状态
            health = await self.health_check()
            if health.get('status') != 'healthy':
                print(f"\n❌ 服务已崩溃，停止测试")
                failure_point = concurrency
                system_limit_reached = True
                break
            
            # 短暂休息，让系统恢复
            print(f"\n💤 休息 5 秒，让系统恢复...")
            await asyncio.sleep(5)
        
        end_time = datetime.now()
        
        # 生成报告
        report = StressTestReport(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            total_duration_seconds=(end_time - start_time).total_seconds(),
            test_scenarios=all_results,
            max_concurrency_tested=max_concurrency,
            system_limit_reached=system_limit_reached,
            failure_point=failure_point
        )
        
        # 打印最终报告
        self.print_final_report(report)
        
        await self.close_session()
        
        return report
    
    def print_test_result(self, result: TestResult):
        """打印单个测试结果"""
        print(f"\n📊 测试结果:")
        print(f"   并发数：{result.concurrency}")
        print(f"   总请求数：{result.total_requests}")
        print(f"   成功：{result.success_count}, 失败：{result.fail_count}")
        print(f"   成功率：{result.success_rate}%")
        print(f"   QPS: {result.qps}")
        print(f"   响应时间 (ms):")
        print(f"      平均：{result.avg_response_time_ms:.2f}")
        print(f"      最小：{result.min_response_time_ms:.2f}")
        print(f"      最大：{result.max_response_time_ms:.2f}")
        print(f"      P50: {result.p50_response_time_ms:.2f}")
        print(f"      P90: {result.p90_response_time_ms:.2f}")
        print(f"      P95: {result.p95_response_time_ms:.2f}")
        print(f"      P99: {result.p99_response_time_ms:.2f}")
        print(f"   持续时间：{result.duration_seconds:.2f}秒")
    
    def print_final_report(self, report: StressTestReport):
        """打印最终报告"""
        print(f"\n{'='*80}")
        print("📋 压力测试最终报告".center(80))
        print(f"{'='*80}")
        print(f"   开始时间：{report.start_time}")
        print(f"   结束时间：{report.end_time}")
        print(f"   总持续时间：{report.total_duration_seconds:.2f}秒")
        print(f"   最大并发数：{report.max_concurrency_tested}")
        print(f"   系统极限：{'是' if report.system_limit_reached else '否'}")
        if report.failure_point:
            print(f"   失败临界点：并发={report.failure_point}")
        
        print(f"\n📊 各场景详细结果:")
        for result in report.test_scenarios:
            print(f"\n   --- 并发 {result.concurrency} ---")
            print(f"      成功率：{result.success_rate}%")
            print(f"      QPS: {result.qps}")
            print(f"      P99 响应时间：{result.p99_response_time_ms:.2f}ms")
        
        print(f"\n{'='*80}")
        if report.system_limit_reached:
            print("⚠️  测试结论：系统已达到性能极限")
        else:
            print("✓ 测试结论：系统表现良好，未达到极限")
        print(f"{'='*80}")


async def main():
    """主函数"""
    tester = InventoryStressTester("http://localhost:8000")
    
    try:
        await tester.run_stress_test_suite()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试异常：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
