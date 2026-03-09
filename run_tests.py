#!/usr/bin/env python3
"""
单元测试运行脚本
提供多种测试运行选项
"""

import subprocess
import sys
import argparse


def run_tests(test_pattern=None, verbose=False, coverage=False, parallel=False):
    """运行单元测试
    
    Args:
        test_pattern: 测试文件或函数模式 (如 test_*.py 或 ::test_function)
        verbose: 是否显示详细输出
        coverage: 是否生成覆盖率报告
        parallel: 是否并行执行测试
    """
    cmd = ["python", "-m", "pytest"]
    
    # 基础参数
    if verbose:
        cmd.append("-v")
    else:
        # 使用标准输出格式（介于 -v 和 -q 之间）
        cmd.extend(["--tb=short"])

    # 并行执行选项
    if parallel:
        cmd.extend(["-n", "auto"])  # 使用 pytest-xdist 自动并行
    
    # 如果指定了测试模式
    if test_pattern:
        cmd.append(test_pattern)
    else:
        cmd.append("tests/")
    
    # 覆盖率选项
    if coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing"
        ])
    
    print(f"Running command: {' '.join(cmd)}")
    print("=" * 50)
        
    try:
        result = subprocess.run(cmd, check=True)
        print("\nTests completed successfully")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\nTests failed with exit code: {e.returncode}")
        return False


def run_specific_test(test_name):
    """运行特定测试"""
    print(f"Running test: {test_name}")
    return run_tests(test_name, verbose=True)


def main():
    parser = argparse.ArgumentParser(
        description="库存微服务单元测试运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python run_tests.py --all                    # 运行所有测试
  python run_tests.py --service --verbose      # 运行服务测试 (详细输出)
  python run_tests.py --integration --coverage # 运行集成测试并生成覆盖率
  python run_tests.py test_reserve_stock_success  # 运行特定测试函数
  python run_tests.py --parallel --all         # 并行运行所有测试
        """
    )
    
    # 测试范围选项
    scope_group = parser.add_argument_group('测试范围')
    scope_group.add_argument(
        "--all", 
        action="store_true",
        help="运行所有测试"
    )
    scope_group.add_argument(
        "--service",
        action="store_true",
        help="只运行库存服务测试"
    )
    scope_group.add_argument(
        "--router",
        action="store_true",
        help="只运行路由测试"
    )
    scope_group.add_argument(
        "--models",
        action="store_true",
        help="只运行模型测试"
    )
    scope_group.add_argument(
        "--deps",
        action="store_true",
        help="只运行依赖注入测试"
    )
    scope_group.add_argument(
        "--tasks",
        action="store_true",
        help="只运行 Celery 任务测试"
    )
    scope_group.add_argument(
        "--integration",
        action="store_true",
        help="只运行集成测试 (test_app.py)"
    )
    
    # 功能选项
    feature_group = parser.add_argument_group('功能选项')
    feature_group.add_argument(
        "--openapi",
        action="store_true",
        help="运行 OpenAPI 相关测试"
    )
    feature_group.add_argument(
        "--coverage",
        action="store_true",
        help="生成覆盖率报告"
    )
    feature_group.add_argument(
        "--parallel",
        action="store_true",
        help="并行执行测试 (需要 pytest-xdist)"
    )
    feature_group.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出模式"
    )
    
    # 位置参数
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
    
    # 根据选项运行不同测试集（互斥选择）
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
        pattern = "tests/test_app.py::AppTester::test_pydantic_schemas tests/test_app.py::AppTester::test_openapi_documentation"
    elif args.all:
        pattern = None  # 运行所有测试
    else:
        # 默认运行所有测试
        pattern = None
    
    success = run_tests(pattern, args.verbose, args.coverage, args.parallel)
        
    if args.coverage and success:
        print("\nCoverage report generated to htmlcov/ directory")
        print("View report: open htmlcov/index.html or start htmlcov\\index.html")
        
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
