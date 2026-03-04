import enum

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Integer,
    TIMESTAMP,
    text,
    Enum,
    UniqueConstraint,
    Index,
    ForeignKey,
)
from app.db.base import Base


class ReservationStatus(str, enum.Enum):
    RESERVED = "RESERVED"     # 已预占
    CONFIRMED = "CONFIRMED"    # 已确认扣减
    RELEASED = "RELEASED"      # 已释放
    CANCELED = "CANCELED"      # 取消


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    warehouse_id = Column(
        String(32),
        nullable=False,
        index=True,
        comment="仓库ID",
    )

    order_id = Column(
        String(64),
        nullable=False,
        index=True,
        comment="订单ID",
    )

    product_id = Column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="商品ID",
    )

    quantity = Column(
        Integer,
        nullable=False,
        comment="预占数量",
    )

    status = Column(
        Enum(
            ReservationStatus,
            name="reservation_status_type",
            create_type=True,
        ),
        nullable=False,
        server_default=ReservationStatus.RESERVED.value,
        comment="预占状态",
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )

    expired_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="预占过期时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "order_id",
            "product_id",
            name="uq_warehouse_order_product",
        ),
    )


Index(
    "idx_reservation_product_status",
    InventoryReservation.product_id,
    InventoryReservation.status,
)

Index(
    "idx_reservation_warehouse_status",
    InventoryReservation.warehouse_id,
    InventoryReservation.status,
)