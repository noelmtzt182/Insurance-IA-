"""AI Sales Intelligence."""
from __future__ import annotations

import streamlit as st

from integrations import llm
from services import insights
from utils import data
from utils.components import csv_bytes, demo_banner, page_header


def render() -> None:
    page_header("AI Sales Intelligence", "Asistente de inteligencia comercial",
                "Respuestas calculadas con tus datos reales. La IA (opcional) solo explica cifras ya calculadas.")
    demo_banner()
    leads = data.leads()
    camps = data.campaigns()
    ai = llm.is_configured()
    st.caption("Modo: " + (f"cálculo determinístico + explicación con IA ({llm.model_name()})" if ai
                           else "cálculo determinístico (configura ANTHROPIC_API_KEY para explicaciones en lenguaje natural)"))

    st.markdown("##### Preguntas frecuentes")
    keys = list(insights.QUESTIONS)
    cols = st.columns(2)
    for i, k in enumerate(keys):
        if cols[i % 2].button(insights.QUESTIONS[k][0], key=f"q_{k}", use_container_width=True):
            st.session_state["sales_q"] = k
            st.session_state["sales_text"] = insights.QUESTIONS[k][0]
            st.session_state.pop("sales_ai_answer", None)

    with st.form("free_q"):
        text = st.text_input("O escribe tu pregunta", placeholder="Ej. ¿Qué campañas debería optimizar este mes?")
        ok = st.form_submit_button("Preguntar")
    if ok and text.strip():
        key = insights.route_question(text)
        st.session_state["sales_text"] = text.strip()
        st.session_state["sales_q"] = key
        st.session_state.pop("sales_ai_answer", None)
        if key is None and not ai:
            st.warning("No identifiqué la pregunta. Prueba con una de las preguntas frecuentes.")

    key = st.session_state.get("sales_q")
    question = st.session_state.get("sales_text")
    if not question:
        return
    st.divider()
    st.markdown(f"#### {question}")
    if key:
        res = insights.run(key, leads, camps)
        st.markdown(res.answer)
        if not res.table.empty:
            st.dataframe(res.table, use_container_width=True, hide_index=True)
            st.download_button("Exportar resultado (CSV)", csv_bytes(res.table), f"analisis_{key}.csv", "text/csv")
        facts = res.facts
    else:
        st.info("Pregunta abierta: se usará el resumen agregado de todos los análisis.")
        facts = insights.global_facts(leads, camps)

    if ai:
        if st.button("Explicar con IA", type="primary"):
            with st.spinner("Generando explicación…"):
                try:
                    st.session_state["sales_ai_answer"] = llm.explain(question, facts)
                except RuntimeError as exc:
                    st.error(str(exc))
        if st.session_state.get("sales_ai_answer"):
            st.markdown("**✦ Explicación generada por IA** (basada solo en las cifras anteriores; sin datos personales)")
            st.markdown(st.session_state["sales_ai_answer"])
