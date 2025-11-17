# api/db.py
from sqlalchemy import create_engine
from .config import ENGINE_URL

engine = create_engine(ENGINE_URL, pool_pre_ping=True)
