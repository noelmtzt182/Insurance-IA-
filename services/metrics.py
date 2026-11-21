"""Cálculo de indicadores comerciales y de campañas.

Todas las divisiones usan ``safe_div``: si el denominador es 0 o falta un dato,
el resultado es ``None`` (se muestra como "—"), nunca un número inventado.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from utils.config import IDX_QUALIFIED, IDX_QUOTE, PRODUCTS, STAGES, STAGE_LOST


def _is_missing(x) -> bool:
    if x is None:
        return True
    try:
        return isinstance(x, float) and math.isnan(x) or pd.isna(x)
    except (TypeError, ValueError):
        return False


def safe_div(num, den, scale: float = 1.0) -> Optional[float]:
    if _is_missing(num) or _is_missing(den):
        return None
    try:
        den = float(den)
        num = float(num)
    except (TypeError, ValueError):
        return None
    if den == 0:
        return None
    return num / den * scale


def fmt_money(x, decimals: int = 0) -> str:
    if _is_missing(x):
        return "—"
    return f"-${abs(x):,.{decimals}f}" if x < 0 else f"${x:,.{decimals}f}"


def fmt_pct(x, decimals: int = 1) -> str:
    return "—" if _is_missing(x) else f"{x:.{decimals}f}%"


def fmt_ratio(x, decimals: int = 2) -> str:
    return "—" if _is_missing(x) else f"{x:.{decimals}f}x"


def fmt_int(x) -> str:
    return "—" if _is_missing(x) else f"{int(x):,}"


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
def is_quoted(df: pd.DataFrame) -> pd.Series:
    return (df["max_stage_index"] >= IDX_QUOTE) | df["quote_amount"].notna()


def is_policy(df: pd.DataFrame) -> pd.Series:
    return df["stage"] == "Póliza emitida"


def is_qualified(df: pd.DataFrame) -> pd.Series:
    return df["max_stage_index"] >= IDX_QUALIFIED


def funnel_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Leads que alcanzaron cada etapa (acumulado, incluye los perdidos después)."""
    rows = []
    for i, stage in enumerate(STAGES):
        if i == len(STAGES) - 1:
            n = int(is_policy(df).sum()) if len(df) else 0
        else:
            n = int((df["max_stage_index"] >= i).sum()) if len(df) else 0
        rows.append({"Etapa": stage, "Leads": n})
    out = pd.DataFrame(rows)
    prev = out["Leads"].shift(1)
    out["Conversión desde etapa previa"] = [safe_div(n, p, 100) for n, p in zip(out["Leads"], prev)]
    return out


def lead_kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    if total == 0:
        return {"total": 0, "qualified": 0, "quotes": 0, "policies": 0, "conversion": None,
                "commissions": None, "premium": None, "lost": 0, "active": 0, "appointments": 0}
    policies = int(is_policy(df).sum())
    commissions = df.loc[is_policy(df), "commission"].sum(min_count=1)
    premium = df.loc[is_policy(df), "policy_premium"].sum(min_count=1)
    return {
        "total": total,
        "qualified": int(is_qualified(df).sum()),
        "appointments": int(is_appointment(df).sum()),
        "quotes": int(is_quoted(df).sum()),
        "policies": policies,
        "conversion": safe_div(policies, total, 100),
        "commissions": None if pd.isna(commissions) else float(commissions),
        "premium": None if pd.isna(premium) else float(premium),
        "lost": int((df["stage"] == STAGE_LOST).sum()),
        "active": int((~df["stage"].isin(["Póliza emitida", STAGE_LOST])).sum()),
    }


