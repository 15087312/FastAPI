from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    ForeignKey,
    CheckConstraint,
    TIMESTAMP,
    text,
    Index,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class ProductStock(Base):
    __tablename__ = "product_stocks"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    warehouse_id = Column(
        String(32),
        nullable=False,
        index=True,
        comment="仓库ID",
    )

    product_id = Column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="商品ID",
    )

    available_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="可用库存",
    )

    reserved_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="预占库存",
    )

    frozen_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="冻结库存（如待检品、待定分配）",
    )

    safety_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="安全库存（最低库存预警线）",
    )

    version = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="乐观锁版本号",
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        # 复合唯一索引：仓库ID+商品ID 唯一
        Index(
            "uq_warehouse_product",
            "warehouse_id",
            "product_id",
            unique=True,
        ),
        CheckConstraint(
            "available_stock >= 0",
            name="ck_available_stock_non_negative",
        ),
        CheckConstraint(
            "reserved_stock >= 0",
            name="ck_reserved_stock_non_negative",
        ),
        CheckConstraint(
            "frozen_stock >= 0",
            name="ck_frozen_stock_non_negative",
        ),
        CheckConstraint(
            "safety_stock >= 0",
            name="ck_safety_stock_non_negative",
        ),
    )