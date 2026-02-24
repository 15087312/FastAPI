from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    ForeignKey,
    CheckConstraint,
    TIMESTAMP,
    text,
)
from app.db.base import Base


class ProductStock(Base):
    __tablename__ = "product_stocks"

    product_id = Column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
        comment="商品ID",
    )

    available_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="当前可售库存",
    )

    reserved_stock = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="已预占库存",
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
        CheckConstraint(
            "available_stock >= 0",
            name="ck_available_stock_non_negative",
        ),
        CheckConstraint(
            "reserved_stock >= 0",
            name="ck_reserved_stock_non_negative",
        ),
    )