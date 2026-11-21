"""Revenue Intelligence — resultados de venta.

Distinción obligatoria:
  * PRIMA vendida  = lo que paga el cliente a la aseguradora (NO es ingreso del agente).
  * COMISIÓN esperada = comisión registrada al emitir la póliza.
  * COMISIÓN cobrada  = comisión efectivamente recibida (registrada por el agente).
Los ingresos del agente son las comisiones; el ROAS y la rentabilidad se calculan sobre comisiones.
"""
from __future__ import annotations

import pandas as pd

from services.metrics import (
    campaign_table,
    conversion_by,
    is_policy,
    is_quoted,
    overall_acquisition,
    product_conversion,
    safe_div,
)
from utils.config import STAGE_LOST, STAGES


def kpis(leads: pd.DataFrame, camps: pd.DataFrame, quotes: pd.DataFrame) -> dict:
    pol = leads[is_policy(leads)] if not leads.empty else leads
    ct = campaign_table(camps, leads)
    acq = overall_acquisition(ct)
    expected = float(pol["commission"].fillna(0).sum()) if len(pol) else 0.0
    collected = float(pol["commission_paid"].fillna(0).sum()) if len(pol) else 0.0
    premium = float(pol["policy_premium"].fillna(0).sum()) if len(pol) else 0.0
    n_quotes = len(quotes) if quotes is not None and len(quotes) else int(is_quoted(leads).sum()) if len(leads) else 0
    inv = acq["investment"]
    return {
        "prospects": len(leads),
        "quotes": n_quotes,
        "quoted_leads": int(is_quoted(leads).sum()) if len(leads) else 0,
        "policies": len(pol),
        "premium_sold": premium,
        "commission_expected": expected,
        "commission_collected": collected,
        "commission_pending": expected - collected,
        "collection_rate": safe_div(collected, expected, 100),
        "conversion": safe_div(len(pol), len(leads), 100),
        "investment": inv,
        "cac": safe_div(inv, len(pol)) if inv is not None else None,
        "roas_expected": safe_div(expected, inv),
        "roas_collected": safe_div(collected, inv),
        "net_profit_collected": (collected - inv) if inv is not None else None,
        "avg_premium": safe_div(premium, len(pol)),
        "avg_commission": safe_div(expected, len(pol)),
    }


def sales_by_campaign(leads: pd.DataFrame, camps: pd.DataFrame) -> pd.DataFrame:
    ct = campaign_table(camps, leads)
    if ct.empty:
        return ct
    rows = []
    for _, c in ct.iterrows():
        sub = leads[(leads["campaign_id"] == c["id"]) & is_policy(leads)] if not leads.empty else leads
        prem = float(sub["policy_premium"].fillna(0).sum()) if len(sub) else 0.0
        paid = float(sub["commission_paid"].fillna(0).sum()) if len(sub) else 0.0
        rows.append({"Campaña": c["Campaña"], "Plataforma": c["Plataforma"], "Leads": c["Leads"],
                     "Pólizas": c["Pólizas"], "Conversión %": c["Conversión %"], "Prima vendida": prem,
                     "Comisión esperada": c["Comisiones"], "Comisión cobrada": paid, "Inversión": c["Inversión"],
                     "CAC": c["CAC"], "ROAS (comisión esperada)": c["ROAS comisiones"],
                     "ROAS (comisión cobrada)": safe_div(paid, c["Inversión"]), "Origen de datos": c["Origen de datos"]})
    return pd.DataFrame(rows).sort_values(["Pólizas", "Comisión esperada"], ascending=False).reset_index(drop=True)


def sales_by_product(leads: pd.DataFrame) -> pd.DataFrame:
    pc = product_conversion(leads)
    if leads.empty:
        return pc
    pol = leads[is_policy(leads)]
    extra = pol.groupby("product").agg(**{"Prima vendida": ("policy_premium", "sum"),
                                          "Comisión cobrada": ("commission_paid", "sum")})
    pc = pc.merge(extra, left_on="Producto", right_index=True, how="left")
    pc = pc.rename(columns={"Comisiones": "Comisión esperada"})
    return pc


