"""Sales Pipeline Automation — alertas internas y lista diaria de prioridades.

Las alertas se calculan en cada visita con los datos actuales del CRM y se muestran
dentro de Streamlit. No se envían notificaciones externas.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd

from utils.config import CLOSED_STAGES, today_mx
from utils.dates import day

ALERT_TYPES = {
    "Lead nuevo sin contactar": "Haz el primer contacto (llamada o WhatsApp) y registra la actividad.",
    "Alta intención de compra": "Propón una cita y solicita cotizaciones oficiales.",
    "Cotización sin respuesta": "Pregunta si pudo revisarla y qué dudas tiene; ofrece una explicación guiada.",
    "Cita pendiente": "Confirma la cita y prepara preguntas y cotizaciones.",
    "Sin seguimiento": "Agenda una próxima acción concreta con fecha.",
    "Cotización por vencer": "Confirma la decisión o solicita a la aseguradora una cotización actualizada.",
    "Oportunidad próxima al cierre": "Resuelve objeciones pendientes y explica los pasos de emisión.",
}
PRIORITY_ORDER = {"Alta": 0, "Media": 1, "Baja": 2}
COLUMNS = ["lead_id", "Prospecto", "Producto", "Etapa", "Score", "Alerta", "Motivo", "Prioridad",
           "Acción recomendada", "Fecha de seguimiento", "Teléfono", "Consentimiento"]


def build_alerts(leads: pd.DataFrame, quotes: pd.DataFrame, objections: Optional[pd.DataFrame] = None,
                 today: Optional[date] = None, no_reply_days: int = 3, stale_days: int = 7,
                 expiring_days: int = 5) -> pd.DataFrame:
    today = today or today_mx()
    T = pd.Timestamp(today)
    if leads.empty:
        return pd.DataFrame(columns=COLUMNS)
    act = leads[~leads["stage"].isin(CLOSED_STAGES)].copy()
    created = day(act["created_at"])
    updated = day(act["updated_at"])
    nad = day(act["next_action_date"])
    last_contact = day(act["last_contact_at"])
    rows = []

    def add(row, alert, motivo, prioridad, fecha):
        rows.append({"lead_id": int(row["id"]), "Prospecto": row["name"], "Producto": row["product"],
                     "Etapa": row["stage"], "Score": int(row["score"]), "Alerta": alert, "Motivo": motivo,
                     "Prioridad": prioridad, "Acción recomendada": ALERT_TYPES[alert], "Fecha de seguimiento": fecha,
                     "Teléfono": row["phone"], "Consentimiento": bool(row["consent_contact"])})

    for i, r in act.iterrows():
        age = (T - created[i]).days if pd.notna(created[i]) else 0
        if r["stage"] == "Nuevo" and pd.isna(last_contact[i]):
            pr = "Alta" if age >= 1 or r["score"] >= 80 else "Media"
            add(r, "Lead nuevo sin contactar", f"Captado hace {age} día(s) y sin contacto registrado.", pr, today)
        if r["score"] >= 80 and r["stage"] in ("Nuevo", "Contactado", "Calificado"):
            add(r, "Alta intención de compra", f"Score {r['score']} en etapa {r['stage']}.", "Alta", today)
        if r["stage"] == "Cita agendada":
            if pd.notna(nad[i]) and nad[i] < T:
                add(r, "Cita pendiente", f"La cita estaba programada para el {nad[i]:%d/%m} y sigue sin actualizarse.",
                    "Alta", today)
            elif pd.notna(nad[i]) and nad[i] <= T + pd.Timedelta(days=2):
                add(r, "Cita pendiente", f"Cita el {nad[i]:%d/%m}.", "Alta" if nad[i] == T else "Media", nad[i].date())
            elif pd.isna(nad[i]):
                add(r, "Cita pendiente", "Etapa «Cita agendada» sin fecha registrada.", "Media", today)
        if r["stage"] == "Negociación":
            add(r, "Oportunidad próxima al cierre", "Prospecto en negociación.", "Alta",
                nad[i].date() if pd.notna(nad[i]) else today)
        if r["stage"] != "Nuevo" and (pd.isna(nad[i]) or nad[i] < T) and pd.notna(updated[i]) \
                and (T - updated[i]).days >= stale_days:
            add(r, "Sin seguimiento", f"Sin movimiento en {(T - updated[i]).days} días y sin próxima acción vigente.",
                "Media" if r["score"] >= 50 else "Baja", today)

    if quotes is not None and not quotes.empty:
        qa = quotes[quotes["lead_id"].isin(act["id"])].copy()
        sent = day(qa["sent_at"])
        created_q = day(qa["created_at"])
        responded = qa["responded_at"].isna() if "responded_at" in qa else True
        vu = day(qa["valid_until"])
        by_lead = act.set_index("id")
        for i, q in qa.iterrows():
            r = by_lead.loc[q["lead_id"]].copy()
            r["id"] = q["lead_id"]
            ref = sent[i] if pd.notna(sent[i]) else created_q[i]
            if q["status"] in ("Registrada", "Enviada") and responded[i] and pd.notna(ref) \
                    and (T - ref).days >= no_reply_days:
                add(r, "Cotización sin respuesta",
                    f"Cotización #{q['id']} ({q['insurer']}) {q['status'].lower()} hace {(T - ref).days} días sin respuesta.",
                    "Alta" if r["score"] >= 50 else "Media", today)
            if q["status"] in ("Registrada", "Enviada") and pd.notna(vu[i]) and T <= vu[i] <= T + pd.Timedelta(days=expiring_days):
                add(r, "Cotización por vencer", f"Cotización #{q['id']} ({q['insurer']}) vence el {vu[i]:%d/%m}.",
                    "Alta", today)
            if q["status"] == "Aceptada" and r["stage"] != "Póliza emitida":
                add(r, "Oportunidad próxima al cierre", f"Cotización #{q['id']} aceptada: falta emitir la póliza.",
                    "Alta", today)
        if objections is not None and not objections.empty:
            pend = objections[(objections["status"] == "Pendiente") & objections["lead_id"].isin(act["id"])]
            for lid in pend["lead_id"].unique():
                r = by_lead.loc[lid].copy()
                r["id"] = lid
                if r["stage"] in ("Cotización enviada", "Negociación"):
                    add(r, "Oportunidad próxima al cierre", "Tiene objeciones pendientes en etapa avanzada.", "Alta", today)

    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    df = df.drop_duplicates(["lead_id", "Alerta"])
    df["_p"] = df["Prioridad"].map(PRIORITY_ORDER)
    return df.sort_values(["_p", "Score"], ascending=[True, False]).drop(columns="_p").reset_index(drop=True)


def daily_priorities(alerts: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Un renglón por prospecto (su alerta más importante), ordenado por prioridad y score."""
    if alerts.empty:
        return alerts
    first = alerts.drop_duplicates("lead_id", keep="first")
    counts = alerts.groupby("lead_id").size()
    first = first.assign(**{"Alertas": first["lead_id"].map(counts)})
    return first.head(limit).reset_index(drop=True)


def summary(alerts: pd.DataFrame) -> dict:
    if alerts.empty:
        return {"total": 0, "alta": 0, "por_tipo": {}}
    return {"total": int(alerts["lead_id"].nunique()), "alta": int(alerts.loc[alerts["Prioridad"] == "Alta", "lead_id"].nunique()),
            "por_tipo": alerts["Alerta"].value_counts().to_dict()}
