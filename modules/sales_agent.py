"""AI Sales Agent — copiloto comercial por prospecto y conversación asistida."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from database import repository as repo
from database import sales_repository as srepo
from database.session import session_scope
from integrations import llm
from services import sales_agent as agent
from services import sales_coach
from services.whatsapp import wa_link
from utils import data
from utils.components import demo_banner, empty_state, flash, kpi_row, page_header
from utils.config import ALL_STAGES, APPOINTMENT_SLOTS, PRODUCTS, today_mx

SLOTS = APPOINTMENT_SLOTS


def lead_picker(leads: pd.DataFrame, key: str, active_only: bool = False) -> int | None:
    """Selector de prospecto compartido entre los módulos de ventas (recuerda la selección)."""
    opts = data.lead_options(leads, active_only=active_only)
    if not opts:
        return None
    ids = list(opts)
    cur = st.session_state.get("sales_lead_id")
    lid = st.selectbox("Prospecto", ids, index=ids.index(cur) if cur in ids else 0, format_func=lambda i: opts[i],
                       key=key)
    st.session_state["sales_lead_id"] = lid
    return lid


def render() -> None:
    page_header("AI Sales Agent", "Asistente comercial por prospecto",
                "Identifica necesidades e intención, recomienda acciones, prepara mensajes y registra todo en el CRM. "
                "Solo usa información validada: no inventa primas, coberturas ni condiciones.")
    demo_banner()
    flash()
    leads = data.leads()
    tabs = st.tabs(["Prospecto y recomendaciones", "Conversación asistida", "Historial comercial",
                    "Base de conocimiento validada"])
    with tabs[3]:
        _knowledge()
    if leads.empty:
        with tabs[0]:
            empty_state("No hay prospectos en este conjunto de datos.")
        return
    with tabs[0]:
        lid = lead_picker(leads, "agent_lead")
    with session_scope() as s:
        hist = srepo.lead_history(s, lid)
    lead = hist["lead"]
    settings = data.settings()
    with tabs[0]:
        _recommendations(lead, hist, settings)
    with tabs[1]:
        _conversation(lead, hist, settings)
    with tabs[2]:
        _history(hist)


def _recommendations(lead: dict, hist: dict, settings: dict) -> None:
    level, signals = agent.purchase_intent(lead)
    pending_obj = hist["objections"][hist["objections"]["status"] == "Pendiente"] if len(hist["objections"]) else []
    kpi_row([("Etapa", lead["stage"], None), ("Lead Score", f"{lead['score']}/100", lead["priority"]),
             ("Intención de contratación", level, None),
             ("Objeciones pendientes", str(len(pending_obj)), None)])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Necesidades de protección")
        for n in agent.protection_needs(lead, hist["diagnostics"]):
            st.markdown(f"- {n}")
    with c2:
        st.markdown("##### Señales de intención")
        for sgn in signals:
            st.markdown(f"- {sgn}")
    st.markdown("##### Siguientes acciones recomendadas")
    acts = pd.DataFrame(agent.next_actions(lead, hist["quotations"], hist["objections"]))
    st.dataframe(acts, hide_index=True, use_container_width=True,
                 column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})

    st.markdown("##### Acciones rápidas")
    a1, a2 = st.columns(2)
    with a1, st.form(f"agent_follow_{lead['id']}"):
        st.markdown("**Programar seguimiento**")
        action = st.text_input("Acción", value=acts.iloc[0]["Acción"][:200] if len(acts) else "")
        when = st.date_input("Fecha", value=today_mx() + timedelta(days=1), format="DD/MM/YYYY")
        if st.form_submit_button("Programar"):
            with session_scope() as s:
                repo.set_next_action(s, lead["id"], action, when, author=data.current_user())
            data.bump()
            flash("Seguimiento programado.")
            st.rerun()
    with a2, st.form(f"agent_stage_{lead['id']}"):
        st.markdown("**Cambiar estado comercial**")
        stage = st.selectbox("Etapa", ALL_STAGES, index=ALL_STAGES.index(lead["stage"]))
        reason = st.text_input("Motivo de pérdida (si aplica)")
        if st.form_submit_button("Actualizar etapa"):
            with session_scope() as s:
                repo.change_stage(s, lead["id"], stage, author=data.current_user(), lost_reason=reason or None)
            data.bump()
            flash(f"Etapa actualizada a «{stage}».")
            st.rerun()

    with st.form(f"agent_appt_{lead['id']}"):
        st.markdown("**Agendar cita con el agente**")
        c1, c2, c3 = st.columns([1, 1, 1])
        d = c1.date_input("Fecha", value=today_mx() + timedelta(days=2), format="DD/MM/YYYY")
        slot = c2.selectbox("Horario", SLOTS)
        confirmed = c3.checkbox("El prospecto ya confirmó", value=True)
        if st.form_submit_button("Registrar cita"):
            with session_scope() as s:
                srepo.request_appointment(s, lead["id"], d, slot, author=data.current_user(), confirm=confirmed)
            data.bump()
            flash("Cita registrada en el CRM." if confirmed else "Solicitud de cita registrada como recordatorio.")
            st.rerun()

    st.markdown("##### Mensajes preparados")
    if not lead["consent_contact"]:
        st.warning("Sin consentimiento de contacto registrado: no envíes mensajes a este prospecto.")
        return
    for title, msg in agent.prepared_messages(lead, settings, hist["objections"]).items():
        with st.expander(title):
            text = st.text_area("Mensaje", value=msg, key=f"pm_{lead['id']}_{title}", height=110)
            link = wa_link(lead["phone"], text)
            c1, c2 = st.columns(2)
            if link:
                c1.link_button("Abrir WhatsApp", link)
            if c2.button("Registrar envío manual", key=f"pmlog_{lead['id']}_{title}"):
                with session_scope() as s:
                    repo.add_note(s, lead["id"], f"Mensaje enviado manualmente ({title}):\n{text}", kind="WhatsApp",
                                  author=data.current_user())
                data.bump()
                flash("Interacción registrada en el CRM.")
                st.rerun()


def _conversation(lead: dict, hist: dict, settings: dict) -> None:
    st.caption("Pega o escribe el mensaje del prospecto (por ejemplo, de WhatsApp). El asistente sugiere una respuesta "
               "basada solo en fuentes validadas; tú decides si la envías. Todo queda registrado en el CRM.")
    msgs = hist["messages"]
    for m in msgs.to_dict("records")[-30:]:
        role = {"prospecto": "user", "asistente": "assistant", "agente": "assistant"}.get(m["role"], "assistant")
        with st.chat_message(role, avatar="🙂" if m["role"] == "prospecto" else ("🤖" if m["role"] == "asistente" else "🧑‍💼")):
            st.markdown(m["text"])
            if m["sources"]:
                st.caption("Fuente: " + "; ".join(m["sources"]))

    with session_scope() as s:
        kb = srepo.knowledge_items(s, lead["product"])
    with st.form(f"conv_{lead['id']}", clear_on_submit=True):
        text = st.text_area("Mensaje del prospecto", height=80)
        ok = st.form_submit_button("Analizar y sugerir respuesta", type="primary")
    if ok and text.strip():
        r = agent.respond(text, lead["product"], kb, lead["name"])
        draft = r.reply
        if llm.is_configured() and r.intent == "producto":
            item = next((k for k in kb if k["answer"] == r.reply), None)
            if item:
                try:
                    draft = llm.agent_draft(text, [item])
                except RuntimeError:
                    draft = r.reply
        with session_scope() as s:
            srepo.add_agent_message(s, lead["id"], "prospecto", text.strip(), intent=r.intent)
            repo.add_note(s, lead["id"], f"Mensaje del prospecto: «{text.strip()[:500]}»", kind="Nota",
                          author=data.current_user())
            if r.intent_signal == "Alta" and lead["purchase_intent"] != "Alta":
                repo.update_lead(s, lead["id"], {"purchase_intent": "Alta"}, author="asistente")
            if r.opt_out:
                repo.update_lead(s, lead["id"], {"contact_requested": False}, author="asistente")
                repo.add_note(s, lead["id"], "El prospecto pidió no ser contactado (BAJA). Revisa y revoca el consentimiento.",
                              kind="Sistema", author="asistente")
        st.session_state["agent_suggestion"] = {"lead": lead["id"], "reply": draft, "intent": r.intent,
                                                "objection": r.objection, "sources": r.sources,
                                                "handoff": r.handoff_suggested, "appt": r.appointment_suggested,
                                                "prospect_text": text.strip()}
        data.bump()
        st.rerun()

    sug = st.session_state.get("agent_suggestion")
    if not sug or sug["lead"] != lead["id"]:
        return
    st.markdown("##### Respuesta sugerida")
    st.caption(f"Intención detectada: **{sug['intent']}**" + (f" · Objeción: **{sug['objection']}**" if sug["objection"] else "")
               + (f" · Fuentes: {'; '.join(sug['sources'])}" if sug["sources"] else " · Sin fuente validada"))
    reply = st.text_area("Edita antes de enviar", value=sug["reply"], key=f"sugg_{lead['id']}", height=120)
    b1, b2, b3, b4 = st.columns(4)
    link = wa_link(lead["phone"], reply) if lead["consent_contact"] else None
    if link:
        b1.link_button("Abrir WhatsApp", link)
    if b2.button("Registrar respuesta", key="reg_reply"):
        with session_scope() as s:
            srepo.add_agent_message(s, lead["id"], "agente", reply, intent=sug["intent"], sources=sug["sources"])
            repo.add_note(s, lead["id"], f"Respuesta enviada al prospecto:\n{reply}", kind="WhatsApp",
                          author=data.current_user())
        st.session_state.pop("agent_suggestion", None)
        data.bump()
        flash("Respuesta registrada en el CRM.")
        st.rerun()
    if sug["objection"] and b3.button("Registrar objeción", key="reg_obj"):
        with session_scope() as s:
            srepo.add_objection(s, lead["id"], sug["objection"], text=sug["prospect_text"], response=reply,
                                source="asistente", author=data.current_user())
        data.bump()
        flash(f"Objeción «{sug['objection']}» registrada.")
        st.rerun()
    if b4.button("Transferir al agente humano", key="handoff"):
        with session_scope() as s:
            srepo.request_handoff(s, lead["id"], f"Mensaje: «{sug['prospect_text'][:200]}»", author=data.current_user())
        st.session_state.pop("agent_suggestion", None)
        data.bump()
        flash("Conversación transferida: se creó un recordatorio de atención personal para hoy.")
        st.rerun()
    if sug["handoff"]:
        st.info("El asistente no tiene información validada suficiente o el prospecto pidió atención personal: "
                "se recomienda transferir al agente humano.")
    if sug["objection"]:
        play = sales_coach.OBJECTIONS[sug["objection"]]
        with st.expander("Guía del AI Sales Coach para esta objeción"):
            st.markdown("**Preguntas sugeridas:**\n" + "\n".join(f"- {q}" for q in play["questions"]))
            st.markdown("**Evita:** " + "; ".join(play["avoid"]))


def _history(hist: dict) -> None:
    lead = hist["lead"]
    st.markdown(f"**{lead['name']}** · {lead['product']} · {lead['city'] or '—'} · Fuente {lead['source'] or '—'} · "
                f"Captado {lead['created_at']:%d/%m/%Y}")
    st.markdown("##### Cotizaciones")
    q = hist["quotations"]
    if q.empty:
        st.caption("Sin cotizaciones oficiales registradas.")
    else:
        st.dataframe(q[["id", "insurer", "plan_name", "premium_amount", "premium_period", "sum_insured",
                        "valid_until", "status"]], hide_index=True, use_container_width=True)
    st.markdown("##### Objeciones")
    o = hist["objections"]
    if o.empty:
        st.caption("Sin objeciones registradas.")
    else:
        st.dataframe(o[["created_at", "category", "text", "status", "source"]], hide_index=True, use_container_width=True)
    st.markdown("##### Diagnósticos")
    if not hist["diagnostics"]:
        st.caption("Sin diagnóstico.")
    for d in hist["diagnostics"]:
        st.markdown(f"- {d['fecha']:%d/%m/%Y} · {d['producto']} · necesidad {d['necesidad']} · intención {d['intencion']}")
    st.markdown("##### Actividades y notas")
    st.dataframe(hist["notes"], hide_index=True, use_container_width=True,
                 column_config={"Fecha": st.column_config.DatetimeColumn(format="DD/MM/YY HH:mm")})


def _knowledge() -> None:
    st.markdown("El asistente solo responde preguntas de producto con esta información. Registra datos tomados de "
                "**condiciones generales, folletos oficiales o comunicados de la aseguradora**, con su fuente. "
                "Las preguntas sin respuesta validada se transfieren al agente.")
    with st.form("kb_new", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        product = c1.selectbox("Producto", ["General"] + PRODUCTS)
        insurer = c2.text_input("Aseguradora (opcional)")
        topic = c3.text_input("Tema *", placeholder="Ej. Maternidad")
        question = st.text_input("Pregunta del prospecto *", placeholder="¿El plan cubre maternidad?")
        answer = st.text_area("Respuesta validada *", height=90)
        c4, c5 = st.columns(2)
        keywords = c4.text_input("Palabras clave", placeholder="maternidad, parto, embarazo")
        source = c5.text_input("Fuente *", placeholder="Condiciones generales Plan X, versión 2026, cláusula 5")
        if st.form_submit_button("Guardar en base validada"):
            try:
                with session_scope() as s:
                    srepo.add_knowledge(s, {"product": product, "insurer": insurer, "topic": topic, "question": question,
                                            "answer": answer, "keywords": keywords, "source": source},
                                        author=data.current_user())
                st.success("Información validada guardada.")
            except ValueError as e:
                st.error(str(e))
    with session_scope() as s:
        items = srepo.knowledge_items(s, only_active=False)
    st.markdown(f"**{sum(1 for i in items if i['active'])}** elementos activos · "
                f"{len(agent.GLOSSARY)} conceptos del glosario general")
    if items:
        df = pd.DataFrame(items)
        st.dataframe(df[["id", "product", "insurer", "topic", "question", "source", "validated_by", "validated_at",
                         "active"]], hide_index=True, use_container_width=True)
        c1, c2 = st.columns([2, 1])
        iid = c1.selectbox("Elemento", df["id"].tolist(), format_func=lambda i: f"#{i} · {df.set_index('id').loc[i, 'topic']}")
        active = bool(df.set_index("id").loc[iid, "active"])
        if c2.button("Desactivar" if active else "Activar"):
            with session_scope() as s:
                srepo.set_knowledge_active(s, int(iid), not active)
            st.rerun()
    with st.expander("Glosario general incluido"):
        for g in agent.GLOSSARY:
            st.markdown(f"**{g['topic']}** — {g['answer']}")
