"""性能测试 API 路由器 - 为前端提供性能测试接口"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import asyncio
from datetime import datetime
import json
import os

from tests.api_perf_test import (
    PerformanceTestSuite,
    TestConfig,
    PerformanceMetrics,
    quick_test
)

router = APIRouter(prefix="/perf", tags=["性能测试"])

# 存储测试结果的目录
RESULTS_DIR = "test_results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# ==================== 请求模型 ====================

class SinglePerfTestRequest(BaseModel):
    """单个性能测试请求"""
    api_name: str = Field(..., description="API 名称")
    method: str = Field("GET", description="HTTP 方法")
    path: str = Field(..., description="API 路径")
    data: Optional[Dict] = Field(None, description="请求体数据")
    concurrency: int = Field(100, ge=1, le=10000, description="并发数")
    total_requests: int = Field(1000, ge=1, le=100000, description="总请求数")
    timeout: int = Field(30, ge=1, le=300, description="超时时间 (秒)")


class InventoryPerfTestRequest(BaseModel):
    """库存性能测试请求"""
    product_id: int = Field(1, ge=1, description="商品 ID")
    warehouse_id: str = Field("WH01", description="仓库 ID")
    concurrency: int = Field(100, ge=1, le=10000, description="并发数")
    total_requests: int = Field(1000, ge=1, le=100000, description="总请求数")


class StressTestRequest(BaseModel):
    """压力测试请求"""
    path: str = Field(..., description="API 路径")
    method: str = Field("GET", description="HTTP 方法")
    data: Optional[Dict] = Field(None, description="请求体数据")
    start_concurrency: int = Field(100, ge=1, le=5000, description="起始并发数")
    max_concurrency: int = Field(1000, ge=100, le=10000, description="最大并发数")
    step: int = Field(100, ge=10, le=500, description="递增步长")


class CustomTestRequest(BaseModel):
    """自定义测试请求"""
    tests: List[SinglePerfTestRequest] = Field(..., description="测试列表")


# ==================== 响应模型 ====================

class PerfTestResponse(BaseModel):
    """性能测试响应"""
    success: bool = True
    message: str = ""
    timestamp: str = ""
    test_name: str = ""
    metrics: Dict = {}


class InventoryPerfResponse(BaseModel):
    """库存性能测试响应"""
    success: bool = True
    message: str = ""
    timestamp: str = ""
    summary: Dict = {}
    tests: Dict[str, Dict] = {}


class StressTestResponse(BaseModel):
    """压力测试响应"""
    success: bool = True
    message: str = ""
    timestamp: str = ""
    test_type: str = "stress"
    results: List[Dict] = []


# ==================== API 端点 ====================

@router.get("/health", response_model=PerfTestResponse, summary="健康检查性能测试")
async def test_health(
    concurrency: int = Query(default=100, ge=1, le=10000, description="并发数"),
    requests: int = Query(default=1000, ge=1, le=100000, description="请求数")
):
    """
    测试健康检查接口的性能
    
    - **concurrency**: 并发请求数
    - **requests**: 总请求数
    
    返回 QPS、延迟、成功率等性能指标
    """
    try:
        result = await quick_test(
            url="http://localhost:8000",
            concurrency=concurrency,
            requests=requests
        )
        
        return PerfTestResponse(
            success=True,
            message="健康检查性能测试完成",
            timestamp=datetime.now().isoformat(),
            test_name="health_check",
            metrics=result.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.post("/single", response_model=PerfTestResponse, summary="单个 API 性能测试")
async def test_single_api(request: SinglePerfTestRequest):
    """
    测试单个 API 的性能
    
    可以指定任意 API 路径、方法和数据进行测试
    """
    try:
        suite = PerformanceTestSuite(base_url="http://localhost:8000")
        config = TestConfig(
            concurrency=request.concurrency,
            total_requests=request.total_requests,
            timeout=request.timeout
        )
        
        result = await suite.run_single_test(
            api_name=request.api_name,
            method=request.method,
            path=request.path,
            data=request.data,
            config=config
        )
        
        # 保存结果到文件
        result_data = {
            "test_name": request.api_name,
            "config": request.dict(),
            "metrics": result.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
        filename = f"{RESULTS_DIR}/single_{request.api_name}_{int(datetime.now().timestamp())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        return PerfTestResponse(
            success=True,
            message=f"{request.api_name} 性能测试完成",
            timestamp=datetime.now().isoformat(),
            test_name=request.api_name,
            metrics=result.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.post("/inventory", response_model=InventoryPerfResponse, summary="库存 API 性能测试套件")
async def test_inventory_apis(request: InventoryPerfTestRequest):
    """
    测试所有库存相关 API 的性能
    
    包括：查询、预占、确认、释放、增加等操作
    """
    try:
        suite = PerformanceTestSuite(base_url="http://localhost:8000")
        config = TestConfig(
            concurrency=request.concurrency,
            total_requests=request.total_requests
        )
        
        results = await suite.run_inventory_tests(
            product_id=request.product_id,
            warehouse_id=request.warehouse_id,
            config=config
        )
        
        report = suite.generate_report()
        
        # 保存完整报告
        filename = f"{RESULTS_DIR}/inventory_{int(datetime.now().timestamp())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return InventoryPerfResponse(
            success=True,
            message="库存 API 性能测试套件完成",
            timestamp=datetime.now().isoformat(),
            summary=report["summary"],
            tests=report["tests"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.post("/stress", response_model=StressTestResponse, summary="阶梯式压力测试")
async def test_stress(request: StressTestRequest):
    """
    阶梯式压力测试
    
    从低并发到高并发逐步增加，观察系统性能变化
    """
    try:
        suite = PerformanceTestSuite(base_url="http://localhost:8000")
        
        results = await suite.run_stress_test(
            path=request.path,
            method=request.method,
            data=request.data,
            max_concurrency=request.max_concurrency,
            step=request.step
        )
        
        # 保存结果
        report = {
            "test_type": "stress",
            "path": request.path,
            "method": request.method,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }
        
        filename = f"{RESULTS_DIR}/stress_{int(datetime.now().timestamp())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return StressTestResponse(
            success=True,
            message="阶梯压力测试完成",
            timestamp=datetime.now().isoformat(),
            test_type="stress",
            results=results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.post("/custom", response_model=InventoryPerfResponse, summary="自定义组合测试")
async def test_custom(request: CustomTestRequest):
    """
    自定义多个 API 的组合测试
    
    可以同时测试多个不同的 API
    """
    try:
        suite = PerformanceTestSuite(base_url="http://localhost:8000")
        
        for test_config in request.tests:
            config = TestConfig(
                concurrency=test_config.concurrency,
                total_requests=test_config.total_requests,
                timeout=test_config.timeout
            )
            
            await suite.run_single_test(
                api_name=test_config.api_name,
                method=test_config.method,
                path=test_config.path,
                data=test_config.data,
                config=config
            )
        
        report = suite.generate_report()
        
        # 保存结果
        filename = f"{RESULTS_DIR}/custom_{int(datetime.now().timestamp())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return InventoryPerfResponse(
            success=True,
            message=f"自定义测试完成，共执行 {len(request.tests)} 个测试",
            timestamp=datetime.now().isoformat(),
            summary=report["summary"],
            tests=report["tests"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.get("/results/{filename}", summary="获取测试结果")
async def get_test_result(filename: str):
    """获取历史测试结果"""
    filepath = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="测试结果不存在")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        result = json.load(f)
    
    return result


@router.get("/results", summary="获取所有测试结果列表")
async def list_test_results():
    """获取所有测试结果文件列表"""
    if not os.path.exists(RESULTS_DIR):
        return {"results": []}
    
    files = []
    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(RESULTS_DIR, filename)
            stat = os.stat(filepath)
            files.append({
                "filename": filename,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    
    # 按修改时间倒序
    files.sort(key=lambda x: x['modified_at'], reverse=True)
    
    return {"results": files[:100]}  # 最多返回 100 条


@router.delete("/results/{filename}", summary="删除测试结果")
async def delete_test_result(filename: str):
    """删除指定的测试结果"""
    filepath = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="测试结果不存在")
    
    os.remove(filepath)
    
    return {"success": True, "message": f"已删除 {filename}"}


@router.get("/metrics/summary", summary="获取性能指标说明")
async def get_metrics_description():
    """获取性能指标详细说明"""
    return {
        "metrics": {
            "total_requests": "总请求数",
            "success_count": "成功请求数",
            "failure_count": "失败请求数",
            "success_rate": "成功率 (%)",
            "failure_rate": "失败率 (%)",
            "total_time": "总耗时 (秒)",
            "qps": "每秒查询数 (Queries Per Second)",
            "tps": "每秒事务数 (Transactions Per Second)",
            "avg_latency_ms": "平均延迟 (毫秒)",
            "min_latency_ms": "最小延迟 (毫秒)",
            "max_latency_ms": "最大延迟 (毫秒)",
            "p50_latency_ms": "P50 延迟 - 50% 请求的延迟低于此值 (毫秒)",
            "p75_latency_ms": "P75 延迟 - 75% 请求的延迟低于此值 (毫秒)",
            "p90_latency_ms": "P90 延迟 - 90% 请求的延迟低于此值 (毫秒)",
            "p95_latency_ms": "P95 延迟 - 95% 请求的延迟低于此值 (毫秒)",
            "p99_latency_ms": "P99 延迟 - 99% 请求的延迟低于此值 (毫秒)",
            "error_types": "错误类型统计"
        },
        "performance_standards": {
            "excellent": {
                "qps": "> 1000",
                "p95_latency_ms": "< 100ms",
                "success_rate": "> 99.9%"
            },
            "good": {
                "qps": "500 - 1000",
                "p95_latency_ms": "100 - 500ms",
                "success_rate": "99% - 99.9%"
            },
            "acceptable": {
                "qps": "100 - 500",
                "p95_latency_ms": "500ms - 1s",
                "success_rate": "95% - 99%"
            },
            "poor": {
                "qps": "< 100",
                "p95_latency_ms": "> 1s",
                "success_rate": "< 95%"
            }
        }
    }
