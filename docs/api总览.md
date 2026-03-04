🎯 库存微服务 API 设计（企业级标准版）

## 📊 核心库存查询接口

### 1️⃣ 单个商品库存查询
```
GET /inventory/stock/{product_id}
```

**响应示例：**
```json
{
  "success": true,
  "product_id": 1,
  "available_stock": 100,
  "reserved_stock": 10
}
```

### 2️⃣ 批量商品库存查询
```
POST /inventory/stock/batch
```

**请求参数（Body）：**
```json
{
  "product_ids": [1, 2, 3]
}
```

**响应示例：**
```json
{
  "success": true,
  "data": {
    "1": {"available": 100, "reserved": 10},
    "2": {"available": 50, "reserved": 5},
    "3": {"available": 0, "reserved": 0}
  }
}
```

## ➕ 库存调整接口（新增）

### 9️⃣ 增加库存（入库/补货）
```
POST /inventory/increase
```

**请求参数（Query Parameters）：**
- `product_id` (int, required): 商品 ID
- `quantity` (int, required): 增加数量
- `reason` (string, optional): 入库原因（采购入库/退货入库/盘点增加）

**核心逻辑：**
- 🔒 数据库行级锁
- ➕ 增加 `available_stock`
- 📝 如果是新商品，自动创建库存记录
- 📊 记录库存变更日志（类型：ADJUST）

**响应示例：**
```json
{
  "success": true,
  "message": "库存增加成功",
  "data": {
    "product_id": 1,
    "previous_stock": 100,
    "increased_quantity": 50,
    "current_stock": 150
  }
}
```

### 🔟 调整库存（盘点修正）
```
POST /inventory/adjust?product_id=1&quantity=80&reason=盘点修正
```

**请求参数（Query Parameters）：**
- `product_id` (int, required): 商品 ID
- `quantity` (int, required): 调整后库存数量
- `reason` (string, required): 调整原因

**核心逻辑：**
- 🔒 数据库行级锁
- 🎯 直接设置库存为目标值
- 📊 记录调整前后的差异
- 📝 记录详细的调整日志

**响应示例：**
```json
{
  "success": true,
  "message": "库存调整成功",
  "data": {
    "product_id": 1,
    "previous_stock": 150,
    "adjusted_stock": 80,
    "difference": -70
  }
}
```

## 📝 库存流水接口（新增）

### 1️⃣1️⃣ 查询库存变更日志
```
GET /inventory/logs?product_id=1&page=1&page_size=20
```

**查询参数：**
- `product_id` (int, optional): 商品 ID（可选）
- `order_id` (string, optional): 订单 ID（可选）
- `change_type` (string, optional): 变更类型（RESERVE/CONFIRM/RELEASE/ADJUST）
- `page` (int, optional): 页码，默认 1
- `page_size` (int, optional): 每页数量，默认 20

