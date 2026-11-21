"""Market Intelligence."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from integrations import llm
from services import market
from utils import data
from utils.components import demo_banner, page_header
from utils.config import CITIES, PRODUCTS, SEGMENTS
from utils.theme import SERIES


def render() -> None:
    page_header("Market Intelligence", "Segmentos y oportunidades para vender seguros en México",
                "Motor de reglas que combina tus datos verificados del CRM con hipótesis comerciales explícitas.")
    demo_banner()
    st.caption("Este módulo no extrae datos personales de redes sociales ni genera listas de contacto.")
    leads = data.leads()

    with st.form("market_form"):
        c1, c2, c3 = st.columns(3)
        product = c1.selectbox("Producto", ["Ambos"] + PRODUCTS)
        segment = c2.selectbox("Segmento", SEGMENTS)
        location = c3.selectbox("Ubicación", ["Todo México"] + CITIES)
        ok = st.form_submit_button("Analizar", type="primary")
    if ok or "market_result" not in st.session_state:
        st.session_state["market_result"] = market.analyze(
            leads, None if product == "Ambos" else product, segment, None if location == "Todo México" else location)
        st.session_state.pop("market_ai", None)
    res = st.session_state["market_result"]
    profile = market.SEGMENT_PROFILES[res["facts"]["segmento"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**✓ Información verificada (CRM)**")
        for line in res["verified"]:
            st.markdown(f"- {line}")
    with c2:
        st.markdown("**◐ Hipótesis comerciales**")
        for line in res["hypotheses"]:
            st.markdown(f"- {line}")
        st.markdown(f"- Productos con mayor afinidad: {', '.join(p.lower() for p in profile['products'])}.")
        st.caption("Supuestos por validar con tus propios resultados.")
    with c3:
        st.markdown("**→ Recomendaciones (reglas)**")
        for line in res["recommendations"]:
            st.markdown(f"- {line}")

    st.markdown("##### Análisis con IA")
    if llm.is_configured():
        if st.button("Generar análisis adicional con IA"):
            with st.spinner("Generando análisis…"):
                try:
                    st.session_state["market_ai"] = llm.market_analysis(res["facts"])
                except RuntimeError as exc:
                    st.error(str(exc))
        if st.session_state.get("market_ai"):
            st.markdown("**✦ Recomendaciones generadas por IA** (basadas solo en los datos anteriores)")
            st.markdown(st.session_state["market_ai"])
    else:
        st.caption("Configura ANTHROPIC_API_KEY en st.secrets para habilitar análisis en lenguaje natural.")

    st.markdown("##### Resultados por segmento (verificado)")
    seg = market.segment_overview(leads)
    if seg.empty:
        st.caption("Aún no hay leads con segmento registrado.")
    else:
        fig = px.bar(seg, x="Segmento", y="Conversión %", title="Conversión a póliza por segmento (%)",
                     hover_data=["Leads", "Pólizas"])
        fig.update_traces(marker_color=SERIES[0])
        fig.update_layout(height=340, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.dataframe(seg, use_container_width=True, hide_index=True,
                     column_config={"Conversión %": st.column_config.NumberColumn(format="%.1f%%"),
                                    "Comisiones": st.column_config.NumberColumn(format="$%,.0f")})

    with st.expander("Matriz de segmentos (hipótesis de trabajo)"):
        for name, p in market.SEGMENT_PROFILES.items():
            st.markdown(f"**{name}** — {p['need']}  \nCanales: {', '.join(p['channels'])}.  \nMensaje: «{p['message']}»")
