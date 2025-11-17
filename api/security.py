# api/security.py
import re
from fastapi import HTTPException

DDL_DML_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|MERGE|CALL|COMMENT|VACUUM|ANALYZE)\b",
    re.IGNORECASE,
)
LEADING_COMMENTS_RE = re.compile(
    r"^\s*(?:--[^\n]*\n|/\*.*?\*/|\s+)*", re.DOTALL
)
MULTI_STMT = re.compile(r";")

def _first_keyword(sql: str) -> str:
    s = LEADING_COMMENTS_RE.sub("", sql or "").lstrip()
    m = re.match(r"([a-zA-Z]+)", s)
    return m.group(1).lower() if m else ""

def validate_sql_is_safe(sql: str) -> None:
    s = (sql or "").strip()
    if MULTI_STMT.search(s):
        raise HTTPException(status_code=400, detail="SQL invalide: une seule instruction sans ';' est autorisée.")
    fk = _first_keyword(s)
    if fk not in {"select", "with"}:
        raise HTTPException(status_code=400, detail="SQL invalide: seules les requêtes SELECT (ou WITH ... SELECT) sont autorisées.")
    if DDL_DML_FORBIDDEN.search(s):
        raise HTTPException(status_code=400, detail="SQL invalide: DDL/DML interdits.")
