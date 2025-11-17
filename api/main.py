# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .log import setup_logging
from .config import CORS_ORIGINS
from .routes.charts import router as charts_router

log = setup_logging()

app = FastAPI(title="LBWL Analytics API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(charts_router)

@app.get("/health")
def health():
    return {"status": "ok"}
