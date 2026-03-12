# 服务层 AOP 切面使用指南

## 概述

为了解决代码重复问题，我们引入了统一的 AOP（面向切面编程）模块 `app/core/aspects.py`，提供：
- ✅ 性能监控
- ✅ 日志记录
- ✅ 异常处理
- ✅ 缓存失效
- ✅ 事务管理

所有 Service 层现在都使用统一的切面处理，消除了重复代码。

---

## 核心组件

### 1. 装饰器

#### `@performance_monitor`
性能监控装饰器，自动记录函数执行时间。

```python
from app.core.aspects import performance_monitor

class MyService:
    @performance_monitor
    def do_something(self, param1, param2):
        # 业务逻辑
        pass
```

**特性：**
- 自动记录执行耗时
- 超过阈值自动告警（WARNING/CRITICAL）
- 异常时记录错误和耗时

---

#### `@log_operation(operation_name)`
操作日志记录装饰器。

```python
from app.core.aspects import log_operation

class MyService:
    @log_operation("创建订单")
    def create_order(self, order_data):
        # 业务逻辑
        pass
```

---

#### `@handle_exception(default_return=None, reraise=True)`
异常处理装饰器。

```python
from app.core.aspects import handle_exception

class MyService:
    @handle_exception(default_return={"error": "操作失败"}, reraise=False)
    def risky_operation(self):
        # 可能抛出异常的逻辑
        pass
```

---

### 2. 切面类

#### `CacheInvalidationAspect` - 缓存失效切面

统一管理缓存失效逻辑，避免每个 service 重复实现 `_invalidate_cache` 方法。

```python
from app.core.aspects import CacheInvalidationAspect

class InventoryService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_service = cache_service
        # 初始化缓存失效切面
        self.cache_aspect = CacheInvalidationAspect(cache_service)
    
    def update_stock(self, warehouse_id, product_id, quantity):
        # 业务逻辑
        # ...
        
        # 使用统一的缓存失效切面
        self.cache_aspect.invalidate_single(warehouse_id, product_id)
    
    def batch_update(self, items):
        # 批量操作
        # ...
        
        # 批量失效缓存
        self.cache_aspect.invalidate_batch(items)
    
    def process_reservations(self, reservations):
        # 处理预占记录
        # ...
        
        # 根据预占记录失效缓存
        self.cache_aspect.invalidate_by_order(reservations)
```

**方法：**
- `invalidate_single(warehouse_id, product_id)` - 失效单个商品缓存
- `invalidate_batch(items)` - 批量失效缓存
- `invalidate_by_order(reservations)` - 根据预占记录失效缓存

---

#### `TransactionAspect` - 事务管理切面

统一管理数据库事务的提交和回滚。

```python
from app.core.aspects import TransactionAspect

class OrderService:
    def __init__(self, db):
        self.db = db
        self.tx_aspect = TransactionAspect(db)
    
    def create_order_with_items(self, order_data, items):
        def operation():
            # 创建订单
            order = self._create_order(order_data)
            
            # 创建订单项
            for item in items:
                self._create_order_item(order.id, item)
            
            return order
        
        def on_success():
            # 成功后回调（在 commit 之前）
            logger.info(f"订单创建成功：{order_data['id']}")
        
        # 使用事务包装
        return self.tx_aspect.execute_with_transaction(operation, on_success)
```

---

#### `LoggingAspect` - 日志记录切面

提供统一的日志记录模式。

```python
from app.core.aspects import LoggingAspect
import time

class ProductService:
    def update_product(self, product_id, data):
        start_time = time.time()
        
        try:
            LoggingAspect.log_operation_start("update_product", {"product_id": product_id})
            
            # 业务逻辑
            result = self._do_update(product_id, data)
            
            elapsed_ms = (time.time() - start_time) * 1000
            LoggingAspect.log_operation_success(
                "update_product",
                duration_ms=elapsed_ms,
                extra_data={"result": result}
            )
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            LoggingAspect.log_operation_failure("update_product", e, elapsed_ms)
            raise
```

---

## 重构前后对比

### ❌ 重构前 - 重复代码

每个 Service 都自己实现缓存失效和日志记录：

```python
# inventory_reservation.py
class InventoryReservationService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_service = cache_service
    
    def _invalidate_cache(self, warehouse_id, product_id):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)
    
    def reserve_stock(self, warehouse_id, product_id, quantity, order_id):
        # ... 业务逻辑 ...
        
        self.db.commit()
        logger.info(f"预占库存成功：order_id={order_id}")
        
        # 手动循环失效缓存
        self._invalidate_cache(warehouse_id, product_id)
```

