#!/usr/bin/env python3
"""
FastAPI Mall 应用综合测试脚本
用于验证应用的各项功能和健康状态
"""

import requests
import time
import json
import sys
from typing import Dict, Any

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

class AppTester:
    """应用测试器类"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []
    
    def log_result(self, test_name: str, success: bool, message: str = ""):
        """记录测试结果"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = f"{status} {test_name}"
        if message:
            result += f" - {message}"
        print(result)
        self.results.append({
            "test": test_name,
            "success": success,
            "message": message
        })
    
    def wait_for_service(self, max_wait: int = 30) -> bool:
        """等待服务启动"""
        print(f"⏳ 等待服务启动 (最多等待 {max_wait} 秒)...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = self.session.get(f"{self.base_url}/health", timeout=1)
                if response.status_code == 200:
                    print("✅ 服务已启动")
                    return True
            except:
                pass
            
            print(".", end="", flush=True)
            time.sleep(1)
        
        print("\n❌ 服务启动超时")
        return False
    
    def test_health_check(self) -> bool:
        """测试健康检查接口"""
        print("\n🔍 测试健康检查接口...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                self.log_result("健康检查", True, f"状态: {data.get('status')}")
                return True
            else:
                self.log_result("健康检查", False, f"状态码: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("健康检查", False, f"异常: {str(e)}")
            return False
    
    def test_root_endpoint(self) -> bool:
        """测试根路径接口"""
        print("\n🔍 测试根路径接口...")
        try:
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                data = response.json()
                self.log_result("根路径访问", True, data.get("message", ""))
                return True
            else:
                self.log_result("根路径访问", False, f"状态码: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("根路径访问", False, f"异常: {str(e)}")
            return False
    
    def test_api_docs(self) -> bool:
        """测试 API 文档访问"""
        print("\n🔍 测试 API 文档...")
        try:
            response = self.session.get(f"{self.base_url}/docs")
            if response.status_code == 200:
                self.log_result("API 文档访问", True)
                return True
            else:
                self.log_result("API 文档访问", False, f"状态码: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("API 文档访问", False, f"异常: {str(e)}")
            return False
    
    def test_openapi_schema(self) -> bool:
        """测试 OpenAPI Schema"""
        print("\n🔍 测试 OpenAPI Schema...")
        try:
            response = self.session.get(f"{self.base_url}/openapi.json")
            if response.status_code == 200:
                schema = response.json()
                title = schema.get("info", {}).get("title", "Unknown")
                version = schema.get("info", {}).get("version", "Unknown")
                self.log_result("OpenAPI Schema", True, f"{title} v{version}")
                return True
            else:
                self.log_result("OpenAPI Schema", False, f"状态码: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("OpenAPI Schema", False, f"异常: {str(e)}")
            return False
    
    def test_inventory_routes_exist(self) -> bool:
        """测试库存路由是否存在"""
        print("\n🔍 测试库存路由注册...")
        try:
            # 测试一个不存在的商品ID，应该返回404而不是405
            response = self.session.get(f"{self.base_url}{API_PREFIX}/inventory/stock/999999")
            
            if response.status_code in [200, 404, 500]:
                self.log_result("库存路由注册", True, f"状态码: {response.status_code}")
                return True
            elif response.status_code == 405:
                self.log_result("库存路由注册", False, "方法不被允许，路由可能未正确注册")
                return False
            else:
                self.log_result("库存路由注册", False, f"意外状态码: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("库存路由注册", False, f"异常: {str(e)}")
            return False
    
    def test_cors_headers(self) -> bool:
        """测试 CORS 头部"""
        print("\n🔍 测试 CORS 支持...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            cors_header = response.headers.get('access-control-allow-origin')
            if cors_header is not None:
                self.log_result("CORS 支持", True, f"Origin: {cors_header}")
                return True
            else:
                self.log_result("CORS 支持", False, "未找到 CORS 头部")
                return False
        except Exception as e:
            self.log_result("CORS 支持", False, f"异常: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("🚀 FastAPI Mall 应用综合测试开始")
        print("=" * 60)
        
        # 等待服务启动
        if not self.wait_for_service():
            print("❌ 服务未正常启动，测试终止")
            return {
                "success": False,
                "message": "服务启动失败",
                "results": self.results
            }
        
        # 执行各项测试
        tests = [
            self.test_health_check,
            self.test_root_endpoint,
            self.test_api_docs,
            self.test_openapi_schema,
            self.test_inventory_routes_exist,
            self.test_cors_headers
        ]
        
        passed = 0
        for test_func in tests:
            if test_func():
                passed += 1
            time.sleep(0.3)  # 避免请求过于频繁
        
        # 生成测试报告
        total = len(tests)
        success_rate = (passed / total) * 100 if total > 0 else 0
        
        print("\n" + "=" * 60)
        print(f"📊 测试结果汇总: {passed}/{total} 通过 ({success_rate:.1f}%)")
        
        if passed == total:
            print("🎉 所有测试通过！应用运行正常")
            status = "SUCCESS"
        elif passed >= total * 0.8:
            print("⚠️  大部分测试通过，应用基本可用")
            status = "PARTIAL_SUCCESS"
        else:
            print("❌ 多个测试失败，请检查应用状态")
            status = "FAILURE"
        
        print("\n📋 详细结果:")
        for result in self.results:
            icon = "✅" if result["success"] else "❌"
            print(f"  {icon} {result['test']}")
            if result["message"]:
                print(f"     {result['message']}")
        
        print("\n💡 访问信息:")
        print(f"   📚 API 文档: {self.base_url}/docs")
        print(f"   🏥 健康检查: {self.base_url}/health")
        print(f"   🏠 首页: {self.base_url}/")
        print(f"   📡 OpenAPI: {self.base_url}/openapi.json")
        
        return {
            "success": status in ["SUCCESS", "PARTIAL_SUCCESS"],
            "status": status,
            "passed": passed,
            "total": total,
            "success_rate": success_rate,
            "results": self.results
        }

def main():
    """主函数"""
    # 支持自定义基础URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    
    tester = AppTester(base_url)
    report = tester.run_all_tests()
    
    # 设置退出码
    sys.exit(0 if report["success"] else 1)

if __name__ == "__main__":
    main()