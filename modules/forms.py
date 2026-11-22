"""Formularios compartidos: captura de lead y cuestionario de diagnóstico."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import streamlit as st

from services import diagnosis as dx
from utils.config import (APPOINTMENT_SLOTS, BUDGET_RANGES, PRODUCT_GMM, PRODUCT_VIDA, PRODUCTS, SEGMENT_OTHER,
                          SEGMENTS, SOURCES, today_mx)


def next_business_day(days: int = 1):
    d = today_mx() + timedelta(days=days)
    while d.weekday() >= 5:  # sábado o domingo
        d += timedelta(days=1)
    return d


def lead_form(key: str, *, public: bool, settings: dict, default_source: Optional[str] = None,
              campaigns: Optional[dict] = None, default_product: Optional[str] = None) -> Optional[dict]:
    """Dibuja el formulario y devuelve los datos crudos al enviarse (o None)."""
    with st.form(key, clear_on_submit=False, border=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Nombre completo *", max_chars=120)
        phone = c2.text_input("Teléfono celular (10 dígitos) *", max_chars=20, placeholder="55 1234 5678")
        c3, c4 = st.columns(2)
        email = c3.text_input("Correo electrónico *", max_chars=200)
        city = c4.text_input("Ciudad *", max_chars=100)
        c5, c6 = st.columns(2)
        product = c5.radio("Producto de interés *", PRODUCTS, horizontal=True,
                           index=PRODUCTS.index(default_product) if default_product in PRODUCTS else 0)
        budget = c6.selectbox("Presupuesto mensual aproximado (MXN)", BUDGET_RANGES, index=0)
        c7, c8 = st.columns(2)
        est = c7.date_input("¿Cuándo te gustaría contratar? (fecha estimada)", value=today_mx() + timedelta(days=30),
                            min_value=today_mx(), max_value=today_mx() + timedelta(days=3 * 365), format="DD/MM/YYYY")
        segment = c8.selectbox("¿Qué te describe mejor?", [SEGMENT_OTHER] + SEGMENTS)
        if public:
            src_idx = SOURCES.index(default_source) if default_source in SOURCES else SOURCES.index("Sitio web")
            source = st.selectbox("¿Cómo te enteraste de nosotros?", SOURCES, index=src_idx)
            campaign_id = None
        else:
            c9, c10 = st.columns(2)
            source = c9.selectbox("Fuente de adquisición", SOURCES,
                                  index=SOURCES.index(default_source) if default_source in SOURCES else 0)
            opts = {None: "Sin campaña"} | (campaigns or {})
            campaign_id = c10.selectbox("Campaña", list(opts), format_func=lambda k: opts[k])

        appt_date = appt_slot = None
        if public:
            st.markdown("**📅 Agenda tu asesoría gratuita (20 minutos, por llamada o videollamada)**")
            a1, a2 = st.columns(2)
            appt_date = a1.date_input("Día que prefieres", value=next_business_day(), min_value=today_mx(),
                                      max_value=today_mx() + timedelta(days=30), format="DD/MM/YYYY")
            appt_slot = a2.selectbox("Horario", APPOINTMENT_SLOTS)
            quote = st.checkbox("También quiero recibir una cotización", value=True)
            contact = True
        else:
            q1, q2 = st.columns(2)
            quote = q1.checkbox("Quiero recibir una cotización", value=True)
            contact = q2.checkbox("Quiero que un asesor me contacte", value=True)

        if public:
            with st.expander("Leer aviso de privacidad"):
                st.markdown(settings["privacy_notice"])
                st.caption(f"Versión {settings['privacy_version']}")
            consent_contact = st.checkbox(settings["contact_consent_text"])
            consent_privacy = st.checkbox("He leído y acepto el aviso de privacidad.")
        else:
            st.caption("Captura interna: confirma que el prospecto otorgó su consentimiento y conoce el aviso de privacidad.")
            consent_contact = st.checkbox("El prospecto autorizó ser contactado (consentimiento verbal o escrito documentado)")
            consent_privacy = st.checkbox(f"Se informó al prospecto el aviso de privacidad vigente ({settings['privacy_version']})")
        submitted = st.form_submit_button("Agendar mi asesoría gratuita" if public else "Guardar lead", type="primary",
                                          use_container_width=public)
    if not submitted:
        return None
    return {
        "name": name, "phone": phone, "email": email, "city": city, "product": product,
        "budget_range": budget, "est_purchase_date": est, "source": source, "campaign_id": campaign_id,
        "segment": segment if segment in SEGMENTS else None, "quote_requested": quote, "contact_requested": contact,
        "consent_contact": consent_contact, "consent_privacy": consent_privacy,
        "appt_date": appt_date, "appt_slot": appt_slot,
    }


def diagnostic_form(key: str, product: str, default_city: str = "") -> Optional[tuple[dict, dict]]:
    """Cuestionario dinámico. No solicita información médica. Devuelve (respuestas, resultado)."""
    st.caption("Sin preguntas médicas. El resultado es orientativo: no es una cotización ni garantiza cobertura.")
    with st.form(key, border=True):
        if product == PRODUCT_VIDA:
            c1, c2 = st.columns(2)
            answers = {
                "edad": c1.selectbox("Rango de edad", dx.AGE_RANGES, index=1),
                "dependientes": c2.selectbox("Dependientes económicos", dx.DEPENDENTS),
            }
            c3, c4 = st.columns(2)
            answers["ingresos"] = c3.selectbox("Rango de ingresos mensuales", dx.INCOME_RANGES, index=1)
            answers["cobertura_actual"] = c4.selectbox("Cobertura actual de vida", dx.LIFE_COVERAGE)
            answers["obligaciones"] = st.multiselect("Obligaciones financieras", dx.OBLIGATIONS)
        else:
            c1, c2 = st.columns(2)
            answers = {
                "edad": c1.selectbox("Rango de edad del titular", dx.AGE_RANGES, index=1),
                "tipo": c2.radio("Cobertura", dx.GMM_TYPE, horizontal=True),
            }
            c3, c4 = st.columns(2)
            answers["asegurados"] = int(c3.number_input("Número de asegurados", min_value=1, max_value=12, value=1))
            answers["ciudad"] = c4.text_input("Ciudad", value=default_city, max_chars=100)
            answers["cobertura_actual"] = st.selectbox("Cobertura médica actual", dx.GMM_COVERAGE)
        c5, c6 = st.columns(2)
        answers["presupuesto"] = c5.selectbox("Presupuesto mensual", BUDGET_RANGES)
        answers["intencion"] = c6.selectbox("Horizonte de contratación", dx.INTENT_OPTIONS, index=1)
        ok = st.form_submit_button("Ver mi diagnóstico", type="primary")
    if not ok:
        return None
    if product == PRODUCT_GMM and answers.get("tipo") == "Individual":
        answers["asegurados"] = 1
    return answers, dx.diagnose(product, answers)


def show_diagnosis(result: dict) -> None:
    c1, c2 = st.columns(2)
    c1.metric("Nivel de necesidad de protección", result["need_level"])
    c2.metric("Intención de contratación", result["intent"])
    st.markdown("**Lo que identificamos**")
    for f in result["findings"]:
        st.markdown(f"- {f}")
    st.markdown("**Aspectos a considerar**")
    for c in result["considerations"]:
        st.markdown(f"- {c}")
    st.markdown("**Siguientes pasos sugeridos**")
    for n in result["next_steps"]:
        st.markdown(f"- {n}")
    st.caption(result["disclaimer"])
