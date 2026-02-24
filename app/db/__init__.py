from .base import Base
from .session import engine
# db/init_db.py

from app.db.session import engine
from app.models import *

def init_db():
    Base.metadata.create_all(bind=engine)
# Export for convenience
__all__ = ["Base", "engine"]