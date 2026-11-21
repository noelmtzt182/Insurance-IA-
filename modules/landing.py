"""Landing pública de captación (/registro).

Separada del CRM: no lee ni muestra registros comerciales; solo crea leads
autorizados y, opcionalmente, guarda el diagnóstico del propio prospecto.
"""
from __future__ import annotations

import html

import streamlit as st

from database import repository as repo
from database.session import session_scope
from modules.forms import diagnostic_form, lead_form, show_diagnosis
from services.capture import attribution_from_params, ingest
from services.whatsapp import wa_link
from utils.config import PRODUCT_GMM, PRODUCT_VIDA, PRODUCTS, UTM_SOURCE_MAP
from utils.data import bump

MAX_SUBMISSIONS_PER_SESSION = 3

FAQ = [
    ("¿El diagnóstico tiene costo?", "No. Es gratuito, orientativo y sin compromiso de contratación."),
    ("¿Me van a pedir información médica?", "No. En este sitio no solicitamos datos de salud. Si decides contratar, "
     "la aseguradora te pedirá la información necesaria directamente en su solicitud."),
    ("¿Cuánto cuesta un seguro?", "Depende de la aseguradora, la cobertura y tu perfil. Por eso no publicamos precios: "
     "un asesor te presentará una cotización formal."),
    ("¿Qué pasa con mis datos?", "Se usan solo para las finalidades del aviso de privacidad. Puedes ejercer tus "
     "derechos ARCO o revocar tu consentimiento en cualquier momento."),
    ("¿Puedo dejar de recibir mensajes?", "Sí. Basta con responder «BAJA» o solicitarlo al asesor."),
]


