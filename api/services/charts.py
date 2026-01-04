"""
Chart rendering service (Plotly + Kaleido) pour des graphes stylés.
Prend un ChartSpec et renvoie un PNG.
"""

import io
from typing import List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fastapi import HTTPException

from ..models import ChartSpec, ChartOptions


def _ensure_columns(df: pd.DataFrame, cols: List[str]) -> None:
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Colonnes manquantes: {missing}")


def _assert_numeric(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c and c in df.columns and not pd.api.types.is_numeric_dtype(df[c]):
            raise HTTPException(status_code=400, detail=f"Colonne non numérique: {c}")


def _apply_template(theme: str):
    return "plotly_dark" if (theme or "light").lower() == "dark" else "plotly_white"


def _to_png(fig) -> bytes:
    return fig.to_image(format="png", scale=2)


def plot_chart(df: pd.DataFrame, spec: ChartSpec) -> bytes:
    opts: ChartOptions = spec.options or ChartOptions()
    template = _apply_template(opts.theme or "light")
    t = spec.type

    # pré-tri / rolling éventuel
    if spec.x and opts.sort:
        df = df.sort_values(spec.x)
    if opts.rolling and opts.rolling > 1:
        ys = [spec.y] if isinstance(spec.y, str) else (spec.y or [])
        for c in ys:
            if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = df[c].rolling(window=opts.rolling, min_periods=max(1, opts.rolling // 2)).mean()

    # PIE
    if t == "pie":
        if spec.y:
            if isinstance(spec.y, list) and len(spec.y) == 2:
                label_col, value_col = spec.y
            elif isinstance(spec.y, str) and spec.x:
                label_col, value_col = spec.x, spec.y
            else:
                raise HTTPException(status_code=400, detail="Pie: y=[label,value] ou x + y requis.")
        else:
            raise HTTPException(status_code=400, detail="Pie: y (et/ou x) requis.")
        _ensure_columns(df, [label_col, value_col])
        fig = px.pie(df, names=label_col, values=value_col, title=spec.title or "", template=template)
        return _to_png(fig)

    # SCATTER
    if t == "scatter":
        if not spec.x or not spec.y:
            raise HTTPException(status_code=400, detail="Scatter: x et y requis.")
        ys = [spec.y] if isinstance(spec.y, str) else list(spec.y)
        _ensure_columns(df, [spec.x] + ys)
        _assert_numeric(df, ys)
        fig = px.scatter(df, x=spec.x, y=ys[0] if len(ys) == 1 else ys, title=spec.title or "", template=template)
        return _to_png(fig)

    # BAR / LINE / AREA
    if t in {"bar", "line", "area"}:
        # multi-séries via pivot si spec.series fourni
        if spec.series:
            if not spec.x or not spec.y or isinstance(spec.y, list):
                raise HTTPException(status_code=400, detail="Avec 'series', fournissez x et y (str).")
            _ensure_columns(df, [spec.x, spec.y, spec.series])
            _assert_numeric(df, [spec.y])
            piv = df.pivot_table(index=spec.x, columns=spec.series, values=spec.y, aggfunc="sum").reset_index()
            if opts.sort and spec.x in piv.columns:
                piv = piv.sort_values(spec.x)
            if t == "bar":
                fig = go.Figure()
                for col in [c for c in piv.columns if c != spec.x]:
                    fig.add_bar(name=str(col), x=piv[spec.x], y=piv[col])
                fig.update_layout(barmode="group", template=template, title=spec.title or "",
                                  xaxis_title=spec.x_label or spec.x, yaxis_title=spec.y_label or str(spec.y))
                if opts.legend: fig.update_layout(showlegend=True)
                return _to_png(fig)
            if t == "line":
                fig = px.line(piv, x=spec.x, y=[c for c in piv.columns if c != spec.x], title=spec.title or "", template=template)
                fig.update_layout(xaxis_title=spec.x_label or spec.x, yaxis_title=spec.y_label or str(spec.y))
                return _to_png(fig)
            if t == "area":
                fig = go.Figure()
                for col in [c for c in piv.columns if c != spec.x]:
                    fig.add_trace(go.Scatter(x=piv[spec.x], y=piv[col], stackgroup="one", name=str(col), mode="lines"))
                fig.update_layout(template=template, title=spec.title or "",
                                  xaxis_title=spec.x_label or spec.x, yaxis_title=spec.y_label or str(spec.y))
                return _to_png(fig)

        # y multiple
        if isinstance(spec.y, list):
            _ensure_columns(df, ([spec.x] + spec.y) if spec.x else spec.y)
            _assert_numeric(df, spec.y)
            data = df
            if t == "bar":
                fig = go.Figure()
                x_vals = data[spec.x] if spec.x else list(range(len(data)))
                for ycol in spec.y:
                    if opts.orientation == "horizontal":
                        fig.add_bar(y=x_vals, x=data[ycol], orientation="h", name=ycol)
                    else:
                        fig.add_bar(x=x_vals, y=data[ycol], name=ycol)
                fig.update_layout(barmode="group" if not opts.stacked else "stack",
                                  template=template,
                                  title=spec.title or "",
                                  xaxis_title=spec.x_label or (spec.x or ""),
                                  yaxis_title=spec.y_label or ", ".join(spec.y))
                return _to_png(fig)
            if t == "line":
                fig = px.line(data, x=spec.x, y=spec.y, title=spec.title or "", template=template)
                fig.update_layout(xaxis_title=spec.x_label or (spec.x or ""), yaxis_title=spec.y_label or ", ".join(spec.y))
                return _to_png(fig)
            if t == "area":
                fig = go.Figure()
                for ycol in spec.y:
                    fig.add_trace(go.Scatter(x=data[spec.x] if spec.x else list(range(len(data))),
                                             y=data[ycol], stackgroup="one", name=ycol, mode="lines"))
                fig.update_layout(template=template, title=spec.title or "",
                                  xaxis_title=spec.x_label or (spec.x or ""), yaxis_title=spec.y_label or ", ".join(spec.y))
                return _to_png(fig)

        # y simple
        if not isinstance(spec.y, str):
            raise HTTPException(status_code=400, detail="y doit être une chaîne ou une liste de chaînes.")
        _ensure_columns(df, [spec.y] + ([spec.x] if spec.x else []))
        _assert_numeric(df, [spec.y])
        data = df
        if t == "bar":
            if spec.x:
                fig = px.bar(data, x=spec.x, y=spec.y, title=spec.title or "", template=template,
                             orientation="h" if opts.orientation == "horizontal" else "v")
            else:
                fig = px.bar(y=data[spec.y], title=spec.title or "", template=template)
            fig.update_layout(xaxis_title=spec.x_label or (spec.x or ""), yaxis_title=spec.y_label or spec.y)
            return _to_png(fig)
        if t == "line":
            fig = px.line(data, x=spec.x, y=spec.y, title=spec.title or "", template=template)
            fig.update_layout(xaxis_title=spec.x_label or (spec.x or ""), yaxis_title=spec.y_label or spec.y)
            return _to_png(fig)
        if t == "area":
            fig = px.area(data, x=spec.x, y=spec.y, title=spec.title or "", template=template)
            fig.update_layout(xaxis_title=spec.x_label or (spec.x or ""), yaxis_title=spec.y_label or spec.y)
            return _to_png(fig)

    raise HTTPException(status_code=400, detail=f"Type de graphique non géré: {t}")

