
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class BaseSchema(BaseModel):
    """基础响应字段"""
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True  # 支持从 ORM 对象直接生成 Schema