# api/routes/charts.py
from fastapi import APIRouter, HTTPException, Response
from ..models import RequestSpec
from ..services.query import run_query_df
from ..services.charts import plot_chart

router = APIRouter()

@router.post("/render", summary="Exécute la requête et renvoie un PNG")
def render_chart(req: RequestSpec):
    df = run_query_df(req.sql, req.params, schema=req.schema)
    if df.empty:
        raise HTTPException(status_code=404, detail="La requête a renvoyé 0 ligne.")
    png = plot_chart(df, req.chart)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": 'inline; filename="chart.png"'}
    )

@router.post("/render/base64", summary="PNG encodé en base64")
def render_chart_base64(req: RequestSpec):
    import base64
    df = run_query_df(req.sql, req.params, schema=req.schema)
    if df.empty:
        raise HTTPException(status_code=404, detail="La requête a renvoyé 0 ligne.")
    png = plot_chart(df, req.chart)
    b64 = base64.b64encode(png).decode("ascii")
    return {"content_type": "image/png", "filename": "chart.png", "base64": b64}

@router.post("/dry-run", summary="Aperçu JSON (limité)")
def dry_run(req: RequestSpec):
    df = run_query_df(req.sql, req.params, schema=req.schema)
    preview = df.head(50).to_dict(orient="records")
    return {"rows": preview, "columns": list(df.columns), "count": len(df)}

@router.post("/csv", summary="Export CSV", response_class=Response)
def export_csv(req: RequestSpec):
    df = run_query_df(req.sql, req.params, schema=req.schema)
    if df.empty:
        raise HTTPException(status_code=404, detail="0 ligne")
    csv = df.to_csv(index=False).encode("utf-8")
    return Response(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename=\"export.csv\"'}
    )
