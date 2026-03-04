# PostgreSQL Alembic 自增主键问题解决方案

## 📋 问题背景

在 FastAPI + PostgreSQL + Alembic 项目中，为已有表 `product_stocks` 添加自增主键 `id` 列时遇到了问题。

### **症状**
- 迁移脚本执行成功，但插入数据时报错
- 错误信息：`null value in column "id" of relation "product_stocks" violates not-null constraint`
- `id` 列没有自动递增，需要手动指定值

### **错误日志**
```sql
(psycopg2.errors.NotNullViolation) null value in column "id" of relation "product_stocks" violates not-null constraint
DETAIL: Failing row contains (1, 0, 0, 0, 2026-03-04 13:03:38.245159+00, ..., null, WH01, 0, 0, 0).
```

---

## 🔍 问题分析

### **1. PostgreSQL 的自增机制**

在 PostgreSQL 中，实现自增列有三种方式：

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| **SERIAL/BIGSERIAL** | 伪类型，自动创建序列并设置默认值 | 创建新表时使用 |
| **Sequence + DEFAULT** | 手动创建序列并设置默认值 | 修改现有表结构 |
| **GENERATED ALWAYS AS IDENTITY** | SQL 标准语法（PostgreSQL 10+） | 新项目推荐使用 |

### **2. Alembic 的限制**

Alembic 的 `op.add_column()` 方法无法直接为 PostgreSQL 创建自增列：

```python
# ❌ 错误方式 - autoincrement=True 不会生效
op.add_column('product_stocks', sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False))

# ❌ 错误方式 - server_default 也不会生效
op.add_column('product_stocks', sa.Column('id', sa.BigInteger(), 
                                           server_default=sa.text("nextval('seq')"),
                                           nullable=False))
```

**原因：**
- `autoincrement=True` 只在使用 `create_table()` 时有效
- `add_column()` 是在已有表上添加列，Alembic 不会自动创建序列
- 在事务中执行 `ALTER COLUMN ... SET DEFAULT` 可能不生效

---

## ✅ 解决方案

### **方案一：分步执行（推荐用于修改现有表）**

```python
from sqlalchemy import text

def upgrade() -> None:
    # 1. 先添加列为普通列
    op.add_column('product_stocks', sa.Column('id', sa.BigInteger(), nullable=False))
    
    # 2. 使用连接对象执行原生 SQL
    from sqlalchemy import text
    conn = op.get_bind()
    
    # 3. 创建序列
    conn.execute(text("CREATE SEQUENCE IF NOT EXISTS product_stocks_id_seq"))
    
    # 4. 设置列为使用序列作为默认值
    conn.execute(text("ALTER TABLE product_stocks ALTER COLUMN id SET DEFAULT nextval('product_stocks_id_seq')"))
    
    # 5. 初始化序列值（从现有最大 ID 开始）
    conn.execute(text("SELECT setval('product_stocks_id_seq', COALESCE((SELECT MAX(id) FROM product_stocks), 1), true)"))
```

### **方案二：在新表中直接使用 BIGSERIAL**

```python
# ✅ 正确方式 - 创建新表时使用
op.create_table('products',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.PrimaryKeyConstraint('id')
)

# 或者显式使用 BIGSERIAL
op.create_table('my_table',
    sa.Column('id', sa.BigInteger(), sa.Sequence('my_table_id_seq'), nullable=False),
    sa.PrimaryKeyConstraint('id')
)
```

### **方案三：迁移后手动修复**

如果迁移脚本已经执行但 `id` 列没有自增，可以手动执行 SQL 修复：

```bash
# Docker 环境
docker exec fastapi_db psql -U postgres -d mydb -c \
  "CREATE SEQUENCE IF NOT EXISTS product_stocks_id_seq; \
   ALTER TABLE product_stocks ALTER COLUMN id SET DEFAULT nextval('product_stocks_id_seq'); \
   SELECT setval('product_stocks_id_seq', COALESCE((SELECT MAX(id) FROM product_stocks), 1), true);"
```

---

## 🛠️ 完整迁移脚本示例

文件：`alembic/versions/a1b2c3d4e5f6_add_warehouse_support.py`

```python
"""add warehouse and multi-stock fields

Revision ID: a1b2c3d4e5f6
Revises: f7d3a84be1ff
Create Date: 2026-03-04 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7d3a84be1ff'

def upgrade() -> None:
    """Upgrade schema: add warehouse support and stock fields."""
    
    # === product_stocks 表改造 ===
    
    # 1. 添加 id 主键列（先添加为普通列）
    op.add_column('product_stocks', sa.Column('id', sa.BigInteger(), nullable=False))
    
    # 2. 创建序列并设置为默认值（PostgreSQL 特殊处理）
    # 注意：由于 add_column 时无法直接设置 autoincrement，需要手动创建序列并设置默认值
    # 使用独立的事务来确保 ALTER COLUMN 生效
    from sqlalchemy import text
    conn = op.get_bind()
    conn.execute(text("CREATE SEQUENCE IF NOT EXISTS product_stocks_id_seq"))
    conn.execute(text("ALTER TABLE product_stocks ALTER COLUMN id SET DEFAULT nextval('product_stocks_id_seq')"))
    conn.execute(text("SELECT setval('product_stocks_id_seq', COALESCE((SELECT MAX(id) FROM product_stocks), 1), true)"))
    
    # 3. 添加其他列
    op.add_column('product_stocks', sa.Column('warehouse_id', sa.String(length=32), nullable=False, server_default='WH01'))
    op.add_column('product_stocks', sa.Column('frozen_stock', sa.Integer(), server_default='0', nullable=False))
    op.add_column('product_stocks', sa.Column('in_transit_stock', sa.Integer(), server_default='0', nullable=False))
    op.add_column('product_stocks', sa.Column('safety_stock', sa.Integer(), server_default='0', nullable=False))
    
    # 4. 删除原有主键约束
    op.drop_constraint('product_stocks_pkey', 'product_stocks', type_='primary')
    
    # 5. 添加复合唯一索引
    op.create_index('uq_warehouse_product', 'product_stocks', ['warehouse_id', 'product_id'], unique=True)

def downgrade() -> None:
    """Downgrade schema: revert to single warehouse model."""
    
    op.drop_index('uq_warehouse_product', table_name='product_stocks')
    op.drop_column('product_stocks', 'safety_stock')
    op.drop_column('product_stocks', 'in_transit_stock')
    op.drop_column('product_stocks', 'frozen_stock')
    op.drop_column('product_stocks', 'warehouse_id')
    op.drop_column('product_stocks', 'id')
    op.create_primary_key('product_stocks_pkey', 'product_stocks', ['product_id'])
    
    # 删除序列
    op.execute("DROP SEQUENCE IF EXISTS product_stocks_id_seq")
```

