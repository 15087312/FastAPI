from sqlalchemy import (
    Column,
    BigInteger,
    String,
    TIMESTAMP,
    text,
    Index,
)
from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    sku = Column(
        String(64),
        nullable=False,
        unique=True,
        comment="商品唯一SKU",
    )

    name = Column(
        String(255),
        nullable=False,
        comment="商品名称",
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
        onupdate=text("now()"),
    )


# -----------------------------
# 组合索引（如果未来支持按名称搜索）
# -----------------------------
Index(
    "idx_products_name",
    Product.name,
)

















