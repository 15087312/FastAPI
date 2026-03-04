"""add warehouse and multi-stock fields

Revision ID: a1b2c3d4e5f6
Revises: f7d3a84be1ff
Create Date: 2026-03-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7d3a84be1ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add warehouse support and stock fields."""
    
    # === 1. 创建新的 ENUM 类型（包含所有值）===
    # 注意：PostgreSQL ALTER TYPE ADD VALUE 只能在事务外执行
    # 这里我们创建一个新类型，然后修改列类型
    
    # 先检查并创建新的 change_type 枚举类型
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inventory_change_type_new') THEN
                CREATE TYPE inventory_change_type_new AS ENUM (
                    'RESERVE', 'CONFIRM', 'RELEASE', 'ADJUST', 
                    'INCREASE', 'FREEZE', 'UNFREEZE', 'ADJUST_INCREASE', 'ADJUST_DECREASE'
                );
            END IF;
        END $$;
    """)
    
    # === product_stocks 表改造 ===
    
    # 1. 添加 id 主键列（自增）
    op.add_column('product_stocks', sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False))
    
    # 2. 添加 warehouse_id 列
    op.add_column('product_stocks', sa.Column('warehouse_id', sa.String(length=32), nullable=False, server_default='WH01'))
    
    # 3. 添加新的库存字段
    op.add_column('product_stocks', sa.Column('frozen_stock', sa.Integer(), server_default='0', nullable=False))
    op.add_column('product_stocks', sa.Column('in_transit_stock', sa.Integer(), server_default='0', nullable=False))
    op.add_column('product_stocks', sa.Column('safety_stock', sa.Integer(), server_default='0', nullable=False))
    
    # 4. 删除原有的 product_id 主键约束
    op.drop_constraint('product_stocks_pkey', 'product_stocks', type_='primary')
    
    # 5. 添加复合唯一索引
    op.create_index('uq_warehouse_product', 'product_stocks', ['warehouse_id', 'product_id'], unique=True)
    
    # 6. 添加 CHECK 约束
    op.create_check_constraint('ck_frozen_stock_non_negative', 'product_stocks', 'frozen_stock >= 0')
    op.create_check_constraint('ck_in_transit_stock_non_negative', 'product_stocks', 'in_transit_stock >= 0')
    op.create_check_constraint('ck_safety_stock_non_negative', 'product_stocks', 'safety_stock >= 0')
    
    # === inventory_reservations 表改造 ===
    
    # 1. 添加 warehouse_id 列
    op.add_column('inventory_reservations', sa.Column('warehouse_id', sa.String(length=32), nullable=False, server_default='WH01'))
    
    # 2. 删除原有的唯一约束
    op.drop_constraint('uq_order_product', 'inventory_reservations', type_='unique')
    
    # 3. 添加新的复合唯一约束
    op.create_unique_constraint('uq_warehouse_order_product', 'inventory_reservations', ['warehouse_id', 'order_id', 'product_id'])
    
    # 4. 添加索引
    op.create_index('idx_reservation_warehouse_status', 'inventory_reservations', ['warehouse_id', 'status'], unique=False)
    
    # === inventory_logs 表改造 ===
    
    # 1. 添加 warehouse_id 列
    op.add_column('inventory_logs', sa.Column('warehouse_id', sa.String(length=32), nullable=True))
    
    # 2. 添加新的库存字段
    op.add_column('inventory_logs', sa.Column('before_reserved', sa.Integer(), server_default='0', nullable=False))
    op.add_column('inventory_logs', sa.Column('after_reserved', sa.Integer(), server_default='0', nullable=False))
    op.add_column('inventory_logs', sa.Column('before_frozen', sa.Integer(), server_default='0', nullable=False))
    op.add_column('inventory_logs', sa.Column('after_frozen', sa.Integer(), server_default='0', nullable=False))
    op.add_column('inventory_logs', sa.Column('remark', sa.String(length=255), nullable=True))
    
    # 3. 添加索引
    op.create_index('idx_inventory_logs_warehouse_created_desc', 'inventory_logs', ['warehouse_id', sa.desc('created_at')], unique=False)
    
    # 4. 修改 ENUM 类型列
    op.execute("ALTER TABLE inventory_logs ALTER COLUMN change_type TYPE inventory_change_type_new USING change_type::text::inventory_change_type_new")
    
    # 5. 删除旧类型（可选，保留旧类型以便回滚）
    # op.execute("DROP TYPE inventory_change_type")


def downgrade() -> None:
    """Downgrade schema: revert to single warehouse model."""
    
    # === inventory_logs 表还原 ===
    op.drop_index('idx_inventory_logs_warehouse_created_desc', table_name='inventory_logs')
    op.drop_column('inventory_logs', 'remark')
    op.drop_column('inventory_logs', 'after_frozen')
    op.drop_column('inventory_logs', 'before_frozen')
    op.drop_column('inventory_logs', 'after_reserved')
    op.drop_column('inventory_logs', 'before_reserved')
    op.drop_column('inventory_logs', 'warehouse_id')
    
    # === inventory_reservations 表还原 ===
    op.drop_index('idx_reservation_warehouse_status', table_name='inventory_reservations')
    op.drop_constraint('uq_warehouse_order_product', 'inventory_reservations', type_='unique')
    op.create_unique_constraint('uq_order_product', 'inventory_reservations', ['order_id', 'product_id'])
    op.drop_column('inventory_reservations', 'warehouse_id')
    
    # === product_stocks 表还原 ===
    op.drop_constraint('ck_safety_stock_non_negative', 'product_stocks', type_='check')
    op.drop_constraint('ck_in_transit_stock_non_negative', 'product_stocks', type_='check')
    op.drop_constraint('ck_frozen_stock_non_negative', 'product_stocks', type_='check')
    op.drop_index('uq_warehouse_product', table_name='product_stocks')
    op.drop_column('product_stocks', 'safety_stock')
    op.drop_column('product_stocks', 'in_transit_stock')
    op.drop_column('product_stocks', 'frozen_stock')
    op.drop_column('product_stocks', 'warehouse_id')
    op.drop_column('product_stocks', 'id')
    op.create_primary_key('product_stocks_pkey', 'product_stocks', ['product_id'])
