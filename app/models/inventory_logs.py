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


class ChangeType(str, enum.Enum):
    RESERVE = "RESERVE"      # 预占库存
    CONFIRM = "CONFIRM"      # 确认扣减
    RELEASE = "RELEASE"       # 释放库存
    ADJUST = "ADJUST"        # 人工调整
    INCREASE = "INCREASE"    # 入库/补货
    FREEZE = "FREEZE"         # 冻结库存
    UNFREEZE = "UNFREEZE"    # 解冻库存
    BATCH_RESERVE = "BATCH_RESERVE"  # 批量预占
    BATCH_RELEASE = "BATCH_RELEASE"  # 批量释放


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    warehouse_id = Column(
        String(32),
        nullable=True,
        index=True,
        comment="仓库ID（可选，用于多仓场景）",
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
            name="inventory_change_type",
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

    before_reserved = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="变更前预占库存",
    )

    after_reserved = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="变更后预占库存",
    )

    before_frozen = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="变更前冻结库存",
    )

    after_frozen = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="变更后冻结库存",
    )

    remark = Column(
        String(255),
        nullable=True,
        comment="备注（如调整原因）",
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
        comment="来源：order_service / manual / webhook / system",
    )


Index(
    "idx_inventory_logs_product_created_desc",
    InventoryLog.product_id,
    InventoryLog.created_at.desc(),
)

Index(
    "idx_inventory_logs_warehouse_created_desc",
    InventoryLog.warehouse_id,
    InventoryLog.created_at.desc(),
)

Index(
    "idx_inventory_logs_order_id",
    InventoryLog.order_id,
)
