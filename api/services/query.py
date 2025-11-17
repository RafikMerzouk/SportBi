# api/services/query.py
import time
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text
from ..db import engine
from ..config import API_MAX_ROWS, API_QUERY_TIMEOUT
from ..security import validate_sql_is_safe

def run_query_df(sql: str, params: dict | None) -> pd.DataFrame:
    validate_sql_is_safe(sql)
    params = params or {}
    if " limit " not in sql.lower():
        sql = sql.rstrip() + f" LIMIT {API_MAX_ROWS}"
    start = time.time()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    if time.time() > start + API_QUERY_TIMEOUT:
        raise HTTPException(status_code=408, detail="Temps d’exécution dépassé")
    return df
