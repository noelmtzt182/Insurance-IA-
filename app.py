"""INSURANCE LEADS AI — punto de entrada.

    streamlit run app.py

Rutas:
  /registro  → landing pública de captación (sin acceso a datos comerciales)
  /          → acceso al panel privado (requiere autenticación)
"""
from __future__ import annotations

import streamlit as st

from utils.config import APP_NAME, DATA_MODES

st.set_page_config(page_title=APP_NAME, page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

from database.session import init_db  # noqa: E402
from modules import (  # noqa: E402
    acquisition,
    automations,
    campaign_generator,
    campaigns,
    capture,
    coach,
    crm,
    dashboard,
    diagnosis,
    landing,
    login,
    market,
    pipeline,
    quotations,
    revenue,
    sales_agent,
    sales_ai,
    scoring,
    settings,
)
from utils.theme import inject_css  # noqa: E402


@st.cache_resource(show_spinner=False)
def _init() -> bool:
    init_db()
    return True


_init()
user = st.session_state.get("user")

landing_page = st.Page(landing.render, title="Landing pública", url_path="registro", icon=":material/public:")

if not user:
    # Visitantes: solo la página de acceso y la landing pública. Cualquier otra ruta no existe para ellos.
    login_page = st.Page(login.render, title="Acceso", url_path="acceso", icon=":material/lock:", default=True)
    nav = st.navigation([login_page, landing_page], position="hidden")
    inject_css(public=True)
    nav.run()
    st.stop()

pages = {
    "dashboard": st.Page(dashboard.render, title="Executive Dashboard", url_path="dashboard",
                         icon=":material/monitoring:", default=True),
    "acquisition": st.Page(acquisition.render, title="AI Lead Acquisition", url_path="adquisicion",
                           icon=":material/rocket_launch:"),
    "market": st.Page(market.render, title="Market Intelligence", url_path="mercado", icon=":material/travel_explore:"),
    "generator": st.Page(campaign_generator.render, title="AI Campaign Generator", url_path="generador",
                         icon=":material/auto_awesome:"),
    "capture": st.Page(capture.render, title="Captación de Leads", url_path="captacion", icon=":material/input:"),
    "diagnosis": st.Page(diagnosis.render, title="Diagnóstico Inteligente", url_path="diagnostico",
                         icon=":material/quiz:"),
    "scoring": st.Page(scoring.render, title="Lead Scoring", url_path="scoring", icon=":material/speed:"),
    "crm": st.Page(crm.render, title="CRM Comercial", url_path="crm", icon=":material/contacts:"),
    "sales_ai": st.Page(sales_ai.render, title="AI Sales Intelligence", url_path="inteligencia",
                        icon=":material/psychology:"),
    "campaigns": st.Page(campaigns.render, title="Campañas y ROI", url_path="campanas", icon=":material/paid:"),
    "automations": st.Page(automations.render, title="Automatizaciones", url_path="automatizaciones",
                           icon=":material/notifications_active:"),
    "sales_agent": st.Page(sales_agent.render, title="AI Sales Agent", url_path="agente-ventas",
                           icon=":material/support_agent:"),
    "quotations": st.Page(quotations.render, title="Cotizaciones", url_path="cotizaciones",
                          icon=":material/request_quote:"),
    "pipeline": st.Page(pipeline.render, title="Sales Pipeline", url_path="pipeline", icon=":material/view_kanban:"),
    "coach": st.Page(coach.render, title="AI Sales Coach", url_path="coach", icon=":material/school:"),
    "revenue": st.Page(revenue.render, title="Revenue Intelligence", url_path="ingresos",
                       icon=":material/account_balance:"),
    "settings": st.Page(settings.render, title="Configuración", url_path="configuracion", icon=":material/settings:"),
    "landing": landing_page,
}
st.session_state["_pages"] = pages

nav = st.navigation({
    "Dirección": [pages["dashboard"]],
    "Adquisición": [pages["acquisition"], pages["market"], pages["generator"], pages["capture"]],
    "Conversión": [pages["diagnosis"], pages["scoring"], pages["crm"], pages["sales_ai"]],
    "Ventas": [pages["pipeline"], pages["sales_agent"], pages["quotations"], pages["coach"], pages["revenue"]],
    "Rentabilidad": [pages["campaigns"], pages["automations"]],
    "Sistema": [pages["settings"], pages["landing"]],
}, expanded=True)
inject_css(public=False)

with st.sidebar:
    st.markdown(f'<div class="ila-brand"><div class="ila-brand-mark">IL</div><div>'
                f'<div class="ila-brand-name">{APP_NAME}</div>'
                f'<div class="ila-brand-tag">Vida · Gastos médicos mayores · México</div></div></div>',
                unsafe_allow_html=True)
    modes = list(DATA_MODES)
    current = st.session_state.get("data_mode", "reales")
    choice = st.selectbox("Datos", modes, index=modes.index(current), format_func=lambda k: DATA_MODES[k])
    if choice != current:
        st.session_state["data_mode"] = choice
        st.rerun()

    try:
        high = pipeline.pipeline.summary(pipeline.current_alerts())["alta"]
    except Exception:  # la alerta del menú nunca debe impedir usar la app
        high = 0
    if high:
        st.page_link(pages["pipeline"], label=f"🔔 {high:,} prospectos con prioridad alta")

nav.run()

with st.sidebar:
    st.divider()
    st.caption(f"Sesión: **{user['username']}** ({user['role']})")
    if st.button("Cerrar sesión", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
