#!/usr/bin/env python3
"""
库存微服务库 - 打包和发布脚本

使用方法:
    python publish_library.py
    
步骤:
    1. 清理旧的构建文件
    2. 构建 wheel 包
    3. 上传到 PyPI (可选)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def clean_build():
    """清理构建文件"""
    print("🧹 清理构建文件...")
    
    dirs_to_remove = ["build", "dist", "*.egg-info", "__pycache__"]
    for dir_name in dirs_to_remove:
        for path in Path(".").rglob(dir_name):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"  已删除：{path}")
    
    # 清理 .pyc 文件
    for pyc_file in Path(".").rglob("*.pyc"):
        pyc_file.unlink()
    
    print("✅ 清理完成\n")


def build_package():
    """构建 Python 包"""
    print("📦 构建 package...")
    
    try:
        # 使用 build 模块（推荐）
        result = subprocess.run(
            [sys.executable, "-m", "build"],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        print("✅ 构建成功\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 构建失败：{e}")
        print(e.stderr)
        return False
    except FileNotFoundError:
        print("⚠️  未找到 build 模块，尝试使用 setup.py...")
        try:
            result = subprocess.run(
                [sys.executable, "setup.py", "sdist", "bdist_wheel"],
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
            print("✅ 构建成功\n")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 构建失败：{e}")
            return False


def upload_to_pypi(test=True):
    """上传到 PyPI
    
    Args:
        test: 如果为 True，上传到 TestPyPI；否则上传到正式 PyPI
    """
    print(f"🚀 上传到 {'TestPyPI' if test else 'PyPI'}...")
    
    repository = "testpypi" if test else "pypi"
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "twine", "upload", "--repository", repository, "dist/*"],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        print(f"✅ 上传成功到 {repository}\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 上传失败：{e}")
        print(e.stderr)
        return False
    except FileNotFoundError:
        print("❌ 未安装 twine，请先安装：pip install twine")
        return False


def install_locally():
    """本地安装测试"""
    print("🔧 本地安装测试...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        print("✅ 本地安装成功\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 本地安装失败：{e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("库存微服务库 - 打包和发布工具")
    print("=" * 60)
    print()
    
    # 1. 清理
    clean_build()
    
    # 2. 构建
    if not build_package():
        sys.exit(1)
    
    # 3. 本地安装测试
    if not install_locally():
        print("⚠️  本地安装失败，但继续执行")
    
    # 4. 询问是否上传
    print("\n" + "=" * 60)
    upload_choice = input("是否上传到 PyPI? (y/n): ").strip().lower()
    
    if upload_choice == 'y':
        test_choice = input("先上传到 TestPyPI 测试？(y/n): ").strip().lower()
        
        if test_choice == 'y':
            if upload_to_pypi(test=True):
                print("✅ TestPyPI 上传成功！")
                final_choice = input("是否上传到正式 PyPI? (y/n): ").strip().lower()
                if final_choice == 'y':
                    upload_to_pypi(test=False)
        else:
            upload_to_pypi(test=False)
    
    print("\n" + "=" * 60)
    print("🎉 所有操作完成！")
    print("=" * 60)
    
    # 显示生成的文件
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\n生成的文件:")
        for file in dist_dir.iterdir():
            size = file.stat().st_size / 1024  # KB
            print(f"  📄 {file.name} ({size:.1f} KB)")


if __name__ == "__main__":
    main()
