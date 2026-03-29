# 🚀 通用版本快速开始

## 5 分钟快速上手

### 1️⃣ 安装依赖

```bash
pip install fastapi sqlalchemy redis pydantic python-dotenv psycopg2-binary
```

### 2️⃣ 复制核心文件

```bash
# 创建目录结构
mkdir -p app/core app/db app/services

# 复制核心文件（从原项目）
cp /path/to/original/app/core/config_generic.py app/core/
cp /path/to/original/app/core/model_factory.py app/core/
cp /path/to/original/app/core/model_configs.json app/core/
cp /path/to/original/app/db/base.py app/db/
cp /path/to/original/app/services/generic_inventory_service.py app/services/
```

### 3️⃣ 配置环境变量

创建 `.env` 文件：

```bash
cat > .env << EOF
# 数据库配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=your_db

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379

# 通用模型配置
ENABLED_MODELS=Product,ProductStock
USE_BUILTIN_INVENTORY_MODELS=True
USE_CUSTOM_MODELS=False

# 功能开关
ENABLE_REDIS_CACHE=true
ENABLE_BLOOM_FILTER=true
ENABLE_IDEMPOTENCY=true
EOF
```

### 4️⃣ 使用动态模型

创建 `main.py`：

```python
from fastapi import FastAPI
from app.core.model_factory import create_product_model

app = FastAPI()

# 创建模型
Product = create_product_model()

@app.get("/products/{product_id}")
def get_product(product_id: int):
    # 使用模型查询数据库
    # 这里省略数据库连接代码
    return {"id": product_id, "name": "测试商品"}
```

### 5️⃣ 运行测试

```bash
# 测试模型创建
python -c "from app.core.model_factory import create_product_model; print(create_product_model())"

# 启动服务
uvicorn main:app --reload
```

---

## 💡 常用场景

### 场景 1：标准电商库存系统

```bash
# .env
ENABLED_MODELS=Product,ProductStock,InventoryReservation,Order
USE_BUILTIN_INVENTORY_MODELS=True
```

### 场景 2：票务系统

```bash
# .env
ENABLED_MODELS=Event,Ticket,Order
USE_CUSTOM_MODELS=True
CUSTOM_MODEL_CONFIG_PATH=config/ticket_system.json
```

创建 `config/ticket_system.json`：

```json
{
  "Event": {
    "table_name": "events",
    "fields": {
      "id": {"type": "BigInteger", "primary_key": true, "autoincrement": true},
      "name": {"type": "String", "max_length": 255, "nullable": false},
      "date": {"type": "TIMESTAMP", "nullable": false}
    }
  },
  "Ticket": {
    "table_name": "tickets",
    "fields": {
      "id": {"type": "BigInteger", "primary_key": true, "autoincrement": true},
      "event_id": {"type": "BigInteger", "nullable": false, "index": true},
      "seat": {"type": "String", "max_length": 20, "nullable": false},
      "price": {"type": "Integer", "nullable": false},
      "status": {"type": "String", "max_length": 20, "default": "available"}
    }
  }
}
```

### 场景 3：酒店管理系统

```bash
# .env
ENABLED_MODELS=Hotel,Room,Booking
USE_CUSTOM_MODELS=True
CUSTOM_MODEL_CONFIG_PATH=config/hotel_system.json
```

---

## 🔧 核心 API

### 创建单个模型

```python
from app.core.model_factory import ModelFactory

Product = ModelFactory.create_model("Product")
Warehouse = ModelFactory.create_model("Warehouse")
```

### 批量创建模型

```python
models = ModelFactory.create_all_models()
for name, model in models.items():
    print(f"{name}: {model.__tablename__}")
```

### 使用通用服务

```python
from app.services.generic_inventory_service import create_generic_inventory_service

service = create_generic_inventory_service(redis_client)

# 查询库存
stock = service.get_product_stock("WH001", 980)

# 预占库存
service.reserve_stock("WH001", 980, 5, "ORDER_001")
```

---

## 📋 完整示例

查看 `examples/generic_usage.py` 获取完整使用示例。

---

## 📚 详细文档

- [通用版本配置指南](docs/通用版本配置指南.md) - 完整的配置说明
- [模型配置 JSON 示例](app/core/model_configs.json) - JSON 配置模板
- [配置类源码](app/core/config_generic.py) - 配置类实现
- [模型工厂源码](app/core/model_factory.py) - 动态模型创建

---

## ❓ 常见问题

**Q: 如何添加自定义字段？**  
A: 编辑 JSON 配置文件，在对应模型的 `fields` 中添加新字段，然后运行数据库迁移。

**Q: 可以同时使用内置和自定义模型吗？**  
A: 可以，设置 `USE_BUILTIN_INVENTORY_MODELS=True` 和 `USE_CUSTOM_MODELS=True`。

**Q: 如何迁移现有数据库？**  
A: 使用 Alembic 的自动迁移功能：`alembic revision --autogenerate -m "描述"`。

---

## 🎯 下一步

1. 阅读 [通用版本配置指南](docs/通用版本配置指南.md)
2. 查看 [JSON 配置示例](app/core/model_configs.json)
3. 运行 [使用示例](examples/generic_usage.py)
4. 根据业务需求定制模型