**响应示例：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "product_id": 1,
      "order_id": "ORD123",
      "change_type": "RESERVE",
      "quantity": -2,
      "before_available": 100,
      "after_available": 98,
      "created_at": "2024-01-01T10:00:00Z",
      "operator": "order_service"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20
}
```

## 🛡️ 库存操作核心接口

### 3️⃣ 预占库存（防超卖核心）
```
POST /inventory/reserve?product_id=1&quantity=2&order_id=ORD123
```

**请求参数（Query Parameters）：**
- `product_id` (int, required): 商品ID
- `quantity` (int, required): 预占数量
- `order_id` (string, required): 订单ID

**核心逻辑：**
- 🔒 数据库行级锁 (`.with_for_update()`)
- ✅ 校验 `available_stock >= quantity`
- ➖ 扣减 `available_stock`
- ➕ 增加 `reserved_stock`
- 📝 创建预占记录（15分钟过期）
- 📊 记录库存变更日志

**响应示例：**
```json
{
  "success": true,
  "message": "预占成功",
  "data": true
}
```

### 4️⃣ 确认库存扣减（支付成功）
```
POST /inventory/confirm/{order_id}
```

**路径参数：**
- `order_id` (string, required): 订单ID

**核心逻辑：**
- 🔒 行级锁查询商品库存
- ➖ 扣减 `reserved_stock`
- 📈 增加 `sales_count`（销量统计）
- 🔄 更新预占状态为 CONFIRMED
- 📊 记录确认操作日志

**响应示例：**
```json
{
  "success": true,
  "message": "确认成功",
  "data": true
}
```

### 5️⃣ 释放预占库存（取消订单）
```
POST /inventory/release/{order_id}
```

**路径参数：**
- `order_id` (string, required): 订单ID

**核心逻辑：**
- 🔒 行级锁查询商品库存
- ➕ 恢复 `available_stock`
- ➖ 扣减 `reserved_stock`
- 🔄 更新预占状态为 RELEASED
- 📊 记录释放操作日志

**响应示例：**
```json
{
  "success": true,
  "message": "释放成功",
  "data": true
}
```

## 📦 批量操作接口（新增）

### 1️⃣2️⃣ 批量预占库存（订单包含多个商品）
```
POST /inventory/reserve-batch
```

**请求参数（Body）：**
```json
{
  "order_id": "ORD123",
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 2, "quantity": 1},
    {"product_id": 3, "quantity": 5}
  ]
}
```

**核心逻辑：**
- 🔒 数据库事务保证原子性
- ✅ 所有商品库存检查
- ➖ 批量扣减可用库存
- ➕ 批量增加预占库存
- 📝 创建多条预占记录
- 📊 记录所有变更日志
- ⚠️ 任一商品失败则整体回滚

**响应示例：**
```json
{
  "success": true,
  "message": "批量预占成功",
  "data": {
    "order_id": "ORD123",
    "total_items": 3,
    "reserved_items": [
      {"product_id": 1, "quantity": 2, "status": "RESERVED"},
      {"product_id": 2, "quantity": 1, "status": "RESERVED"},
      {"product_id": 3, "quantity": 5, "status": "RESERVED"}
    ]
  }
}
```

**错误处理：**
```json
{
  "success": false,
  "message": "商品 ID 为 2 的库存不足",
  "failed_item": {
    "product_id": 2,
    "requested_quantity": 1,
    "available_stock": 0
  },
  "rolled_back": true
}
```

## 🧹 自动化维护接口

### 6️⃣ 手动触发清理任务
```
POST /inventory/cleanup/manual?batch_size=500
```

**查询参数：**
- `batch_size` (int, optional): 批处理大小，默认500

**功能说明：**
- 🎯 直接调用 Service 层清理逻辑
- 📦 批处理模式（默认500条/批）
- 🔒 并发安全（skip_locked 防止竞争）
- 📊 返回清理统计信息

**响应示例：**
```json
{
  "success": true,
  "message": "手动清理完成",
  "cleaned_count": 150
}
```

### 7️⃣ 异步清理任务触发
```
POST /inventory/cleanup/celery?batch_size=500
```

**查询参数：**
- `batch_size` (int, optional): 批处理大小，默认500

**功能说明：**
- 🚀 通过 Celery 异步执行
- 📋 返回任务 ID 用于状态查询
- ⏰ 适合定时调度和大批量清理

**响应示例：**
```json
{
  "success": true,
  "message": "已提交异步清理任务",
  "task_id": "abcdef123456"
}
```

### 8️⃣ 清理任务状态查询
```
GET /inventory/cleanup/status/{task_id}
```

**路径参数：**
- `task_id` (string, required): 任务ID

**响应示例：**
```json
{
  "task_id": "abcdef123456",
  "status": "任务完成: 成功清理 150 条过期预占记录",
  "state": "SUCCESS"
}
```

## 🏗️ 企业级架构特色

### 🎯 三层调用入口
1. **API 直接调用** → `/inventory/cleanup/manual`
2. **Celery 异步调用** → `/inventory/cleanup/celery`
3. **本地 CLI 调用** → `python -m app.jobs.manual_cleanup`

### 🔧 核心技术栈
- **Web框架**: FastAPI + Uvicorn
- **数据库**: PostgreSQL + SQLAlchemy ORM
- **缓存**: Redis (库存缓存)
- **分布式锁**: Redis Redlock
- **异步任务**: Celery + Redis Broker
- **数据库迁移**: Alembic

### 🔧 核心技术保障
- **并发控制**：数据库行级锁 + skip_locked
- **内存优化**：批处理限制 + 循环清理
- **错误处理**：事务回滚 + 异常捕获
- **日志追踪**：详细执行过程记录
- **扩展性**：支持多 Worker 并行处理

### 📊 性能指标
- **批处理大小**：可配置（推荐 500-1000）
- **并发安全**：支持多实例同时运行
- **内存占用**：O(batch_size) 级别
- **执行效率**：每批次 100-500ms

### 🛡️ 安全特性
- **输入验证**：Pydantic Schema 校验
- **权限控制**：基于服务间调用
- **防重放攻击**：幂等性设计
- **数据一致性**：ACID 事务保证

## 📊 能力分级评估

### Level 1（基础版）✅ 已达标
- ✅ 单商品库存查询
- ✅ 预占/确认/释放操作
- ✅ 防超卖机制（行级锁 + 分布式锁）
- ✅ 幂等性保证
- ✅ 过期自动清理

### Level 2（电商生产级）🆕 已升级
- ✅ 批量事务操作（reserve-batch）
- ✅ 库存流水日志（inventory logs）
- ✅ 库存调整接口（increase/adjust）
- ✅ 完整的审计追踪
- ⚠️ 性能监控（待实现）

### Level 3（企业库存中台）🔜 规划中
- ⏳ 多仓支持（warehouse_id + product_id）
- ⏳ 冻结库存管理
- ⏳ 安全库存预警
- ⏳ 在途库存管理
- ⏳ 库存上下限策略
- ⏳ 灰度发布策略

## 🚀 下一步优化方向

1. **多仓库支持** - 支持多仓发货和就近配送
2. **库存冻结** - 区分可用/冻结/在途库存
3. **智能预警** - 库存低于阈值时自动通知
4. **批量查询优化** - 支持更大规模的批量操作
5. **监控告警** - 实时监控库存异常和操作失败