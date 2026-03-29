"""
Tornado 服务启动脚本（Windows/本地开发）
自动加载 .env.tornado 环境变量
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('.env.tornado')

print("🚀 启动 Tornado 高性能库存服务...")
print(f"   Redis: {os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}")
print(f"   端口：{os.getenv('PORT', 8001)}")
print()

# 导入并运行主程序
from tornado_server import main

if __name__ == "__main__":
    main()
