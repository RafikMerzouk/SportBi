# api/config.py
import os

DB_HOST = os.getenv("DB_HOST", "lbwl_db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "lbwl")
DB_USER = os.getenv("DB_USER", "lbwl_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lbwl_pass")

ENGINE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

API_MAX_ROWS = int(os.getenv("API_MAX_ROWS", "5000"))
API_QUERY_TIMEOUT = float(os.getenv("API_QUERY_TIMEOUT", "15.0"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]

# NLP / embeddings
NLP_AUTO_INDEX = os.getenv("NLP_AUTO_INDEX", "0") == "1"
NLP_MODEL_NAME = os.getenv("NLP_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
