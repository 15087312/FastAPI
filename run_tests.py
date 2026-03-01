#!/usr/bin/env python3
"""
单元测试运行脚本
提供多种测试运行选项
"""

import subprocess
import sys
import argparse
import os


def run_tests(test_pattern=None, verbose=False, coverage=False):
    """运行单元测试
    
    Args:
        test_pattern: 测试文件或函数模式 (如 test_*.py 或 ::test_function)
        verbose: 是否显示详细输出
        coverage: 是否生成覆盖率报告
    """
    cmd = ["python", "-m", "pytest"]
    
    # 基础参数
    cmd.extend([
        "tests/",
        "-v" if verbose else "-q",
        "--tb=short",  # 简洁的 traceback
        "--disable-warnings",  # 禁用警告
    ])
    
    # 如果指定了测试模式
    if test_pattern:
        cmd.append(test_pattern)
    
    # 覆盖率选项
    if coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing"
        ])
    
    print(f"🚀 运行命令: {' '.join(cmd)}")
    print("=" * 50)
    
    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ 测试运行完成")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 测试失败，退出码: {e.returncode}")
        return False


def run_specific_test(test_name):
    """运行特定测试"""
    print(f"🔍 运行测试: {test_name}")
    return run_tests(test_name, verbose=True)


def main():
    parser = argparse.ArgumentParser(description="库存微服务单元测试运行器")
    parser.add_argument(
        "--all", 
        action="store_true",
        help="运行所有测试"
    )
    parser.add_argument(
        "--service",
        action="store_true",
        help="只运行库存服务测试"
    )
    parser.add_argument(
        "--router",
        action="store_true",
        help="只运行路由测试"
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="只运行模型测试"
    )
    parser.add_argument(
        "--deps",
        action="store_true",
        help="只运行依赖注入测试"
    )
    parser.add_argument(
        "--tasks",
        action="store_true",
        help="只运行 Celery 任务测试"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="只运行集成测试"
    )
    parser.add_argument(
        "--openapi",
        action="store_true",
        help="运行 OpenAPI 相关测试"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="生成覆盖率报告"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出模式"
    )
    parser.add_argument(
        "test_name",
        nargs="?",
        help="特定测试函数名 (如 test_reserve_stock_success)"
    )
    
    args = parser.parse_args()
    
    # 如果提供了特定测试名
    if args.test_name:
        if "::" not in args.test_name:
            # 自动添加测试类前缀
            test_name = f"tests/*::{args.test_name}"
        else:
            test_name = f"tests/{args.test_name}"
        return run_specific_test(test_name)
    
    # 根据选项运行不同测试集
    if args.service:
        pattern = "tests/test_inventory_service.py"
    elif args.router:
        pattern = "tests/test_inventory_router.py"
    elif args.models:
        pattern = "tests/test_models.py"
    elif args.deps:
        pattern = "tests/test_dependencies.py"
    elif args.tasks:
        pattern = "tests/test_celery_tasks.py"
    elif args.integration:
        pattern = "tests/test_app.py"
    elif args.openapi:
        pattern = "tests/test_app.py::AppTester::test_pydantic_schemas or tests/test_app.py::AppTester::test_openapi_documentation"
    else:
        pattern = None  # 运行所有测试
    
    success = run_tests(pattern, args.verbose, args.coverage)
    
    if args.coverage and success:
        print("\n📊 覆盖率报告已生成到 htmlcov/ 目录")
        print("📁 查看报告: open htmlcov/index.html")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
