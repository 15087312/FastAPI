"""
库存微服务库 - Inventory Service Library
=====================================

专业的库存管理微服务库，支持高并发环境下的库存安全管理，防止超卖问题。

核心特性:
- 防超卖保障 - Redis Lua 脚本原子操作，Kafka 异步同步数据库
- 高性能缓存 - Redis 缓存层加速读取，支持批量操作
- 多层架构 - API / Celery / CLI 三种调用方式
- 完整审计 - 详细的操作日志和状态追踪
- 幂等保证 - 基于 Redis 的请求去重机制
- 优雅降级 - Redis 故障时自动降级到只读模式
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

# 读取 requirements.txt
requirements = []
req_file = this_directory / "requirements.txt"
if req_file.exists():
    with open(req_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                # 移除注释部分
                package = line.split("#")[0].strip()
                if package:
                    requirements.append(package)

setup(
    name="inventory-service",
    version="1.0.0",
    author="库存微服务团队",
    author_email="inventory@example.com",
    description="专业的库存管理微服务库，支持高并发环境下的库存安全管理",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/inventory-service",
    project_urls={
        "Documentation": "https://github.com/your-org/inventory-service/docs",
        "Bug Tracker": "https://github.com/your-org/inventory-service/issues",
    },
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Database :: Database Engines/Servers",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "pytest-cov>=4.0.0",
        ],
        "docker": [
            "docker>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "inventory-server=app.main:main",
            "inventory-init=app.init_data:init_cli",
        ],
    },
    include_package_data=True,
    package_data={
        "app.core": ["*.json"],
        "alembic": ["*.ini", "*.mako"],
    },
    license="MIT",
    keywords="inventory microservice fastapi redis kafka sqlalchemy celery",
)
