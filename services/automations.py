"""Automatizaciones de seguimiento.

Las reglas generan RECORDATORIOS internos con el mensaje sugerido. No envían
mensajes: el asesor abre WhatsApp (wa.me) y envía manualmente. Solo se crean
recordatorios para leads con consentimiento de contacto.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from database import repository as repo
from services.whatsapp import render_message
from utils.config import CLOSED_STAGES, today_mx
from utils.dates import day

RULES = {
    "Nuevo sin contacto (24 h)": "Primer contacto",
    "Seguimiento de cotización": "Seguimiento de cotización",
    "Confirmación de cita": "Confirmación de cita",
    "Acción vencida": "Seguimiento",
    "Lead inactivo": "Recuperación de leads inactivos",
}


def evaluate_rules(leads: pd.DataFrame, today: Optional[date] = None, inactive_days: int = 14,
                   quote_days: int = 3) -> pd.DataFrame:
    """Devuelve (lead_id, regla, plantilla) para cada lead que cumple una regla."""
    today = today or today_mx()
    if leads.empty:
        return pd.DataFrame(columns=["lead_id", "rule", "template"])
    act = leads[~leads["stage"].isin(CLOSED_STAGES)].copy()
    created = day(act["created_at"])
    updated = day(act["updated_at"])
    nad = day(act["next_action_date"])
    qd = day(act["quote_date"])
    T = pd.Timestamp
    out = []

    def add(mask, rule):
        for lid in act.loc[mask, "id"]:
            out.append({"lead_id": int(lid), "rule": rule, "template": RULES[rule]})

    add((act["stage"] == "Nuevo") & (created <= T(today - timedelta(days=1))), "Nuevo sin contacto (24 h)")
    add((act["stage"] == "Cotización enviada") & qd.notna() & (qd <= T(today - timedelta(days=quote_days))),
        "Seguimiento de cotización")
    add((act["stage"] == "Cita agendada") & nad.notna() & (nad >= T(today)) & (nad <= T(today + timedelta(days=1))),
        "Confirmación de cita")
    add(nad.notna() & (nad < T(today)) & (act["stage"] != "Cita agendada"), "Acción vencida")
    add((updated <= T(today - timedelta(days=inactive_days))) & (act["stage"] != "Nuevo"), "Lead inactivo")
    res = pd.DataFrame(out, columns=["lead_id", "rule", "template"])
    # Un lead solo recibe la regla de mayor prioridad (orden de RULES)
    order = {r: i for i, r in enumerate(RULES)}
    res["_o"] = res["rule"].map(order)
    return res.sort_values("_o").drop_duplicates("lead_id").drop(columns="_o")


def run_rules(s: Session, leads: pd.DataFrame, settings: dict, author: str, today: Optional[date] = None) -> dict:
    today = today or today_mx()
    matches = evaluate_rules(leads, today, int(settings.get("inactive_days", 14) or 14),
                             int(settings.get("quote_followup_days", 3) or 3))
    created = skipped_consent = skipped_existing = 0
    by_id = leads.set_index("id")
    for m in matches.itertuples():
        lead = by_id.loc[m.lead_id]
        if not bool(lead["consent_contact"]):
            skipped_consent += 1
            continue
        if repo.pending_reminder_exists(s, m.lead_id, m.rule):
            skipped_existing += 1
            continue
        due = today
        if m.rule == "Confirmación de cita" and pd.notna(lead["next_action_date"]):
            due = lead["next_action_date"] - timedelta(days=1) if lead["next_action_date"] > today else today
        msg = render_message(m.template, nombre=lead["name"], asesor=settings.get("advisor_name"),
                             empresa=settings.get("company_name"), producto=str(lead["product"]).lower(),
                             fecha=lead["next_action_date"].strftime("%d/%m/%Y") if pd.notna(lead["next_action_date"]) else None)
        repo.add_reminder(s, m.lead_id, due, m.rule, msg, template=m.template, created_by=author)
        created += 1
    return {"evaluados": len(leads), "coincidencias": len(matches), "creados": created,
            "sin_consentimiento": skipped_consent, "ya_pendientes": skipped_existing}
