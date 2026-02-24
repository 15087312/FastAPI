import enum

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Integer,
    TIMESTAMP,
    text,
    Enum,
    Index,
)
from app.db.base import Base

# 1定义库存变更类型（数据库 ENUM）
class ChangeType(str, enum.Enum):
    RESERVE = "RESERVE"   # 预占库存
    CONFIRM = "CONFIRM"   # 确认扣减
    RELEASE = "RELEASE"   # 释放库存
    ADJUST = "ADJUST"     # 人工调整
# 2️库存日志表
class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    product_id = Column(
        BigInteger,
        nullable=False,
        index=True,
        comment="商品ID",
    )

    order_id = Column(
        String(64),
        nullable=True,
        index=True,
        comment="订单ID（可能为空，例如库存调整）",
    )

    change_type = Column(
        Enum(
            ChangeType,
            name="inventory_change_type",  # 重要！PostgreSQL ENUM 类型名
            create_type=True,
        ),
        nullable=False,
        comment="库存变更类型",
    )

    quantity = Column(
        Integer,
        nullable=False,
        comment="变更数量",
    )

    before_available = Column(
        Integer,
        nullable=False,
        comment="变更前可用库存",
    )

    after_available = Column(
        Integer,
        nullable=False,
        comment="变更后可用库存",
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    operator = Column(
        String(64),
        nullable=True,
        comment="操作人/服务名/API Key",
    )

    source = Column(
        String(50),
        nullable=True,
        comment="来源：order_service / manual / webhook",
    )

# 3️组合索引（高频查询优化）


Index(
    "idx_inventory_logs_product_created_desc",
    InventoryLog.product_id,
    InventoryLog.created_at.desc(),
)
