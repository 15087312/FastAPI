#!/usr/bin/env python3
"""
Redis 库存查询与扣减测试 - 最精简版

功能：
1. 查询商品 980 的库存
2. 扣减 1 个库存
3. 打印每个步骤的耗时
"""

import time
from app.core.redis import redis_client
from app.db.session import SessionLocal
from app.models.product_stocks import ProductStock
from sqlalchemy import select


def main():
    print("="*80)
    print("🔍 Redis 库存查询与扣减测试")
    print("="*80)
    
    warehouse_id = "WH001"
    product_id = 980
    
    # ========== 步骤 1: 查询数据库库存 ==========
    print(f"\n📊 步骤 1: 查询数据库库存")
    start = time.time()
    
    db = SessionLocal()
    stock = db.execute(
        select(ProductStock).where(
            ProductStock.warehouse_id == warehouse_id,
            ProductStock.product_id == product_id
        )
    ).scalar_one_or_none()
    
    db_elapsed = (time.time() - start) * 1000
    
    if stock:
        print(f"   ✅ 数据库库存：{stock.available_stock}")
        print(f"   ⏱️  耗时：{db_elapsed:.2f}ms")
    else:
        print(f"   ❌ 未找到库存记录")
        db.close()
        return
    
    db.close()
    
    # ========== 步骤 2: 查询 Redis 库存 ==========
    print(f"\n📊 步骤 2: 查询 Redis 库存")
    start = time.time()
    
    redis_key = f"stock:available:{warehouse_id}:{product_id}"
    redis_stock = redis_client.get(redis_key)
    
    redis_elapsed = (time.time() - start) * 1000
    
    print(f"   Redis Key: {redis_key}")
    if redis_stock:
        print(f"   ✅ Redis 库存：{redis_stock}")
    else:
        print(f"   ⚠️  Redis 中无数据")
    print(f"   ⏱️  耗时：{redis_elapsed:.2f}ms")
    
    # ========== 步骤 3: Redis 扣减库存 ==========
    print(f"\n📊 步骤 3: Redis 扣减库存 (减 1)")
    start = time.time()
    
    if redis_stock:
        new_stock = int(redis_stock) - 1
    else:
        new_stock = stock.available_stock - 1
    
    redis_client.set(redis_key, new_stock)
    
    write_elapsed = (time.time() - start) * 1000
    
    # 验证写入结果
    verify_stock = redis_client.get(redis_key)
    
    print(f"   扣减前：{redis_stock or stock.available_stock}")
    print(f"   扣减后：{verify_stock}")
    print(f"   ⏱️  耗时：{write_elapsed:.2f}ms")
    
    # ========== 性能对比 ==========
    print(f"\n{'='*80}")
    print("⏱️  性能统计")
    print(f"{'='*80}")
    print(f"   数据库查询：{db_elapsed:.2f}ms")
    print(f"   Redis 查询：{redis_elapsed:.2f}ms")
    print(f"   Redis 写入：{write_elapsed:.2f}ms")
    print(f"\n   🚀 Redis 查询比数据库快：{db_elapsed / redis_elapsed:.2f}x" if redis_elapsed > 0 else "")
    print(f"   🚀 Redis 写入比数据库快：{db_elapsed / write_elapsed:.2f}x" if write_elapsed > 0 else "")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
