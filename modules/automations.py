"""Automatizaciones: reglas de seguimiento, recordatorios internos y plantillas WhatsApp."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import repository as repo
from database.session import session_scope
from integrations import whatsapp_cloud
from services import automations
from services.whatsapp import TEMPLATES, wa_link
from utils import data
from utils.components import demo_banner, page_header


def render() -> None:
    page_header("Automatizaciones", "Seguimiento comercial autorizado",
                "Las reglas crean recordatorios internos con mensajes sugeridos. Ningún mensaje se envía automáticamente.")
    demo_banner()
    settings = data.settings()
    st.caption(f"WhatsApp Business Platform: {whatsapp_cloud.status()}")

    t1, t2, t3 = st.tabs(["Recordatorios", "Reglas", "Plantillas"])
    with t2:
        rules = pd.DataFrame([
            {"Regla": "Nuevo sin contacto (24 h)", "Condición": "Etapa Nuevo y más de 24 h desde la captación",
             "Plantilla": "Primer contacto"},
            {"Regla": "Seguimiento de cotización", "Condición": f"Cotización enviada hace {settings['quote_followup_days']}+ días",
             "Plantilla": "Seguimiento de cotización"},
            {"Regla": "Confirmación de cita", "Condición": "Cita agendada para hoy o mañana", "Plantilla": "Confirmación de cita"},
            {"Regla": "Acción vencida", "Condición": "Fecha de próxima acción ya pasó", "Plantilla": "Seguimiento"},
            {"Regla": "Lead inactivo", "Condición": f"Sin movimiento en {settings['inactive_days']}+ días",
             "Plantilla": "Recuperación de leads inactivos"},
        ])
        st.dataframe(rules, hide_index=True, use_container_width=True)
        st.caption("Solo se generan recordatorios para leads con consentimiento de contacto. Los plazos se ajustan en "
                   "Configuración → Negocio.")
        leads = data.leads()
        preview = automations.evaluate_rules(leads, inactive_days=int(settings["inactive_days"]),
                                             quote_days=int(settings["quote_followup_days"]))
        st.write(f"Coincidencias actuales: **{len(preview):,}** leads.")
        if not preview.empty:
            st.dataframe(preview["rule"].value_counts().rename_axis("Regla").reset_index(name="Leads"),
                         hide_index=True)
        if st.button("Ejecutar reglas y crear recordatorios", type="primary", disabled=preview.empty):
            with session_scope() as s:
                rep = automations.run_rules(s, leads, settings, data.current_user())
            data.bump()
            st.success(f"Recordatorios creados: {rep['creados']} · ya pendientes: {rep['ya_pendientes']} · "
                       f"omitidos sin consentimiento: {rep['sin_consentimiento']}.")

    with t1:
        with session_scope() as s:
            rem = repo.reminders_df(s, data.data_mode(), status="Pendiente")
        if rem.empty:
            st.info("No hay recordatorios pendientes. Ejecuta las reglas en la pestaña «Reglas».")
        else:
            c1, c2 = st.columns([1, 3])
            rule_f = c1.selectbox("Filtrar por regla", ["Todas"] + sorted(rem["Regla"].unique()))
            view = rem if rule_f == "Todas" else rem[rem["Regla"] == rule_f]
            c2.caption(f"{len(view):,} pendientes")
            st.dataframe(view.drop(columns=["id", "lead_id", "Mensaje", "Estado", "Consentimiento"]),
                         hide_index=True, use_container_width=True, height=260)
            for r in view.head(25).to_dict("records"):
                with st.expander(f"{r['Vence']:%d/%m} · {r['Regla']} · {r['Lead']} (score {r['Score']})"):
                    msg = st.text_area("Mensaje", value=r["Mensaje"], key=f"rm_{r['id']}", height=110)
                    b1, b2, b3 = st.columns(3)
                    link = wa_link(r["Teléfono"], msg)
                    if link:
                        b1.link_button("Abrir WhatsApp", link)
                    else:
                        b1.caption("Teléfono inválido para WhatsApp")
                    if b2.button("Marcar como hecho", key=f"done_{r['id']}"):
                        with session_scope() as s:
                            repo.set_reminder_status(s, r["id"], "Hecho", data.current_user())
                            repo.add_note(s, r["lead_id"], f"Seguimiento ({r['Regla']}) realizado manualmente.",
                                          kind="WhatsApp", author=data.current_user())
                        data.bump()
                        st.rerun()
                    if b3.button("Descartar", key=f"dis_{r['id']}"):
                        with session_scope() as s:
                            repo.set_reminder_status(s, r["id"], "Descartado", data.current_user())
                        data.bump()
                        st.rerun()
            if len(view) > 25:
                st.caption("Se muestran los primeros 25; filtra por regla para ver el resto.")

    with t3:
        st.markdown("Plantillas para enlaces wa.me (envío manual). Variables: `{nombre}`, `{asesor}`, `{empresa}`, "
                    "`{producto}`, `{fecha}`, `{hora}`.")
        for name, text in TEMPLATES.items():
            st.markdown(f"**{name}**")
            st.code(text, language=None)
        st.caption("Para WhatsApp Business Platform, cada plantilla debe aprobarse en Meta con el nombre indicado en "
                   "services/whatsapp.py (CLOUD_TEMPLATE_NAMES) y el envío requiere consentimiento explícito.")
