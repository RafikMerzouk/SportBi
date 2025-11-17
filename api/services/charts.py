# api/services/charts.py
import io
import datetime as _dt
from typing import List, Optional

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.dates as mdates

from fastapi import HTTPException
from ..models import ChartSpec, ChartOptions

# Matplotlib defaults (propres)
plt.rcParams.update({
    "figure.figsize": (12, 6),
    "axes.titlesize": 18,
    "axes.labelsize": 14,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "lines.linewidth": 2.0,
    "lines.markersize": 5.5,
})

# ---------- helpers ----------
def _ensure_columns(df: pd.DataFrame, cols: List[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Colonnes manquantes: {missing}")

def _assert_numeric(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c in df.columns and not pd.api.types.is_numeric_dtype(df[c]):
            raise HTTPException(status_code=400, detail=f"Colonne non numérique: {c}")

def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=144, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def _apply_theme(theme: Optional[str]):
    plt.style.use("dark_background" if (theme or "light").lower() == "dark" else "default")

def _format_y(ax, y_fmt: Optional[str]):
    if not y_fmt:
        return
    def _fmt_k(x, _pos):
        sign = "-" if x < 0 else ""
        v = abs(x)
        if v >= 1_000_000: return f"{sign}{v/1_000_000:.1f}M"
        if v >= 1_000:     return f"{sign}{v/1_000:.1f}k"
        return f"{sign}{int(v) if float(v).is_integer() else v:.1f}"
    fmts = {
        "int":    FuncFormatter(lambda x, _pos: f"{int(round(x))}"),
        "float0": FuncFormatter(lambda x, _pos: f"{x:.0f}"),
        "float1": FuncFormatter(lambda x, _pos: f"{x:.1f}"),
        "k":      FuncFormatter(_fmt_k),
    }
    if y_fmt in fmts:
        ax.yaxis.set_major_formatter(fmts[y_fmt])

def _maybe_datetime_axis(ax, x_series: pd.Series):
    try:
        if pd.api.types.is_datetime64_any_dtype(x_series) or isinstance(x_series.iloc[0], (pd.Timestamp, _dt.date, _dt.datetime)):
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=10))
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
            plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    except Exception:
        pass

def _maybe_rolling(df: pd.DataFrame, spec: ChartSpec) -> pd.DataFrame:
    win = (spec.options or ChartOptions()).rolling
    if not win or win <= 1:
        return df
    cols = [spec.y] if isinstance(spec.y, str) else (spec.y or [])
    if spec.x and spec.x in df.columns:
        df = df.sort_values(spec.x)
    for c in cols:
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].rolling(window=win, min_periods=max(1, win // 2)).mean()
    return df

def _maybe_topn(df: pd.DataFrame, spec: ChartSpec) -> pd.DataFrame:
    top_n = (spec.options or ChartOptions()).top_n
    if not top_n or top_n <= 0 or not spec.x:
        return df
    if isinstance(spec.y, str) and spec.y in df.columns:
        vals = df.groupby(spec.x)[spec.y].sum().abs().sort_values(ascending=False).head(top_n).index
        return df[df[spec.x].isin(vals)]
    return df

# ---------- core ----------
def plot_chart(df: pd.DataFrame, spec: ChartSpec) -> bytes:
    opts = spec.options or ChartOptions()
    _apply_theme(opts.theme)

    # pré-traitements
    df = _maybe_rolling(df.copy(), spec)
    df = _maybe_topn(df, spec)

    t = spec.type

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
        fig, ax = plt.subplots()
        ax.pie(df[value_col], labels=df[label_col], autopct="%1.0f%%")
        ax.set_title(spec.title or "Répartition")
        fig.tight_layout()
        return _to_png(fig)

    # SCATTER
    if t == "scatter":
        if not spec.x or not spec.y:
            raise HTTPException(status_code=400, detail="Scatter: x et y requis.")
        ys = [spec.y] if isinstance(spec.y, str) else list(spec.y)
        _ensure_columns(df, [spec.x] + ys)
        _assert_numeric(df, ys)
        fig, ax = plt.subplots()
        for y_col in ys:
            ax.scatter(df[spec.x], df[y_col], label=y_col if opts.legend else None)
        ax.set_title(spec.title or "")
        ax.set_xlabel(spec.x_label or spec.x)
        ax.set_ylabel(spec.y_label or ", ".join(ys))
        if opts.legend and len(ys) > 1:
            ax.legend()
        _maybe_datetime_axis(ax, df[spec.x])
        plt.setp(ax.get_xticklabels(), rotation=opts.x_rotate or 0,
                 ha="right" if (opts.x_rotate or 0) else "center")
        _format_y(ax, opts.y_fmt)
        fig.tight_layout()
        return _to_png(fig)

    # BAR / LINE / AREA
    if t in {"bar", "line", "area"}:
        # multi-séries
        if spec.series:
            if not spec.x or not spec.y or isinstance(spec.y, list):
                raise HTTPException(status_code=400, detail="Avec 'series', fournissez x et y (str).")
            series_col = spec.series
            _ensure_columns(df, [spec.x, spec.y, series_col])
            _assert_numeric(df, [spec.y])
            piv = df.pivot_table(index=spec.x, columns=series_col, values=spec.y, aggfunc="sum").reset_index()
            if opts.sort and spec.x in piv.columns:
                piv = piv.sort_values(spec.x)
            fig, ax = plt.subplots()
            for col in [c for c in piv.columns if c != spec.x]:
                if t == "bar":
                    if opts.orientation == "horizontal":
                        ax.barh(piv[spec.x], piv[col], label=str(col))
                    else:
                        ax.bar(piv[spec.x], piv[col], label=str(col))
                elif t == "line":
                    ax.plot(piv[spec.x], piv[col], marker="o", label=str(col))
                elif t == "area":
                    ax.fill_between(piv[spec.x], piv[col], alpha=0.3, label=str(col))
            ax.set_title(spec.title or "")
            ax.set_xlabel(spec.x_label or spec.x)
            ax.set_ylabel(spec.y_label or str(spec.y))
            if opts.legend:
                ax.legend()
            _maybe_datetime_axis(ax, piv[spec.x])
            plt.setp(ax.get_xticklabels(), rotation=opts.x_rotate or 0,
                     ha="right" if (opts.x_rotate or 0) else "center")
            _format_y(ax, opts.y_fmt)
            fig.tight_layout()
            return _to_png(fig)

        # y liste
        fig, ax = plt.subplots()
        if isinstance(spec.y, list):
            _ensure_columns(df, ([spec.x] + spec.y) if spec.x else spec.y)
            _assert_numeric(df, spec.y)
            data = df.sort_values(spec.x) if (spec.x and opts.sort) else df
            if t == "bar":
                width = 0.8 / max(1, len(spec.y))
                if spec.x:
                    xvals = list(range(len(data[spec.x])))
                    for i, ycol in enumerate(spec.y):
                        xoffs = [k + (i - (len(spec.y)-1)/2)*width for k in xvals]
                        if opts.orientation == "horizontal":
                            ax.barh(xoffs, data[ycol], height=width, label=ycol)
                            ax.set_yticks(xvals); ax.set_yticklabels(list(map(str, data[spec.x])))
                        else:
                            ax.bar(xoffs, data[ycol], width=width, label=ycol)
                            ax.set_xticks(xvals); ax.set_xticklabels(list(map(str, data[spec.x])))
                else:
                    idx = range(len(data))
                    for i, ycol in enumerate(spec.y):
                        xoffs = [k + (i - (len(spec.y)-1)/2)*width for k in idx]
                        ax.bar(xoffs, data[ycol], width=width, label=ycol)
            elif t == "line":
                for ycol in spec.y:
                    ax.plot(data[spec.x], data[ycol], marker="o", label=ycol) if spec.x else ax.plot(data[ycol], marker="o", label=ycol)
            elif t == "area":
                if not spec.x:
                    import pandas as _pd
                    base = _pd.DataFrame({"idx": range(len(data))})
                    data = _pd.concat([base, data], axis=1)
                    spec.x = "idx"
                cumulative = None
                for ycol in spec.y:
                    vals = data[ycol]
                    if cumulative is None:
                        cumulative = vals.copy()
                        ax.fill_between(data[spec.x], cumulative, alpha=0.3, label=ycol)
                    else:
                        new_cum = cumulative + vals
                        ax.fill_between(data[spec.x], cumulative, new_cum, alpha=0.3, label=ycol)
                        cumulative = new_cum
            if opts.legend:
                ax.legend()
            ax.set_title(spec.title or "")
            if spec.x:
                ax.set_xlabel(spec.x_label or spec.x)
            ax.set_ylabel(spec.y_label or (", ".join(spec.y)))
            if spec.x:
                _maybe_datetime_axis(ax, data[spec.x])
                plt.setp(ax.get_xticklabels(), rotation=opts.x_rotate or 0,
                         ha="right" if (opts.x_rotate or 0) else "center")
            _format_y(ax, opts.y_fmt)
            fig.tight_layout()
            return _to_png(fig)

        # y simple
        if not isinstance(spec.y, str):
            raise HTTPException(status_code=400, detail="y doit être une chaîne ou une liste de chaînes.")
        _ensure_columns(df, [spec.x, spec.y] if spec.x else [spec.y])
        _assert_numeric(df, [spec.y])
        data = df.sort_values(spec.x) if (spec.x and opts.sort) else df
        if t == "bar":
            if spec.x:
                if opts.orientation == "horizontal":
                    ax.barh(data[spec.x], data[spec.y])
                else:
                    ax.bar(data[spec.x], data[spec.y])
            else:
                ax.bar(range(len(data[spec.y])), data[spec.y])
        elif t == "line":
            ax.plot(data[spec.x], data[spec.y], marker="o") if spec.x else ax.plot(data[spec.y], marker="o")
        elif t == "area":
            if spec.x:
                ax.fill_between(data[spec.x], data[spec.y], alpha=0.3)
            else:
                ax.fill_between(range(len(data[spec.y])), data[spec.y], alpha=0.3)
        ax.set_title(spec.title or "")
        if spec.x:
            ax.set_xlabel(spec.x_label or spec.x)
        ax.set_ylabel(spec.y_label or spec.y)
        if spec.x:
            _maybe_datetime_axis(ax, data[spec.x])
            plt.setp(ax.get_xticklabels(), rotation=opts.x_rotate or 0,
                     ha="right" if (opts.x_rotate or 0) else "center")
        _format_y(ax, opts.y_fmt)
        fig.tight_layout()
        return _to_png(fig)

    raise HTTPException(status_code=400, detail=f"Type de graphique non géré: {t}")
