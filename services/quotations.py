"""Smart Quotation Manager — comparación de cotizaciones OFICIALES.

Solo compara datos capturados de cotizaciones emitidas por aseguradoras
autorizadas. No estima, completa ni inventa valores: si un dato no fue
capturado, se muestra como «No indicado».
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from services.metrics import fmt_money, safe_div
from utils.config import today_mx

MAX_COMPARE = 3

ROWS = [
    ("Aseguradora", "insurer"), ("Plan", "plan_name"), ("Prima capturada", "premium_label"),
    ("Prima anual equivalente", "annual_premium"), ("Suma asegurada", "sum_insured"), ("Deducible", "deductible"),
    ("Coaseguro", "coinsurance_pct"), ("Tope de coaseguro", "coinsurance_cap"),
    ("Red hospitalaria", "hospital_network"), ("Vigencia de la cotización", "valid_until"),
    ("Observaciones", "observations"), ("PDF oficial", "has_pdf"), ("Estado", "status"),
]


def _fmt(key: str, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return "No indicado"
    if key in ("annual_premium", "sum_insured", "deductible", "coinsurance_cap"):
        return fmt_money(v)
    if key == "coinsurance_pct":
        return f"{v:g}%"
    if key == "valid_until":
        days = (v - today_mx()).days
        return f"{v:%d/%m/%Y} ({'vencida' if days < 0 else f'{days} días'})"
    if key == "has_pdf":
        return "Sí" if v else "No"
    return str(v)


def compare(quotes: pd.DataFrame, today: Optional[date] = None) -> dict:
    """Devuelve tabla comparativa y diferencias objetivas entre 2 y 3 cotizaciones."""
    if len(quotes) < 2:
        raise ValueError("Selecciona al menos 2 cotizaciones para comparar.")
    if len(quotes) > MAX_COMPARE:
        raise ValueError(f"Puedes comparar hasta {MAX_COMPARE} cotizaciones.")
    q = quotes.reset_index(drop=True).copy()
    q["premium_label"] = [f"{fmt_money(a, 2)} {p.lower()}" for a, p in zip(q["premium_amount"], q["premium_period"])]
    labels = [f"#{r.id} · {r.insurer}" for r in q.itertuples()]
    table = pd.DataFrame({lab: [_fmt(k, q.loc[i, k]) for _, k in ROWS] for i, lab in enumerate(labels)},
                         index=[name for name, _ in ROWS])

    findings = []
    prem = q["annual_premium"]
    cheapest = int(prem.idxmin())
    for i in range(len(q)):
        if i != cheapest:
            diff = prem[i] - prem[cheapest]
            pct = safe_div(diff, prem[cheapest], 100)
            findings.append(f"Precio: {labels[i]} cuesta {fmt_money(diff)} más al año que {labels[cheapest]} "
                            f"(+{pct:.1f}%).")
    if q["sum_insured"].notna().sum() >= 2:
        si = q["sum_insured"]
        hi = int(si.idxmax())
        findings.append(f"Cobertura: la mayor suma asegurada es la de {labels[hi]} ({fmt_money(si[hi])}).")
        ratio = [safe_div(p, s, 1000) for p, s in zip(prem, si)]
        if all(r is not None for r in ratio):
            best = min(range(len(ratio)), key=lambda k: ratio[k])
            findings.append(f"Prima por cada $1,000 de suma asegurada: menor en {labels[best]} "
                            f"({fmt_money(ratio[best], 2)}). Úsalo como referencia, no como único criterio.")
    else:
        findings.append("Cobertura: captura la suma asegurada en todas las opciones para comparar cobertura.")
    if q["deductible"].notna().sum() >= 2:
        d = q["deductible"]
        lo = int(d.idxmin())
        findings.append(f"Condiciones: el deducible más bajo es el de {labels[lo]} ({fmt_money(d[lo])}).")
    if q["coinsurance_pct"].notna().sum() >= 2:
        c = q["coinsurance_pct"]
        lo = int(c.idxmin())
        findings.append(f"Condiciones: el coaseguro más bajo es el de {labels[lo]} ({c[lo]:g}%).")
    nets = q["hospital_network"].dropna().unique()
    if len(nets) > 1:
        findings.append("Red hospitalaria distinta entre opciones: verifica que incluya los hospitales de preferencia del cliente.")
    today = today or today_mx()
    for i, vu in enumerate(q["valid_until"]):
        if vu is not None and not pd.isna(vu) and vu < today:
            findings.append(f"Vigencia: la cotización {labels[i]} ya venció; solicita una actualización a la aseguradora.")
    missing_pdf = [labels[i] for i, h in enumerate(q["has_pdf"]) if not h]
    if missing_pdf:
        findings.append("Respaldo: adjunta el PDF oficial de " + ", ".join(missing_pdf) + " antes de presentarlas.")
    findings.append("Las diferencias se basan únicamente en los datos capturados de las cotizaciones oficiales. "
                    "Revisa exclusiones y condiciones generales de cada aseguradora antes de recomendar.")
    return {"table": table, "findings": findings, "labels": labels}


def expiring(quotes: pd.DataFrame, days: int = 5, today: Optional[date] = None) -> pd.DataFrame:
    today = today or today_mx()
    if quotes.empty:
        return quotes
    vu = pd.to_datetime(quotes["valid_until"], errors="coerce")
    t = pd.Timestamp(today)
    mask = quotes["status"].isin(["Registrada", "Enviada"]) & vu.notna() & (vu >= t) & (vu <= t + pd.Timedelta(days=days))
    return quotes[mask]