---

## 📊 验证步骤

### **1. 检查表结构**

```sql
-- 查看表结构
\d product_stocks

-- 应该看到：
-- Column | Type | Default
-- -------+------+---------------------------
-- id     | bigint | nextval('product_stocks_id_seq'::regclass)
```

### **2. 检查序列**

```sql
-- 查看所有序列
\ds

-- 检查序列当前值
SELECT last_value FROM product_stocks_id_seq;
```

### **3. 测试插入数据**

```sql
-- 测试插入（不指定 id，应该自动递增）
INSERT INTO product_stocks (warehouse_id, product_id, available_stock)
VALUES ('WH01', 1, 100);

-- 查看结果（应该有自动生成的 id）
SELECT * FROM product_stocks;
```

---

## ⚠️ 常见错误与解决方法

### **错误 1：迁移成功但 id 没有默认值**

**症状：** `\d product_stocks` 显示 `Default` 为空

**解决：**
```sql
-- 手动执行修复
ALTER TABLE product_stocks ALTER COLUMN id SET DEFAULT nextval('product_stocks_id_seq');
```

### **错误 2：插入时违反非空约束**

**症状：** `null value in column "id" violates not-null constraint`

**原因：** 序列不存在或未设置默认值

**解决：**
```sql
CREATE SEQUENCE IF NOT EXISTS product_stocks_id_seq;
ALTER TABLE product_stocks ALTER COLUMN id SET DEFAULT nextval('product_stocks_id_seq');
```

### **错误 3：重复键值违反唯一约束**

**症状：** `duplicate key value violates unique constraint`

**原因：** 序列值未正确初始化，导致生成的 ID 与现有数据冲突

**解决：**
```sql
-- 重新设置序列值为当前最大 ID + 1
SELECT setval('product_stocks_id_seq', (SELECT MAX(id) FROM product_stocks) + 1, false);
```

---

## 💡 最佳实践建议

### **1. 新表设计**

对于新表，建议在模型定义时就明确指定自增：

```python
class ProductStock(Base):
    __tablename__ = "product_stocks"
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,  # SQLAlchemy 会自动处理
        comment="主键 ID"
    )
```

然后让 Alembic 自动生成迁移脚本：

```bash
alembic revision --autogenerate -m "create product_stocks table"
```

### **2. 修改现有表**

为现有表添加自增列时，采用分步执行策略：

1. 添加普通列
2. 创建序列
3. 设置默认值
4. 初始化序列值

### **3. 使用 Identity 列（PostgreSQL 10+）**

如果使用的是 PostgreSQL 10 或更高版本，可以考虑使用标准的 IDENTITY 列：

```python
# SQLAlchemy 2.0+ 支持
from sqlalchemy import Identity

id = Column(BigInteger, Identity(start=1, increment=1), primary_key=True)
```

### **4. 迁移后验证**

每次迁移后都应该验证：
- ✅ 表结构正确（`\d table_name`）
- ✅ 序列存在（`\ds`）
- ✅ 默认值设置正确
- ✅ 插入测试数据成功

---

## 🔗 相关资源

- [Alembic 官方文档 - Operations](https://alembic.sqlalchemy.org/en/latest/ops.html)
- [PostgreSQL 序列文档](https://www.postgresql.org/docs/current/sql-createsequence.html)
- [PostgreSQL SERIAL 类型](https://www.postgresql.org/docs/current/datatype-numeric.html#DATATYPE-SERIAL)
- [SQLAlchemy Identity 列](https://docs.sqlalchemy.org/en/20/core/defaults.html#associating-a-sequence-or-identity-column-as-the-default)

---

## 📝 总结

在 PostgreSQL 中使用 Alembic 添加自增主键的关键点：

1. **理解 PostgreSQL 的自增机制** - 基于序列实现
2. **区分新表和现有表** - 新表用 `autoincrement=True`，现有表需要手动创建序列
3. **使用 `op.get_bind()`** - 获取连接对象执行原生 SQL
4. **初始化序列值** - 避免与现有数据冲突
5. **迁移后验证** - 确保表结构和默认值正确

通过遵循这些最佳实践，可以避免在数据库迁移过程中遇到自增主键相关的问题。
