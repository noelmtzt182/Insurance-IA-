"""AI Lead Acquisition — motor de adquisición (A demanda, B campañas, C captura, D optimización)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from database import repository as repo
from database.session import session_scope
from integrations import google_ads, meta_ads
from services import capture, demand, metrics as m, optimization
from services.campaign_generator import build_utm_url
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, kpi_row, page_header
from utils.config import OBJECTIVES, PRODUCT_VIDA, SEGMENTS, STATES, STATES_CITIES
from utils.theme import SERIES


def render() -> None:
    page_header("AI Lead Acquisition", "Motor de adquisición de clientes",
                "Detecta demanda, genera campañas, captura leads con atribución y optimiza la inversión.")
    demo_banner()
    leads = data.leads()
    camps = data.campaigns()
    ct = m.campaign_table(camps, leads)
    acq = m.overall_acquisition(ct)
    with session_scope() as s:
        n_plans = len(repo.plans_df(s, data.data_mode()))
        n_kw = len(repo.keywords_df(s, data.data_mode()))
    kpi_row([
        ("Oportunidades guardadas", m.fmt_int(n_kw), "Motor A"),
        ("Propuestas de campaña", m.fmt_int(n_plans), "Motor B"),
        ("Leads atribuidos a campañas", m.fmt_int(int(leads["campaign_id"].notna().sum()) if not leads.empty else 0), "Motor C"),
        ("CPL global", m.fmt_money(acq["CPL"], 2), "Motor D"),
        ("ROAS comisiones", m.fmt_ratio(acq["ROAS"]), "Motor D"),
    ])
    st.write("")
    tab_a, tab_b, tab_c, tab_d = st.tabs(["A · Demand Intelligence", "B · Campaign Generator",
                                          "C · Automated Lead Capture", "D · Acquisition Optimization"])
    with tab_a:
        _demand()
    with tab_b:
        st.markdown("Genera campañas completas (segmentación, palabras clave, anuncios, landing, pruebas A/B y KPIs) "
                    "con IA o plantillas, edítalas, apruébalas y expórtalas.")
        page = st.session_state.get("_pages", {}).get("generator")
        if page:
            st.page_link(page, label="Abrir AI Campaign Generator →")
        with session_scope() as s:
            plans = repo.plans_df(s, data.data_mode())
        if plans.empty:
            empty_state("Aún no hay propuestas generadas.")
        else:
            st.dataframe(plans, use_container_width=True, hide_index=True)
    with tab_c:
        _capture(camps, leads)
    with tab_d:
        _optimization(ct, leads)


def _demand() -> None:
    st.markdown("Identifica búsquedas con intención comercial. **Sin Keyword Planner conectado, las propuestas son "
                "heurísticas: no se muestran volúmenes, CPC ni competencia.**")
    st.caption(f"Google Ads Keyword Planner: {google_ads.status()}")
    with st.form("demand_form"):
        c1, c2, c3 = st.columns(3)
        line = c1.selectbox("Producto / línea", list(demand.LINES))
        state = c2.selectbox("Estado", ["Todo México"] + STATES)
        cities = STATES_CITIES.get(state, [])
        city = c3.selectbox("Ciudad", ["(todas)"] + cities) if cities else None
        c4, c5, c6 = st.columns(3)
        segment = c4.selectbox("Segmento comercial", ["General"] + SEGMENTS)
        budget = c5.number_input("Presupuesto mensual (MXN)", min_value=0.0, step=1000.0, value=15000.0)
        objective = c6.selectbox("Objetivo de campaña", OBJECTIVES)
        ok = st.form_submit_button("Identificar oportunidades", type="primary")
    if ok:
        df = demand.generate_opportunities(line, None if segment == "General" else segment,
                                           None if not city or city == "(todas)" else city,
                                           None if state == "Todo México" else state, objective, budget)
        if google_ads.is_configured() and not df.empty:
            try:
                metrics = {r["keyword"].lower(): r for r in google_ads.keyword_ideas(df["keyword"].head(20).tolist())}
                for i, row in df.iterrows():
                    mt = metrics.get(row["keyword"].lower())
                    if mt:
                        for col in ("avg_monthly_searches", "competition", "low_bid", "high_bid"):
                            df.at[i, col] = mt[col]
                        df.at[i, "source"] = demand.SOURCE_KEYWORD_PLANNER
            except Exception as exc:  # noqa: BLE001
                st.warning(f"No se pudieron obtener métricas de Keyword Planner: {exc}")
        st.session_state["demand_df"] = df
        st.session_state["demand_budget"] = budget
    df = st.session_state.get("demand_df")
    if df is None or df.empty:
        return
    n_high = int((df["priority"] == "Alta").sum())
    st.info(demand.budget_guidance(st.session_state.get("demand_budget"), n_high))
    show = df.rename(columns=demand.DISPLAY_COLUMNS)
    st.dataframe(show, use_container_width=True, hide_index=True,
                 column_config={"Actualización": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
    c1, c2 = st.columns([1, 1])
    if c1.button("Guardar oportunidades en la base de datos"):
        with session_scope() as s:
            n = repo.save_keywords(s, df.to_dict("records"), is_demo=data.write_mode_is_demo())
        st.success(f"{n} oportunidades guardadas.")
    c2.download_button("Exportar CSV", csv_bytes(show), "oportunidades_busqueda.csv", "text/csv")

    with st.expander("Oportunidades guardadas"):
        with session_scope() as s:
            saved = repo.keywords_df(s, data.data_mode())
        if saved.empty:
            st.caption("Sin oportunidades guardadas.")
        else:
            st.dataframe(saved.drop(columns=["id"]).rename(columns=demand.DISPLAY_COLUMNS),
                         use_container_width=True, hide_index=True)


def _capture(camps: pd.DataFrame, leads: pd.DataFrame) -> None:
    st.markdown("Todos los canales pasan por el mismo motor: validación, consentimiento, atribución UTM, "
                "deduplicación (sin borrar registros) y Lead Score.")
    status = pd.DataFrame([
        {"Canal": "Landing pública (/registro)", "Estado": "Activo", "Notas": "Lee utm_*, ad_id, gclid/fbclid"},
        {"Canal": "Formulario interno (Captación)", "Estado": "Activo", "Notas": "Consentimiento documentado"},
        {"Canal": "Importación CSV", "Estado": "Activo", "Notas": "Requiere consentimiento por fila o declarado"},
        {"Canal": "Google Ads Lead Forms", "Estado": "Receptor disponible", "Notas":
            "Webhook en integrations/webhook_server.py (requiere GOOGLE_LEAD_FORM_KEY)"},
        {"Canal": "Meta Lead Ads", "Estado": meta_ads.status(), "Notas": "Sincronización manual desde esta pestaña"},
        {"Canal": "Formularios externos", "Estado": "Receptor disponible", "Notas": "POST firmado con HMAC (WEBHOOK_SECRET)"},
    ])
    st.dataframe(status, use_container_width=True, hide_index=True)

    st.markdown("##### Constructor de enlaces con UTM")
    settings = data.settings()
    base = settings.get("public_url") or "http://localhost:8501"
    if camps.empty:
        st.caption("Registra o aprueba una campaña para generar sus enlaces rastreables.")
    else:
        c1, c2 = st.columns([2, 1])
        cid = c1.selectbox("Campaña", camps["id"].tolist(),
                           format_func=lambda i: camps.set_index("id").loc[i, "name"], key="utm_camp")
        content = c2.text_input("utm_content / ID de anuncio", value="anuncio-a", key="utm_content")
        row = camps.set_index("id").loc[cid]
        url = build_utm_url(base, row["platform"], row["slug"], content)
        st.code(url, language=None)
        if not settings.get("public_url"):
            st.caption("Configura la URL pública de la app en Configuración → Negocio para generar enlaces definitivos.")

    st.markdown("##### Meta Lead Ads")
    if not meta_ads.is_configured():
        st.caption("Sin credenciales de Meta. Agrega `[meta]` en st.secrets para sincronizar formularios instantáneos.")
    else:
        default_product = st.selectbox("Producto para leads sin producto en el formulario",
                                       [PRODUCT_VIDA, "Gastos médicos mayores"], key="meta_prod")
        if st.button("Sincronizar leads de Meta ahora"):
            report = {"creados": 0, "duplicados": 0, "errores": 0}
            try:
                for form_id in meta_ads._cfg()["form_ids"]:
                    for raw in meta_ads.fetch_leads(form_id):
                        raw.update({"email_required": False, "city": raw.get("city") or "Sin dato",
                                    "product": default_product, "consent_contact": True, "consent_privacy": True,
                                    "contact_requested": True})
                        with session_scope() as s:
                            if raw.get("external_id") and repo.external_id_exists(s, raw["external_id"]):
                                continue
                            lid, errors, dup = capture.ingest(s, raw, channel="meta_lead_ads", author=data.current_user())
                        report["creados" if lid else "errores"] += 1
                        report["duplicados"] += int(dup)
                data.bump()
                st.success(f"Sincronización completa: {report}")
            except RuntimeError as exc:
                st.error(str(exc))


def _optimization(ct: pd.DataFrame, leads: pd.DataFrame) -> None:
    st.markdown("Recomendaciones basadas en reglas y en tus datos. **La app no modifica presupuestos ni publica "
                "campañas**: cada acción requiere tu aprobación en la plataforma publicitaria.")
    if ct.empty and leads.empty:
        empty_state("Sin datos para analizar.")
        return
    recs = optimization.recommendations(ct, leads)
    if recs.empty:
        st.success("No se detectaron alertas con las reglas actuales.")
    else:
        st.dataframe(recs, use_container_width=True, hide_index=True)
        st.download_button("Exportar recomendaciones (CSV)", csv_bytes(recs), "recomendaciones.csv", "text/csv")
    if not ct.empty:
        show = ct[["Campaña", "Plataforma", "Inversión", "Impresiones", "Clics", "CTR %", "CPC", "Leads", "Calificados",
                   "Citas", "Cotizaciones", "Pólizas", "CAC", "Comisiones", "ROAS comisiones", "Origen de datos"]]
        st.dataframe(show, use_container_width=True, hide_index=True, column_config={
            "Inversión": st.column_config.NumberColumn(format="$%,.0f"),
            "CPC": st.column_config.NumberColumn(format="$%.2f"), "CAC": st.column_config.NumberColumn(format="$%,.0f"),
            "Comisiones": st.column_config.NumberColumn(format="$%,.0f"),
            "CTR %": st.column_config.NumberColumn(format="%.2f%%"),
            "ROAS comisiones": st.column_config.NumberColumn(format="%.2fx")})
        plot = ct.dropna(subset=["CPL"])
        if not plot.empty:
            fig = px.scatter(plot, x="CPL", y="Conversión %", size="Leads", hover_name="Campaña",
                             title="CPL vs conversión por campaña (tamaño = leads)")
            fig.update_traces(marker=dict(color=SERIES[0], line=dict(color="#FFFFFF", width=2)))
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if not leads.empty and leads["ad_id"].notna().any():
        st.markdown("##### Calidad de lead por anuncio")
        g = leads.dropna(subset=["ad_id"]).groupby("ad_id").agg(
            Leads=("id", "count"), Score_promedio=("score", "mean"),
            Calificados=("max_stage_index", lambda x: int((x >= 2).sum())),
            Pólizas=("stage", lambda x: int((x == "Póliza emitida").sum()))).reset_index()
        g["% calificados"] = g["Calificados"] / g["Leads"] * 100
        st.dataframe(g.sort_values("Leads", ascending=False).rename(columns={"ad_id": "Anuncio (utm_content)",
                                                                             "Score_promedio": "Score promedio"}),
                     use_container_width=True, hide_index=True,
                     column_config={"Score promedio": st.column_config.NumberColumn(format="%.0f"),
                                    "% calificados": st.column_config.NumberColumn(format="%.0f%%")})