def render() -> None:
    with session_scope() as s:
        settings = repo.get_settings(s)
    params = {k: v for k, v in st.query_params.items()}
    attribution = attribution_from_params(params)
    default_source = UTM_SOURCE_MAP.get(str(params.get("utm_source", "")).lower())
    default_product = PRODUCT_GMM if "gmm" in str(params.get("utm_campaign", "")).lower() else None

    st.markdown(f'<div class="ila-eyebrow">{html.escape(settings["company_name"])}</div>', unsafe_allow_html=True)
    st.markdown("# Protege lo que más importa.")
    st.markdown("### Descubre qué seguro se adapta a tus necesidades.")
    st.markdown('<div class="ila-sub">Asesoría profesional en seguro de vida y gastos médicos mayores. '
                'Diagnóstico gratuito y sin compromiso.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="ila-card"><b>Seguro de vida</b><br><span style="color:#4A5260;font-size:.9rem">'
                    'Respaldo económico para quienes dependen de ti: educación, deudas y estabilidad familiar.'
                    '</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="ila-card"><b>Gastos médicos mayores</b><br><span style="color:#4A5260;font-size:.9rem">'
                    'Atención en hospitales privados ante accidentes o enfermedades, protegiendo tu patrimonio.'
                    '</span></div>', unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    b1.markdown("**✓ Diagnóstico gratuito**  \nTe orientamos en minutos.")
    b2.markdown("**✓ Comparación clara**  \nTe explicamos coberturas y condiciones.")
    b3.markdown("**✓ Acompañamiento**  \nDesde la cotización hasta un reclamo.")

    if settings.get("advisor_phone"):
        link = wa_link(settings["advisor_phone"], "Hola, me interesa recibir asesoría sobre seguros.")
        if link:
            st.link_button("💬 Escríbenos por WhatsApp", link)

    tab_form, tab_dx, tab_chat, tab_faq = st.tabs(["Solicitar asesoría / cotización", "Diagnóstico gratuito",
                                                   "Pregunta a nuestro asistente", "Preguntas frecuentes"])

    with tab_form:
        submitted_n = st.session_state.get("public_submissions", 0)
        if st.session_state.get("public_lead_id"):
            st.success("¡Gracias! Recibimos tu solicitud. Un asesor se pondrá en contacto contigo por el medio que "
                       "autorizaste. Mientras tanto, puedes completar tu diagnóstico gratuito en la pestaña de al lado.")
            if submitted_n < MAX_SUBMISSIONS_PER_SESSION and st.button("Enviar otra solicitud"):
                st.session_state.pop("public_lead_id", None)
                st.rerun()
        elif submitted_n >= MAX_SUBMISSIONS_PER_SESSION:
            st.info("Ya recibimos tus solicitudes. Si necesitas algo más, contáctanos por WhatsApp.")
        else:
            raw = lead_form("public_lead_form", public=True, settings=settings, default_source=default_source,
                            default_product=default_product)
            if raw is not None:
                raw.update(attribution)
                with session_scope() as s:
                    lead_id, errors, _dup = ingest(s, raw, channel="landing_publica", require_consent=True)
                    pending = st.session_state.pop("pending_diagnostic", None)
                    if lead_id and pending:
                        repo.save_diagnostic(s, pending["product"], pending["answers"], pending["result"],
                                             lead_id=lead_id)
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    st.session_state["public_lead_id"] = lead_id
                    st.session_state["public_product"] = raw["product"]
                    st.session_state["public_submissions"] = submitted_n + 1
                    bump()
                    st.rerun()

    with tab_dx:
        product = st.radio("¿Sobre qué seguro quieres tu diagnóstico?", PRODUCTS, horizontal=True,
                           index=PRODUCTS.index(st.session_state.get("public_product", PRODUCT_VIDA)), key="dx_product")
        out = diagnostic_form("public_dx", product)
        if out:
            answers, result = out
            lead_id = st.session_state.get("public_lead_id")
            if lead_id:
                with session_scope() as s:
                    repo.save_diagnostic(s, product, answers, result, lead_id=lead_id)
                bump()
            else:
                st.session_state["pending_diagnostic"] = {"product": product, "answers": answers, "result": result}
            st.session_state["public_dx_result"] = result
        if st.session_state.get("public_dx_result"):
            show_diagnosis(st.session_state["public_dx_result"])
            if not st.session_state.get("public_lead_id"):
                st.info("¿Quieres que un asesor revise este diagnóstico contigo? Completa el formulario en la "
                        "pestaña «Solicitar asesoría / cotización». Tu diagnóstico solo se guardará si envías tus datos.")

    with tab_chat:
        _assistant()

    with tab_faq:
        for q, a in FAQ:
            with st.expander(q):
                st.write(a)

    st.divider()
    with st.expander("Aviso de privacidad"):
        st.markdown(settings["privacy_notice"])
        st.caption(f"Versión {settings['privacy_version']}")
    st.caption("La contratación de cualquier seguro está sujeta a las condiciones y políticas de suscripción de "
               "cada aseguradora. Este sitio no publica precios ni garantiza coberturas.")


def _assistant() -> None:
    """Asistente público: responde solo con información validada; transfiere al asesor si no sabe."""
    from datetime import timedelta

    from database import sales_repository as srepo
    from services import sales_agent as agent
    from utils.config import today_mx

    st.caption("Resuelvo dudas generales sobre seguros. No doy precios ni confirmo coberturas: eso lo hace tu asesor "
               "con una cotización oficial. No compartas información médica por este medio.")
    chat = st.session_state.setdefault("public_chat", [])
    for m in chat:
        with st.chat_message(m["role"], avatar="🙂" if m["role"] == "user" else "🤖"):
            st.markdown(m["text"])
    lead_id = st.session_state.get("public_lead_id")
    if len(chat) >= 40:
        st.info("Has alcanzado el límite de mensajes de esta sesión. Tu asesor puede continuar contigo.")
        return
    with st.form("public_chat_form", clear_on_submit=True):
        text = st.text_input("Escribe tu pregunta", max_chars=500)
        ok = st.form_submit_button("Enviar")
    if ok and text.strip():
        product = st.session_state.get("public_product")
        with session_scope() as s:
            kb = srepo.knowledge_items(s, product)
            r = agent.respond(text, product, kb)
            if lead_id:
                srepo.add_agent_message(s, lead_id, "prospecto", text.strip(), intent=r.intent, channel="landing")
                srepo.add_agent_message(s, lead_id, "asistente", r.reply, intent=r.intent, sources=r.sources,
                                        channel="landing")
                if r.objection:
                    srepo.add_objection(s, lead_id, r.objection, text=text.strip(), response=r.reply,
                                        source="asistente", author="asistente")
                if r.handoff_suggested and r.intent == "transferencia":
                    srepo.request_handoff(s, lead_id, f"Solicitado desde la landing: «{text.strip()[:200]}»",
                                          author="asistente", channel="landing")
                if r.opt_out:
                    repo.add_note(s, lead_id, "El prospecto pidió no ser contactado (BAJA) desde el asistente. "
                                              "Revisa y revoca el consentimiento.", kind="Sistema", author="asistente")
        reply = r.reply
        if (r.handoff_suggested or r.appointment_suggested) and not lead_id:
            reply += "\n\nPara que tu asesor te contacte, completa la pestaña «Solicitar asesoría / cotización»."
        chat += [{"role": "user", "text": text.strip()}, {"role": "assistant", "text": reply}]
        st.session_state["public_chat_last"] = {"handoff": r.handoff_suggested, "appt": r.appointment_suggested}
        bump()
        st.rerun()

    last = st.session_state.get("public_chat_last") or {}
    if lead_id and (last.get("appt") or last.get("handoff")):
        with st.form("public_appt"):
            st.markdown("**¿Quieres agendar una llamada con tu asesor?**")
            c1, c2 = st.columns(2)
            d = c1.date_input("Día preferido", value=today_mx() + timedelta(days=1), min_value=today_mx(),
                              max_value=today_mx() + timedelta(days=60), format="DD/MM/YYYY")
            slot = c2.selectbox("Horario", ["Mañana (9–12 h)", "Mediodía (12–15 h)", "Tarde (15–19 h)"])
            c3, c4 = st.columns(2)
            ask_appt = c3.form_submit_button("Solicitar cita")
            ask_human = c4.form_submit_button("Prefiero que me contacte una persona")
        if ask_appt or ask_human:
            with session_scope() as s:
                if ask_appt:
                    srepo.request_appointment(s, lead_id, d, slot, author="prospecto", channel="landing", confirm=False)
                else:
                    srepo.request_handoff(s, lead_id, "El prospecto pidió atención personal desde la landing.",
                                          author="asistente", channel="landing")
            st.session_state["public_chat_last"] = {}
            st.session_state["public_chat"].append({"role": "assistant", "text":
                "¡Listo! Tu asesor recibió tu solicitud y te contactará para confirmar." if ask_appt else
                "¡Listo! Tu asesor te contactará personalmente por el medio que autorizaste."})
            bump()
            st.rerun()