def buyer_profile(leads: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compara leads que contrataron vs. los que no, por atributo comercial (sin datos sensibles)."""
    if leads.empty:
        return {}
    df = leads.assign(Contrató=is_policy(leads))
    closed_or_active = df
    out = {}
    for col, label in (("source", "Fuente"), ("segment", "Segmento"), ("purchase_intent", "Intención declarada"),
                       ("budget_range", "Presupuesto"), ("diagnostic_completed", "Completó diagnóstico"),
                       ("quote_requested", "Solicitó cotización")):
        g = closed_or_active.assign(**{col: closed_or_active[col].fillna("Sin dato").astype(str)})
        t = g.groupby(col).agg(Leads=("id", "count"), Contrataron=("Contrató", "sum")).reset_index()
        t["Conversión %"] = [safe_div(c, n, 100) for c, n in zip(t["Contrataron"], t["Leads"])]
        out[label] = t.rename(columns={col: label}).sort_values("Conversión %", ascending=False, na_position="last")
    pol = df[df["Contrató"]]
    if len(pol) and pol["policy_date"].notna().any():
        days = (pd.to_datetime(pol["policy_date"]) - pol["created_at"]).dt.days
        out["_dias_cierre"] = pd.DataFrame({"Días promedio a cierre": [float(days.mean())],
                                            "Mediana": [float(days.median())]})
    return out


def lost_opportunities(leads: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lost = leads[leads["stage"] == STAGE_LOST] if not leads.empty else leads
    if lost.empty:
        return {}
    by_stage = lost["max_stage_index"].map(lambda i: STAGES[int(i)] if 0 <= int(i) < len(STAGES) else "—")
    stage_df = by_stage.value_counts().rename_axis("Última etapa alcanzada").reset_index(name="Perdidos")
    reason_df = lost["lost_reason"].fillna("Sin motivo registrado").value_counts().rename_axis("Motivo") \
        .reset_index(name="Perdidos")
    quoted_lost = lost[lost["quote_amount"].notna()]
    return {"por_etapa": stage_df, "por_motivo": reason_df,
            "resumen": pd.DataFrame({"Perdidos": [len(lost)], "Con cotización": [len(quoted_lost)],
                                     "Prima cotizada perdida": [float(quoted_lost["quote_amount"].sum())]})}


def action_effectiveness(leads: pd.DataFrame, notes: pd.DataFrame, objections: pd.DataFrame) -> pd.DataFrame:
    """Conversión de los leads que recibieron cada tipo de acción vs. los que no.

    Es una asociación observada, no una relación causal.
    """
    if leads.empty:
        return pd.DataFrame(columns=["Acción comercial", "Leads con la acción", "Conversión con acción %",
                                     "Conversión sin acción %", "Diferencia (pp)"])
    conv = is_policy(leads)
    rows = []

    def add(label, mask):
        with_n = int(mask.sum())
        if with_n == 0:
            return
        c_with = safe_div(conv[mask].sum(), with_n, 100)
        c_without = safe_div(conv[~mask].sum(), int((~mask).sum()), 100)
        rows.append({"Acción comercial": label, "Leads con la acción": with_n, "Conversión con acción %": c_with,
                     "Conversión sin acción %": c_without,
                     "Diferencia (pp)": (c_with - c_without) if c_with is not None and c_without is not None else None})

    if notes is not None and not notes.empty:
        for kind in ["Llamada", "WhatsApp", "Correo", "Reunión"]:
            ids = set(notes.loc[notes["kind"] == kind, "lead_id"])
            add(f"Al menos una actividad: {kind}", leads["id"].isin(ids))
    add("Completó diagnóstico", leads["diagnostic_completed"].fillna(False).astype(bool))
    add("Cita agendada (alcanzó la etapa)", leads["max_stage_index"] >= STAGES.index("Cita agendada"))
    if objections is not None and not objections.empty:
        resolved = set(objections.loc[objections["status"] == "Resuelta", "lead_id"])
        add("Objeción registrada y resuelta", leads["id"].isin(resolved))
    out = pd.DataFrame(rows)
    return out.sort_values("Diferencia (pp)", ascending=False, na_position="last").reset_index(drop=True) if len(out) else out


def conversion_by_campaign(leads: pd.DataFrame) -> pd.DataFrame:
    if leads.empty:
        return pd.DataFrame()
    return conversion_by(leads.assign(campaign=leads["campaign"].fillna("Sin campaña")), "campaign") \
        .rename(columns={"campaign": "Campaña"})