```python
# inventory_operation.py
class InventoryOperationService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_service = cache_service
    
    def _invalidate_cache(self, warehouse_id, product_id):
        """失效缓存"""
        if self.cache_service:
            self.cache_service.invalidate_cache(warehouse_id, product_id)
    
    def increase_stock(self, warehouse_id, product_id, quantity):
        # ... 业务逻辑 ...
        
        self.db.commit()
        logger.info(f"入库成功：warehouse={warehouse_id}")
        
        self._invalidate_cache(warehouse_id, product_id)
```

**问题：**
- ❌ 每个 Service 都重复实现 `_invalidate_cache` 方法
- ❌ 日志记录模式重复
- ❌ 没有统一的异常处理
- ❌ 难以维护和修改

---

### ✅ 重构后 - 统一切面

使用统一的 AOP 切面：

```python
# inventory_reservation.py
from app.core.aspects import (
    performance_monitor,
    CacheInvalidationAspect,
    LoggingAspect
)

class InventoryReservationService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_service = cache_service
        # 使用统一的缓存失效切面
        self.cache_aspect = CacheInvalidationAspect(cache_service)
    
    def _invalidate_cache(self, warehouse_id, product_id):
        """失效缓存（使用统一切面）"""
        self.cache_aspect.invalidate_single(warehouse_id, product_id)
    
    @performance_monitor
    def reserve_stock(self, warehouse_id, product_id, quantity, order_id):
        # ... 业务逻辑 ...
        
        self.db.commit()
        LoggingAspect.log_operation_success(
            "reserve_stock",
            duration_ms=elapsed_ms,
            extra_data={'order_id': order_id}
        )
        
        # 使用统一的缓存失效切面
        self.cache_aspect.invalidate_single(warehouse_id, product_id)
```

```python
# inventory_operation.py
from app.core.aspects import CacheInvalidationAspect, LoggingAspect

class InventoryOperationService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_service = cache_service
        # 使用统一的缓存失效切面
        self.cache_aspect = CacheInvalidationAspect(cache_service)
    
    def increase_stock(self, warehouse_id, product_id, quantity):
        # ... 业务逻辑 ...
        
        self.db.commit()
        LoggingAspect.log_operation_success(
            "increase_stock",
            extra_data={'warehouse_id': warehouse_id}
        )
        
        self.cache_aspect.invalidate_single(warehouse_id, product_id)
```

**优势：**
- ✅ 消除重复代码
- ✅ 统一的日志格式
- ✅ 统一的缓存失效逻辑
- ✅ 易于维护和扩展
- ✅ 性能监控自动化

---

## 最佳实践

### 1. 优先使用装饰器

对于简单的场景，直接使用装饰器：

```python
class UserService:
    @performance_monitor
    @log_operation("创建用户")
    def create_user(self, user_data):
        # 业务逻辑
        pass
```

### 2. 组合使用切面类

对于复杂场景，组合使用多个切面类：

```python
class OrderService:
    def __init__(self, db, cache_service):
        self.db = db
        self.cache_aspect = CacheInvalidationAspect(cache_service)
        self.tx_aspect = TransactionAspect(db)
    
    def process_order(self, order_data):
        def operation():
            # 业务逻辑
            pass
        
        def on_success():
            # 成功后清理缓存
            self.cache_aspect.invalidate_batch(order_data['items'])
        
        return self.tx_aspect.execute_with_transaction(operation, on_success)
```

### 3. 保持切面的纯粹性

切面应该只关注横切关注点，不应该包含业务逻辑：

```python
# ✅ 好的做法
@performance_monitor
def calculate_price(order):
    # 纯业务逻辑
    pass

# ❌ 不好的做法
@performance_monitor
def calculate_price(order):
    # 混合了日志、缓存等业务逻辑
    cache.set(...)
    logger.info(...)
```

---

## 配置

性能监控阈值可以在 `app/core/aspects.py` 中配置：

```python
PERFORMANCE_THRESHOLD_WARNING = 50    # 警告阈值（毫秒）
PERFORMANCE_THRESHOLD_CRITICAL = 100  # 严重阈值（毫秒）
```

---

## 总结

通过引入 AOP 切面，我们实现了：
- ✅ **代码复用**：消除了 Service 层的重复代码
- ✅ **统一标准**：所有 Service 使用相同的日志、缓存、事务处理模式
- ✅ **易于维护**：修改一处即可影响全局
- ✅ **性能监控**：自动记录和分析性能瓶颈
- ✅ **异常处理**：统一的异常处理机制

所有新的 Service 都应该使用这些统一的切面，保持代码的一致性和可维护性。