def conversion_by(df: pd.DataFrame, col: str) -> pd.DataFrame:
    cols = [col, "Leads", "Calificados", "Cotizaciones", "Pólizas", "Conversión %", "Comisiones"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    tmp = df.assign(_q=is_qualified(df), _c=is_quoted(df), _p=is_policy(df),
                    _com=df["commission"].where(is_policy(df)))
    tmp[col] = tmp[col].fillna("Sin dato")
    g = tmp.groupby(col).agg(Leads=("id", "count"), Calificados=("_q", "sum"),
                             Cotizaciones=("_c", "sum"), Pólizas=("_p", "sum"),
                             Comisiones=("_com", lambda s: s.sum(min_count=1))).reset_index()
    g["Conversión %"] = [safe_div(p, l, 100) for p, l in zip(g["Pólizas"], g["Leads"])]
    return g[cols].sort_values("Leads", ascending=False).reset_index(drop=True)


def product_conversion(df: pd.DataFrame) -> pd.DataFrame:
    out = conversion_by(df, "product")
    present = set(out["product"]) if not out.empty else set()
    missing = [p for p in PRODUCTS if p not in present]
    if missing:
        filler = pd.DataFrame([{"product": p, "Leads": 0, "Calificados": 0, "Cotizaciones": 0,
                                "Pólizas": 0, "Conversión %": None, "Comisiones": None} for p in missing])
        out = pd.concat([out, filler], ignore_index=True) if not out.empty else filler
    return out.rename(columns={"product": "Producto"})


# ---------------------------------------------------------------------------
# Campañas
# ---------------------------------------------------------------------------
def is_appointment(df: pd.DataFrame) -> pd.Series:
    from utils.config import IDX_APPOINTMENT
    return df["max_stage_index"] >= IDX_APPOINTMENT


def campaign_metrics(investment, leads, policies, commissions, quotes=None, impressions=None, clicks=None) -> dict:
    """Fórmulas oficiales del módulo Campañas y ROI (con protección contra división entre cero)."""
    return {
        "CPL": safe_div(investment, leads),
        "CPC": safe_div(investment, clicks),
        "CTR %": safe_div(clicks, impressions, 100),
        "CAC": safe_div(investment, policies),
        "Conversión %": safe_div(policies, leads, 100),
        "ROAS comisiones": safe_div(commissions, investment),
        "Tasa cotización %": safe_div(quotes, leads, 100),
    }


def _pick(manual, crm):
    return (crm, "CRM") if _is_missing(manual) else (manual, "Manual")


CAMPAIGN_TABLE_COLS = ["id", "Campaña", "Plataforma", "Producto", "Segmento", "Estado", "Inversión", "Impresiones",
                       "Clics", "CTR %", "CPC", "Leads", "Calificados", "Citas", "Cotizaciones", "Pólizas",
                       "Comisiones", "CPL", "CAC", "Conversión %", "ROAS comisiones", "Score promedio",
                       "Origen de datos", "Origen resultados"]


def campaign_table(camps: pd.DataFrame, leads: pd.DataFrame) -> pd.DataFrame:
    """Combina métricas de plataforma (observadas/importadas/estimadas) con resultados del CRM."""
    if camps.empty:
        return pd.DataFrame(columns=CAMPAIGN_TABLE_COLS)
    rows = []
    for _, c in camps.iterrows():
        sub = leads[leads["campaign_id"] == c["id"]] if not leads.empty else leads
        n = len(sub)
        crm = {
            "leads": n,
            "quotes": int(is_quoted(sub).sum()) if n else 0,
            "pol": int(is_policy(sub).sum()) if n else 0,
            "com": float(sub.loc[is_policy(sub), "commission"].fillna(0).sum()) if n else 0.0,
        }
        n_leads, o1 = _pick(c["leads_manual"], crm["leads"])
        n_quotes, o2 = _pick(c["quotes_manual"], crm["quotes"])
        n_pol, o3 = _pick(c["policies_manual"], crm["pol"])
        com, o4 = _pick(c["commissions_manual"], crm["com"])
        origins = {o1, o2, o3, o4}
        inv = None if _is_missing(c["investment"]) else float(c["investment"])
        imp = None if _is_missing(c.get("impressions")) else int(c["impressions"])
        clk = None if _is_missing(c.get("clicks")) else int(c["clicks"])
        m = campaign_metrics(inv, n_leads, n_pol, com, n_quotes, imp, clk)
        rows.append({
            "id": int(c["id"]), "Campaña": c["name"], "Plataforma": c["platform"], "Producto": c.get("product"),
            "Segmento": c.get("segment"), "Estado": c.get("status"), "Inversión": inv, "Impresiones": imp,
            "Clics": clk, "CTR %": m["CTR %"], "CPC": m["CPC"], "Leads": int(n_leads),
            "Calificados": int(is_qualified(sub).sum()) if n else 0,
            "Citas": int(is_appointment(sub).sum()) if n else 0,
            "Cotizaciones": int(n_quotes), "Pólizas": int(n_pol), "Comisiones": float(com),
            "CPL": m["CPL"], "CAC": m["CAC"], "Conversión %": m["Conversión %"],
            "ROAS comisiones": m["ROAS comisiones"],
            "Score promedio": float(sub["score"].mean()) if n else None,
            "Origen de datos": c.get("data_origin") or "Observado",
            "Origen resultados": "Mixto" if len(origins) > 1 else origins.pop(),
        })
    return pd.DataFrame(rows, columns=CAMPAIGN_TABLE_COLS)


def overall_acquisition(ctable: pd.DataFrame) -> dict:
    keys = ["investment", "impressions", "clicks", "leads", "CTR", "CPC", "CPL", "CAC", "ROAS", "policies",
            "commissions"]
    if ctable.empty:
        return {k: None for k in keys}
    inv = ctable["Inversión"].sum(min_count=1)
    imp = ctable["Impresiones"].sum(min_count=1)
    clk = ctable["Clics"].sum(min_count=1)
    # CTR/CPC solo con campañas que reportan ambos valores
    both = ctable.dropna(subset=["Impresiones", "Clics"])
    with_clicks = ctable.dropna(subset=["Clics", "Inversión"])
    leads = int(ctable["Leads"].sum())
    pol = int(ctable["Pólizas"].sum())
    com = float(ctable["Comisiones"].sum())
    return {
        "investment": None if pd.isna(inv) else float(inv),
        "impressions": None if pd.isna(imp) else int(imp),
        "clicks": None if pd.isna(clk) else int(clk),
        "leads": leads,
        "CTR": safe_div(both["Clics"].sum(), both["Impresiones"].sum(), 100) if not both.empty else None,
        "CPC": safe_div(with_clicks["Inversión"].sum(), with_clicks["Clics"].sum()) if not with_clicks.empty else None,
        "CPL": safe_div(inv, leads),
        "CAC": safe_div(inv, pol),
        "ROAS": safe_div(com, inv),
        "policies": pol,
        "commissions": com,
    }


def weekly_series(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Semana", "Leads", "Pólizas"])
    tmp = df.assign(Semana=df["created_at"].dt.to_period("W-SUN").dt.start_time, _p=is_policy(df))
    return tmp.groupby("Semana").agg(Leads=("id", "count"), Pólizas=("_p", "sum")).reset_index()
