"""AI Sales Coach — guías consultivas, manejo de objeciones y simulación."""
from __future__ import annotations

import streamlit as st

from database import sales_repository as srepo
from database.session import session_scope
from integrations import llm
from modules.sales_agent import lead_picker
from services import sales_coach as coach
from utils import data
from utils.components import demo_banner, flash, page_header
from utils.config import PRODUCTS, STAGES, STAGE_LOST


def render() -> None:
    page_header("AI Sales Coach", "Conversaciones comerciales consultivas",
                "Respuestas que explican el valor de la protección sin presionar, sin afirmaciones falsas y sin "
                "recomendar cancelar pólizas sin análisis.")
    demo_banner()
    flash()
    t1, t2, t3, t4, t5 = st.tabs(["Manejo de objeciones", "Descubrimiento y argumentos", "Seguimiento por etapa",
                                  "Simulación", "Objeciones registradas"])
    with t1:
        _objections()
    with t2:
        product = st.radio("Producto", PRODUCTS, horizontal=True, key="coach_prod")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Preguntas de descubrimiento")
            for q in coach.DISCOVERY_QUESTIONS[product]:
                st.markdown(f"- {q}")
        with c2:
            st.markdown("##### Argumentos de valor")
            for a in coach.VALUE_ARGUMENTS[product]:
                st.markdown(f"- {a}")
        st.caption("Los argumentos no incluyen cifras: precios y coberturas solo se presentan con cotizaciones oficiales.")
    with t3:
        for stage in STAGES + [STAGE_LOST]:
            st.markdown(f"**{stage}** — {coach.STAGE_FOLLOW_UP[stage]}")
    with t4:
        _simulation()
    with t5:
        _registered()


def _objections() -> None:
    c1, c2 = st.columns([1, 2])
    cat = c1.radio("Objeción", coach.OBJECTION_CATEGORIES, key="coach_cat")
    play = coach.OBJECTIONS[cat]
    with c2:
        st.markdown(f"#### «{play['example']}»")
        st.markdown(f"**Objetivo:** {play['intent']}")
        st.markdown("**Respuesta consultiva sugerida**")
        st.info(play["response"])
        st.markdown("**Preguntas para identificar la duda real**")
        for q in play["questions"]:
            st.markdown(f"- {q}")
        st.markdown("**Evita**")
        for a in play["avoid"]:
            st.markdown(f"- {a}")
        st.markdown(f"**Seguimiento recomendado:** {play['follow_up']}")

    st.markdown("##### Registrar esta objeción en un prospecto")
    leads = data.leads()
    if leads.empty:
        st.caption("No hay prospectos.")
        return
    lid = lead_picker(leads, "coach_lead", active_only=True)
    if lid is None:
        return
    with st.form("coach_obj", clear_on_submit=True):
        text = st.text_input("Lo que dijo el prospecto", value=play["example"])
        response = st.text_area("Respuesta que diste o darás", value=play["response"], height=90)
        status = st.radio("Estado", srepo.OBJECTION_STATUSES, horizontal=True)
        if st.form_submit_button("Registrar objeción", type="primary"):
            with session_scope() as s:
                srepo.add_objection(s, int(lid), cat, text, response, status, source="coach", author=data.current_user())
            data.bump()
            flash(f"Objeción «{cat}» registrada en el CRM.")
            st.rerun()


def _simulation() -> None:
    st.caption("Practica con un prospecto simulado. Cada respuesta se evalúa con criterios de venta consultiva.")
    name = st.selectbox("Escenario", list(coach.SCENARIOS), key="sim_scenario")
    sc = coach.SCENARIOS[name]
    state = st.session_state.setdefault("sim", {})
    if state.get("scenario") != name:
        state.clear()
        state.update({"scenario": name, "turn": 0, "log": []})
    for entry in state["log"]:
        with st.chat_message("user", avatar="🙂"):
            st.markdown(entry["prospect"])
        with st.chat_message("assistant", avatar="🧑‍💼"):
            st.markdown(entry["reply"])
            ev = entry["eval"]
            st.caption(f"Evaluación: **{ev['score']}/100 · {ev['level']}**")
            for f in ev["feedback"]:
                st.caption(f)
            if entry.get("ai"):
                st.caption("Comentario de IA: " + entry["ai"])
    if state["turn"] >= len(sc["turns"]):
        scores = [e["eval"]["score"] for e in state["log"]]
        st.success(f"Simulación terminada. Puntuación promedio: {sum(scores) / len(scores):.0f}/100.")
        if st.button("Reiniciar simulación"):
            state.update({"turn": 0, "log": []})
            st.rerun()
        return
    prospect, objection = sc["turns"][state["turn"]]
    with st.chat_message("user", avatar="🙂"):
        st.markdown(prospect)
    if objection:
        with st.expander("Pista del coach"):
            st.markdown(coach.OBJECTIONS[objection]["intent"])
    with st.form(f"sim_turn_{state['turn']}", clear_on_submit=True):
        reply = st.text_area("Tu respuesta", height=90)
        use_ai = st.checkbox("Agregar comentario de IA", value=False, disabled=not llm.is_configured())
        ok = st.form_submit_button("Responder", type="primary")
    if ok and reply.strip():
        ev = coach.evaluate_reply(reply, objection)
        ai = None
        if use_ai:
            try:
                ai = llm.coach_feedback(prospect, reply)
            except RuntimeError as e:
                ai = f"(No disponible: {e})"
        state["log"].append({"prospect": prospect, "reply": reply.strip(), "eval": ev, "ai": ai})
        state["turn"] += 1
        st.rerun()


def _registered() -> None:
    obj = data.objections()
    if obj.empty:
        st.caption("Sin objeciones registradas.")
        return
    c1, c2 = st.columns(2)
    c1.markdown("**Objeciones más frecuentes**")
    c1.dataframe(obj["category"].value_counts().rename_axis("Objeción").reset_index(name="Veces"), hide_index=True,
                 use_container_width=True)
    res = obj.groupby("category")["status"].apply(lambda s: (s == "Resuelta").mean() * 100).rename("% resueltas")
    c2.markdown("**Tasa de resolución**")
    c2.dataframe(res.reset_index().rename(columns={"category": "Objeción"}), hide_index=True, use_container_width=True,
                 column_config={"% resueltas": st.column_config.NumberColumn(format="%.0f%%")})
    pend = obj[obj["status"] == "Pendiente"]
    st.markdown(f"**Pendientes:** {len(pend):,}")
    st.dataframe(pend[["id", "lead_name", "category", "text", "created_at", "lead_stage"]].head(200), hide_index=True,
                 use_container_width=True)
    if not pend.empty:
        c1, c2, c3 = st.columns([2, 1, 1])
        oid = c1.selectbox("Objeción", pend["id"].tolist(),
                           format_func=lambda i: f"#{i} · {pend.set_index('id').loc[i, 'lead_name']} · "
                                                 f"{pend.set_index('id').loc[i, 'category']}")
        new = c2.selectbox("Nuevo estado", ["Resuelta", "No resuelta"])
        if c3.button("Actualizar"):
            with session_scope() as s:
                srepo.set_objection_status(s, int(oid), new)
            data.bump()
            st.rerun()
