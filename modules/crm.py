"""CRM Comercial."""
from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd
import streamlit as st

from database import repository as repo
from database.session import session_scope
from services.scoring import recommended_action
from services.whatsapp import TEMPLATES, render_message, wa_link
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, flash, kpi, page_header, stage_strip
from utils.config import (ACTIVITY_KINDS, ALL_STAGES, BUDGET_RANGES, INTENT_LEVELS, PRIORITIES, PRODUCTS,
                          SEGMENTS, SOURCES, STAGE_LOST, today_mx)
from utils.dates import day
from utils.validation import EMAIL_RE, normalize_phone

EXPORT_COLS = ["id", "uid", "created_at", "name", "phone", "email", "city", "segment", "product", "budget_range",
               "est_purchase_date", "source", "campaign", "ad_id", "utm_source", "utm_medium", "utm_campaign",
               "utm_term", "utm_content", "stage", "score", "priority", "next_action", "next_action_date",
               "quote_amount", "quote_insurer", "policy_number", "policy_premium", "commission", "consent_contact",
               "consent_privacy", "privacy_version", "dup_status", "is_demo"]


def render() -> None:
    page_header("CRM Comercial", "Gestión de oportunidades",
                "Busca, filtra, edita, cambia etapas, registra actividades y agenda seguimiento. Todo se guarda en la base de datos.")
    demo_banner()
    leads = data.leads()
    if leads.empty:
        empty_state("No hay leads. Capta el primero desde Captación de Leads o la landing pública.")
        return

    counts = leads["stage"].value_counts()
    stage_strip({stg: int(counts.get(stg, 0)) for stg in ALL_STAGES})
    flash()

    f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
    q = f1.text_input("Buscar (nombre, teléfono, correo, ciudad, ID)", key="crm_q")
    stages = f2.multiselect("Etapa", ALL_STAGES, key="crm_stage", placeholder="Todas")
    prods = f3.multiselect("Producto", PRODUCTS, key="crm_prod", placeholder="Todas")
    prios = f4.multiselect("Prioridad", PRIORITIES, key="crm_prio", placeholder="Todas")
    srcs = f5.multiselect("Fuente", sorted(leads["source"].dropna().unique()), key="crm_src", placeholder="Todas")
    g1, g2, g3 = st.columns([1, 1, 2])
    camps = g1.multiselect("Campaña", sorted(leads["campaign"].dropna().unique()), key="crm_camp", placeholder="Todas")
    followup = g2.selectbox("Seguimiento", ["Todos", "Vencido / hoy", "Próximos 7 días", "Sin próxima acción"],
                            key="crm_follow")
    view = leads
    if q:
        ql = q.strip().lower()
        hay = (view["name"].str.lower().str.contains(ql, na=False, regex=False) |
               view["phone"].str.contains(ql, na=False, regex=False) |
               view["email"].fillna("").str.lower().str.contains(ql, regex=False) |
               view["city"].fillna("").str.lower().str.contains(ql, regex=False) |
               (view["id"].astype(str) == ql))
        view = view[hay]
    if stages:
        view = view[view["stage"].isin(stages)]
    if prods:
        view = view[view["product"].isin(prods)]
    if prios:
        view = view[view["priority"].isin(prios)]
    if srcs:
        view = view[view["source"].isin(srcs)]
    if camps:
        view = view[view["campaign"].isin(camps)]
    nad = day(view["next_action_date"])
    T = pd.Timestamp
    if followup == "Vencido / hoy":
        view = view[nad.notna() & (nad <= T(today_mx()))]
    elif followup == "Próximos 7 días":
        view = view[nad.notna() & (nad > T(today_mx())) & (nad <= T(today_mx() + timedelta(days=7)))]
    elif followup == "Sin próxima acción":
        view = view[view["next_action"].isna() & ~view["stage"].isin(["Póliza emitida", STAGE_LOST])]

    table = view[["id", "created_at", "name", "phone", "product", "city", "source", "campaign", "stage", "score",
                  "priority", "next_action", "next_action_date"]].rename(columns={
        "id": "ID", "created_at": "Fecha", "name": "Nombre", "phone": "Teléfono", "product": "Producto",
        "city": "Ciudad", "source": "Fuente", "campaign": "Campaña", "stage": "Etapa", "score": "Score",
        "priority": "Prioridad", "next_action": "Próxima acción", "next_action_date": "Fecha acción"})
    g3.caption(f"{len(view):,} de {len(leads):,} leads")
    event = st.dataframe(table, use_container_width=True, hide_index=True, height=360, on_select="rerun",
                         selection_mode="single-row", key="crm_table",
                         column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YY"),
                                        "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                                        "Fecha acción": st.column_config.DateColumn(format="DD/MM/YY")})
    export = view[[c for c in EXPORT_COLS if c in view.columns]]
    if st.download_button("Exportar CSV (vista filtrada)", csv_bytes(export), "crm_leads.csv", "text/csv"):
        with session_scope() as s:
            repo.audit(s, data.current_user(), "Exportar CRM", f"{len(export)} registros")

    rows = event.selection.rows if event and event.selection else []
    lead_id = int(view.iloc[rows[0]]["id"]) if rows else st.session_state.get("crm_lead_id")
    if lead_id not in set(leads["id"]):
        st.caption("Selecciona un lead de la tabla para ver y editar su ficha.")
        return
    st.session_state["crm_lead_id"] = lead_id
    _detail(lead_id)


def _detail(lead_id: int) -> None:
    user = data.current_user()
    with session_scope() as s:
        lead = repo.get_lead(s, lead_id)
        L = {c: getattr(lead, c) for c in repo.LEAD_COLUMNS}
        L["campaign_name"] = lead.campaign.name if lead.campaign else None
        notes = repo.notes_df(s, lead_id)
        consents = repo.consents_df(s, lead_id)
        camps = repo.campaign_options(s, "todos" if L["is_demo"] else "reales")
    settings = data.settings()

    st.divider()
    h1, h2 = st.columns([3, 1])
    h1.markdown(f"### #{L['id']} · {L['name']}")
    h1.caption(f"{L['product']} · {L['city'] or '—'} · Fuente: {L['source'] or '—'} · Campaña: "
               f"{L['campaign_name'] or '—'} · Anuncio: {L['ad_id'] or '—'} · Canal: {L['capture_channel']}")
    with h2:
        kpi("Lead Score", f"{L['score']}/100", L["priority"])
    if L["dup_status"]:
        st.warning(f"{L['dup_status']} (lead original #{L['duplicate_of']}). Revísalo en Captación → Duplicados.")
    st.info(f"**Acción recomendada:** {recommended_action(L)}")

    t1, t2, t3, t4, t5, t6 = st.tabs(["Etapa y seguimiento", "Actividades y notas", "Cotización y póliza",
                                      "Editar datos", "WhatsApp", "Score y consentimiento"])
    with t1:
        with st.form(f"stage_{lead_id}"):
            c1, c2 = st.columns(2)
            stage = c1.selectbox("Etapa", ALL_STAGES, index=ALL_STAGES.index(L["stage"]))
            lost_reason = c2.text_input("Motivo de pérdida (si aplica)", value=L["lost_reason"] or "")
            if st.form_submit_button("Cambiar etapa", type="primary"):
                with session_scope() as s:
                    repo.change_stage(s, lead_id, stage, author=user, lost_reason=lost_reason or None)
                data.bump()
                st.rerun()
        with st.form(f"next_{lead_id}"):
            c1, c2 = st.columns([2, 1])
            action = c1.text_input("Próxima acción", value=L["next_action"] or "")
            when = c2.date_input("Fecha de seguimiento", value=L["next_action_date"] or today_mx() + timedelta(days=1),
                                 format="DD/MM/YYYY")
            if st.form_submit_button("Agendar seguimiento"):
                with session_scope() as s:
                    repo.set_next_action(s, lead_id, action, when, author=user)
                data.bump()
                st.rerun()
    with t2:
        with st.form(f"note_{lead_id}", clear_on_submit=True):
            c1, c2 = st.columns([1, 3])
            kind = c1.selectbox("Tipo de actividad", ACTIVITY_KINDS)
            text = c2.text_area("Detalle", height=80, placeholder="Ej. Llamada: le interesa cobertura familiar…")
            if st.form_submit_button("Registrar actividad"):
                try:
                    with session_scope() as s:
                        repo.add_note(s, lead_id, text, kind=kind, author=user)
                    data.bump()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        st.dataframe(notes, use_container_width=True, hide_index=True,
                     column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YY HH:mm")})
    with t3:
        c1, c2 = st.columns(2)
        with c1, st.form(f"quote_{lead_id}"):
            st.markdown("**Registrar cotización**")
            amount = st.number_input("Prima anual cotizada (MXN)", min_value=0.0, value=float(L["quote_amount"] or 0),
                                     step=500.0)
            insurer = st.text_input("Aseguradora", value=L["quote_insurer"] or "")
            qdate = st.date_input("Fecha de cotización", value=L["quote_date"] or today_mx(), format="DD/MM/YYYY")
            if st.form_submit_button("Guardar cotización"):
                try:
                    with session_scope() as s:
                        repo.register_quote(s, lead_id, amount, insurer, qdate, author=user)
                    data.bump()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        with c2, st.form(f"policy_{lead_id}"):
            st.markdown("**Registrar póliza emitida**")
            number = st.text_input("Número de póliza", value=L["policy_number"] or "")
            premium = st.number_input("Prima anual (MXN)", min_value=0.0,
                                      value=float(L["policy_premium"] or L["quote_amount"] or 0), step=500.0)
            commission = st.number_input("Comisión (MXN)", min_value=0.0, value=float(L["commission"] or 0), step=100.0)
            pdate = st.date_input("Fecha de emisión", value=L["policy_date"] or today_mx(), format="DD/MM/YYYY")
            if st.form_submit_button("Registrar póliza", type="primary"):
                try:
                    with session_scope() as s:
                        repo.register_policy(s, lead_id, number, premium, commission, pdate, author=user)
                    data.bump()
                    flash("Póliza registrada. Indicadores actualizados.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with t4:
        with st.form(f"edit_{lead_id}"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Nombre", value=L["name"])
            phone = c2.text_input("Teléfono", value=L["phone"])
            email = c3.text_input("Correo", value=L["email"] or "")
            c4, c5, c6 = st.columns(3)
            city = c4.text_input("Ciudad", value=L["city"] or "")
            product = c5.selectbox("Producto", PRODUCTS, index=PRODUCTS.index(L["product"]))
            segment = c6.selectbox("Segmento", [None] + SEGMENTS,
                                   index=([None] + SEGMENTS).index(L["segment"]) if L["segment"] in SEGMENTS else 0,
                                   format_func=lambda x: x or "Sin dato")
            c7, c8, c9 = st.columns(3)
            budget = c7.selectbox("Presupuesto", [None] + BUDGET_RANGES,
                                  index=([None] + BUDGET_RANGES).index(L["budget_range"]) if L["budget_range"] in BUDGET_RANGES else 0,
                                  format_func=lambda x: x or "Sin dato")
            intent = c8.selectbox("Intención de contratación", INTENT_LEVELS,
                                  index=INTENT_LEVELS.index(L["purchase_intent"]) if L["purchase_intent"] in INTENT_LEVELS else 0)
            est = c9.date_input("Fecha estimada de contratación", value=L["est_purchase_date"], format="DD/MM/YYYY")
            c10, c11, c12 = st.columns(3)
            source = c10.selectbox("Fuente", SOURCES, index=SOURCES.index(L["source"]) if L["source"] in SOURCES else len(SOURCES) - 1)
            copts = {None: "Sin campaña"} | camps
            camp = c11.selectbox("Campaña", list(copts), format_func=lambda k: copts[k],
                                 index=list(copts).index(L["campaign_id"]) if L["campaign_id"] in copts else 0)
            owner = c12.text_input("Asesor responsable", value=L["owner"] or "")
            c13, c14 = st.columns(2)
            quote_req = c13.checkbox("Solicitó cotización", value=bool(L["quote_requested"]))
            contact_req = c14.checkbox("Solicitó contacto", value=bool(L["contact_requested"]))
            if st.form_submit_button("Guardar cambios", type="primary"):
                errs = []
                norm = normalize_phone(phone)
                if not norm:
                    errs.append("Teléfono inválido (10 dígitos).")
                if email and not EMAIL_RE.match(email.strip()):
                    errs.append("Correo inválido.")
                if len(name.strip()) < 3:
                    errs.append("Nombre inválido.")
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    with session_scope() as s:
                        repo.update_lead(s, lead_id, {
                            "name": name.strip(), "phone": norm, "email": email.strip().lower() or None,
                            "city": city.strip() or None, "product": product, "segment": segment,
                            "budget_range": budget, "purchase_intent": intent, "est_purchase_date": est,
                            "source": source, "campaign_id": camp, "owner": owner.strip() or None,
                            "quote_requested": quote_req, "contact_requested": contact_req}, author=user)
                    data.bump()
                    flash("Datos actualizados y score recalculado.")
                    st.rerun()
        with st.expander("Eliminar lead (solicitud ARCO de cancelación)"):
            st.caption("Úsalo solo cuando el titular solicite la cancelación de sus datos. Queda registrado en bitácora.")
            confirm = st.text_input("Escribe ELIMINAR para confirmar", key=f"del_{lead_id}")
            if st.button("Eliminar definitivamente", disabled=confirm != "ELIMINAR", key=f"delbtn_{lead_id}"):
                with session_scope() as s:
                    repo.delete_lead(s, lead_id, author=user)
                data.bump()
                st.session_state.pop("crm_lead_id", None)
                st.rerun()
    with t5:
        _whatsapp(L, settings, user)
    with t6:
        reasons = pd.DataFrame(json.loads(L["score_reasons"] or "[]"))
        if not reasons.empty:
            st.dataframe(reasons.rename(columns={"factor": "Factor", "puntos": "Puntos", "maximo": "Máximo",
                                                 "detalle": "Razón"}), hide_index=True, use_container_width=True)
        st.markdown(f"**Consentimiento de contacto:** {'Sí' if L['consent_contact'] else 'No'} · "
                    f"**Aviso de privacidad:** {'Sí' if L['consent_privacy'] else 'No'} "
                    f"(versión {L['privacy_version'] or '—'}) · **Fecha:** {L['consent_at'] or '—'}")
        st.markdown(f"**UTM:** source={L['utm_source'] or '—'} · medium={L['utm_medium'] or '—'} · "
                    f"campaign={L['utm_campaign'] or '—'} · term={L['utm_term'] or '—'} · content={L['utm_content'] or '—'} "
                    f"· click id={'sí' if L['click_id'] else '—'}  \n**ID único:** `{L['uid']}`")
        if not consents.empty:
            st.dataframe(consents, hide_index=True, use_container_width=True)


def _whatsapp(L: dict, settings: dict, user: str) -> None:
    if not L["consent_contact"]:
        st.warning("Este lead no tiene consentimiento de contacto registrado. No lo contactes por WhatsApp.")
        return
    c1, c2, c3 = st.columns([1.5, 1, 1])
    tpl = c1.selectbox("Plantilla", list(TEMPLATES), key=f"tpl_{L['id']}")
    fecha = c2.date_input("Fecha de cita", value=L["next_action_date"] or today_mx() + timedelta(days=1),
                          format="DD/MM/YYYY", key=f"wa_date_{L['id']}")
    hora = c3.text_input("Hora", value="10:00", key=f"wa_time_{L['id']}")
    msg = render_message(tpl, nombre=L["name"], asesor=settings.get("advisor_name"),
                         empresa=settings.get("company_name"), producto=L["product"].lower(),
                         fecha=fecha.strftime("%d/%m/%Y"), hora=hora)
    msg = st.text_area("Mensaje (editable)", value=msg, height=130, key=f"wa_msg_{L['id']}_{tpl}")
    link = wa_link(L["phone"], msg)
    if not link:
        st.error("El teléfono no es válido para WhatsApp.")
        return
    b1, b2 = st.columns(2)
    b1.link_button("Abrir WhatsApp con el mensaje", link, type="primary")
    if b2.button("Registrar que envié el mensaje", key=f"wa_log_{L['id']}"):
        with session_scope() as s:
            repo.add_note(s, L["id"], f"WhatsApp ({tpl}) enviado manualmente por el asesor:\n{msg}", kind="WhatsApp",
                          author=user)
        data.bump()
        st.success("Actividad registrada.")
    st.caption("La app solo abre WhatsApp con el mensaje precargado; el envío lo haces tú. "
               "No se envían mensajes automáticos.")
