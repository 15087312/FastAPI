import enum

from sqlalchemy import (
    Column,
    String,
    TIMESTAMP,
    text,
    Enum,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base



# 1️ 幂等状态枚举

class IdempotencyStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"  # 正在处理中
    SUCCESS = "SUCCESS"        # 成功
    FAILED = "FAILED"          # 失败



# 2️ 幂等表

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    # 幂等唯一Key（通常是订单号+操作类型）
    key = Column(
        String(128),
        primary_key=True,
        comment="幂等唯一键",
    )

    status = Column(
        Enum(
            IdempotencyStatus,
            name="idempotency_status_type",
            create_type=True,
        ),
        nullable=False,
        server_default=IdempotencyStatus.PROCESSING.value,
        comment="当前处理状态",
    )

    # 存储接口响应快照（成功后返回）
    response_snapshot = Column(
        JSONB,
        nullable=True,
        comment="接口响应结果快照",
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    expires_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="过期时间（用于清理）",
    )



# 3️ 索引设计

Index(
    "idx_idempotency_keys_expires_at",
    IdempotencyKey.expires_at,
)











