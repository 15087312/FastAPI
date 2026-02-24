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
  "available_stock": 100
}
```

### 2️⃣ 批量商品库存查询
```
POST /inventory/stock/batch
```

**请求参数：**
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
    "1": 100,
    "2": 50,
    "3": 0
  }
}
```

## 🛡️ 库存操作核心接口

### 3️⃣ 预占库存（防超卖核心）
```
POST /inventory/reserve
```

**请求参数：**
```json
{
  "product_id": 1,
  "quantity": 2,
  "order_id": "ORD123"
}
```

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

**核心逻辑：**
- 🔒 行级锁查询商品库存
- ➖ 扣减 `reserved_stock`
- 📈 增加 `sales_count`（销量统计）
- 🔄 更新预占状态为 CONFIRMED
- 📊 记录确认操作日志

### 5️⃣ 释放预占库存（取消订单）
```
POST /inventory/release/{order_id}
```

**核心逻辑：**
- 🔒 行级锁查询商品库存
- ➕ 恢复 `available_stock`
- ➖ 扣减 `reserved_stock`
- 🔄 更新预占状态为 RELEASED
- 📊 记录释放操作日志

## 🧹 自动化维护接口

### 6️⃣ 手动触发清理任务
```
POST /inventory/cleanup/manual?batch_size=500
```

**功能说明：**
- 🎯 直接调用 Service 层清理逻辑
- 📦 批处理模式（默认500条/批）
- 🔒 并发安全（skip_locked 防止竞争）
- 📊 返回清理统计信息

### 7️⃣ 异步清理任务触发
```
POST /inventory/cleanup/celery?batch_size=500
```

**功能说明：**
- 🚀 通过 Celery 异步执行
- 📋 返回任务 ID 用于状态查询
- ⏰ 适合定时调度和大批量清理

### 8️⃣ 清理任务状态查询
```
GET /inventory/cleanup/status/{task_id}
```

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