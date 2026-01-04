# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .log import setup_logging
from .config import CORS_ORIGINS
from .routes.charts import router as charts_router
from .routes.nlpq import router as nlpq_router
from .config import NLP_AUTO_INDEX, NLP_MODEL_NAME

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
app.include_router(nlpq_router)

@app.on_event("startup")
def _load_nlp_index():
    if not NLP_AUTO_INDEX:
        log.info("NLP index auto-build désactivé (NLP_AUTO_INDEX=0).")
        return
    try:
        from .routes.nlpq import SCHEMA_MAPPING
        from .services.nlp_index import build_index_from_db

        schema_to_league = {schema: league for league, schema in SCHEMA_MAPPING.items()}
        idx = build_index_from_db(schema_to_league, model_name=NLP_MODEL_NAME)
        if idx:
            log.info("NLP index construit (%s)", NLP_MODEL_NAME)
        else:
            log.warning("NLP index non construit (faiss/transformers indisponibles ?)")
    except Exception as e:  # pragma: no cover
        log.error("Erreur init NLP index: %s", e)

@app.get("/health")
def health():
    return {"status": "ok"}
