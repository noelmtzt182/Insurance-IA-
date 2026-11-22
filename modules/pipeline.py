"""Sales Pipeline — alertas comerciales y lista diaria de prioridades."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from database import repository as repo
from database.session import session_scope
from services import pipeline
from services.whatsapp import render_message, wa_link
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, flash, kpi_row, page_header, stage_strip
from utils.config import ACTIVITY_KINDS, ALL_STAGES, today_mx

TEMPLATE_BY_ALERT = {
    "Solicitud de cita por confirmar": "Confirmación de cita",
    "Lead nuevo sin contactar": "Primer contacto",
    "Cotización sin respuesta": "Seguimiento de cotización",
    "Cita pendiente": "Confirmación de cita",
    "Cotización por vencer": "Seguimiento de cotización",
}


def current_alerts() -> pd.DataFrame:
    return pipeline.build_alerts(data.leads(), data.quotations(), data.objections())


def render() -> None:
    page_header("Sales Pipeline", "Prioridades comerciales de hoy",
                f"Alertas calculadas con los datos actuales del CRM al {today_mx():%d/%m/%Y}. "
                "Se muestran solo dentro de la app; no se envían notificaciones externas.")
    demo_banner()
    flash()
    leads = data.leads()
    if leads.empty:
        empty_state("No hay prospectos en este conjunto de datos.")
        return
    alerts = current_alerts()
    summ = pipeline.summary(alerts)
    kpi_row([("Prospectos con alertas", f"{summ['total']:,}", None), ("Prospectos con prioridad alta", f"{summ['alta']:,}", None),
             ("Leads activos", f"{int((~leads['stage'].isin(['Póliza emitida', 'Perdido'])).sum()):,}", None),
             ("Pólizas emitidas", f"{int((leads['stage'] == 'Póliza emitida').sum()):,}", None)])
    stage_strip(summ["por_tipo"])

    t1, t2 = st.tabs(["Lista diaria de prioridades", "Todas las alertas"])
    with t1:
        n = st.slider("Prospectos en la lista de hoy", 5, 50, 15, step=5)
        daily = pipeline.daily_priorities(alerts, n)
        if daily.empty:
            st.success("Sin alertas pendientes. ¡Buen trabajo!")
        else:
            st.dataframe(daily.drop(columns=["lead_id", "Teléfono", "Consentimiento"]), hide_index=True,
                         use_container_width=True,
                         column_config={"Fecha de seguimiento": st.column_config.DateColumn(format="DD/MM/YYYY")})
            st.download_button("Exportar lista del día (CSV)", csv_bytes(daily.drop(columns=["lead_id"])),
                               f"prioridades_{today_mx():%Y%m%d}.csv", "text/csv")
            st.markdown("##### Atender")
            for r in daily.to_dict("records"):
                _alert_card(r)
    with t2:
        if alerts.empty:
            st.caption("Sin alertas.")
        else:
            c1, c2 = st.columns(2)
            types = c1.multiselect("Tipo de alerta", sorted(alerts["Alerta"].unique()), placeholder="Todas")
            prios = c2.multiselect("Prioridad", ["Alta", "Media", "Baja"], placeholder="Todas")
            view = alerts
            if types:
                view = view[view["Alerta"].isin(types)]
            if prios:
                view = view[view["Prioridad"].isin(prios)]
            st.dataframe(view.drop(columns=["Teléfono"]), hide_index=True, use_container_width=True,
                         column_config={"Fecha de seguimiento": st.column_config.DateColumn(format="DD/MM/YYYY")})
            st.download_button("Exportar alertas (CSV)", csv_bytes(view), "alertas.csv", "text/csv")


def _alert_card(r: dict) -> None:
    lid = r["lead_id"]
    icon = {"Alta": "🔴", "Media": "🟠", "Baja": "⚪"}[r["Prioridad"]]
    with st.expander(f"{icon} {r['Prospecto']} · {r['Alerta']} · score {r['Score']}"):
        st.markdown(f"**Motivo:** {r['Motivo']}  \n**Acción recomendada:** {r['Acción recomendada']}  \n"
                    f"**Seguimiento:** {r['Fecha de seguimiento']:%d/%m/%Y} · Etapa: {r['Etapa']}")
        settings = data.settings()
        if r["Consentimiento"]:
            tpl = TEMPLATE_BY_ALERT.get(r["Alerta"], "Seguimiento")
            if r["Alerta"] == "Solicitud de cita por confirmar":
                first = str(r["Prospecto"]).split(" ")[0]
                fecha, _, horario = str(r["Cita solicitada"] or "").partition(" · ")
                msg = (f"Hola {first}, soy {settings.get('advisor_name')} de {settings.get('company_name')}. Recibí tu "
                       f"solicitud de asesoría gratuita para el {fecha} en horario de {horario.lower()}. "
                       "¿A qué hora exacta te queda mejor que te llame? Así te la confirmo.")
            else:
                msg = render_message(tpl, nombre=r["Prospecto"], asesor=settings.get("advisor_name"),
                                     empresa=settings.get("company_name"), producto=str(r["Producto"]).lower())
            link = wa_link(r["Teléfono"], msg)
            if link:
                st.link_button(f"Abrir WhatsApp ({tpl})", link)
        else:
            st.warning("Sin consentimiento de contacto.")
        c1, c2, c3 = st.columns(3)
        with c1, st.form(f"pl_act_{lid}_{r['Alerta']}", clear_on_submit=True):
            kind = st.selectbox("Actividad", ACTIVITY_KINDS, key=f"pk_{lid}_{r['Alerta']}")
            note = st.text_input("Detalle", key=f"pn_{lid}_{r['Alerta']}")
            if st.form_submit_button("Registrar"):
                with session_scope() as s:
                    repo.add_note(s, lid, note or f"{kind} realizada ({r['Alerta']}).", kind=kind,
                                  author=data.current_user())
                data.bump()
                flash("Actividad registrada.")
                st.rerun()
        with c2, st.form(f"pl_next_{lid}_{r['Alerta']}"):
            action = st.text_input("Próxima acción", value=r["Acción recomendada"][:200], key=f"pa_{lid}_{r['Alerta']}")
            when = st.date_input("Fecha", value=today_mx() + timedelta(days=2), format="DD/MM/YYYY",
                                 key=f"pd_{lid}_{r['Alerta']}")
            if st.form_submit_button("Programar"):
                with session_scope() as s:
                    repo.set_next_action(s, lid, action, when, author=data.current_user())
                data.bump()
                flash("Seguimiento programado.")
                st.rerun()
        with c3, st.form(f"pl_stage_{lid}_{r['Alerta']}"):
            stage = st.selectbox("Etapa", ALL_STAGES, index=ALL_STAGES.index(r["Etapa"]), key=f"ps_{lid}_{r['Alerta']}")
            if st.form_submit_button("Cambiar etapa"):
                with session_scope() as s:
                    repo.change_stage(s, lid, stage, author=data.current_user())
                data.bump()
                flash(f"Etapa actualizada a «{stage}».")
                st.rerun()
