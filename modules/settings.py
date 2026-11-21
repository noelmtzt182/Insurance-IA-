"""Configuración: datos demo, negocio, aviso de privacidad, usuarios, integraciones y sistema."""
from __future__ import annotations

import streamlit as st

from database import repository as repo
from database.session import is_sqlite, masked_url, session_scope
from integrations import google_ads, google_trends, llm, meta_ads, whatsapp_cloud
from services import auth
from services.demo import generate_demo
from utils import data
from utils.components import flash, page_header
from utils.config import DATA_MODES


def render() -> None:
    page_header("Configuración", "Datos, negocio, privacidad y seguridad")
    flash()
    admin = data.is_admin()
    if is_sqlite():
        st.warning("**Base de datos SQLite local.** Úsala solo para desarrollo o demostración. En Streamlit Community "
                   "Cloud el almacenamiento es efímero: los datos se pierden al reiniciar o redesplegar. Para datos "
                   "reales configura PostgreSQL administrado en `st.secrets[database][url]`.")
    t1, t2, t3, t4, t5, t6 = st.tabs(["Datos demo", "Negocio", "Aviso de privacidad", "Usuarios", "Integraciones",
                                      "Sistema y bitácora"])
    with t1:
        _demo(admin)
    with t2:
        _business(admin)
    with t3:
        _privacy(admin)
    with t4:
        _users(admin)
    with t5:
        _integrations()
    with t6:
        _system(admin)


def _demo(admin: bool) -> None:
    with session_scope() as s:
        counts = repo.count_records(s)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leads reales", f"{counts['leads_reales']:,}")
    c2.metric("Campañas reales", f"{counts['campanas_reales']:,}")
    c3.metric("Leads demo", f"{counts['leads_demo']:,}")
    c4.metric("Campañas demo", f"{counts['campanas_demo']:,}")
    st.markdown("Los datos demo son **sintéticos** (nombres ficticios, teléfonos con prefijo 00, correos "
                "@example.com) y se guardan separados con una marca `is_demo`. Nunca se mezclan con los reales salvo "
                "que elijas la vista combinada.")
    modes = list(DATA_MODES)
    cur = data.data_mode()
    sel = st.radio("Conjunto de datos visible en el panel", modes, index=modes.index(cur),
                   format_func=lambda k: DATA_MODES[k], horizontal=True)
    if sel != cur:
        st.session_state["data_mode"] = sel
        st.rerun()
    if not admin:
        st.caption("Solo un administrador puede cargar o eliminar datos demo.")
        return
    n = st.number_input("Número de prospectos demo", min_value=100, max_value=5000, value=1000, step=100)
    b1, b2 = st.columns(2)
    if b1.button("Cargar / reiniciar datos demo", type="primary"):
        with st.spinner("Generando datos sintéticos…"):
            with session_scope() as s:
                res = generate_demo(s, n=int(n))
                repo.audit(s, data.current_user(), "Cargar datos demo", str(res))
        st.session_state["data_mode"] = "demo"
        data.bump()
        flash(f"Se generaron {res['leads']:,} leads y {res['campaigns']} campañas demo. Vista cambiada a «Datos demo».")
        st.rerun()
    if b2.button("Eliminar datos demo"):
        with session_scope() as s:
            k = repo.delete_demo_data(s)
            repo.audit(s, data.current_user(), "Eliminar datos demo", f"{k} leads")
        st.session_state["data_mode"] = "reales"
        data.bump()
        flash(f"Se eliminaron {k:,} leads demo y sus campañas. Los datos reales no se modificaron.")
        st.rerun()


def _business(admin: bool) -> None:
    sets = data.settings()
    with st.form("business"):
        c1, c2 = st.columns(2)
        company = c1.text_input("Nombre comercial", value=sets["company_name"])
        advisor = c2.text_input("Nombre del asesor (para mensajes)", value=sets["advisor_name"])
        c3, c4 = st.columns(2)
        phone = c3.text_input("WhatsApp del asesor (10 dígitos, botón de la landing)", value=sets["advisor_phone"])
        url = c4.text_input("URL pública de la app", value=sets["public_url"], placeholder="https://tu-app.streamlit.app")
        c5, c6 = st.columns(2)
        inactive = c5.number_input("Días para considerar un lead inactivo", min_value=3, max_value=120,
                                   value=int(sets["inactive_days"]))
        qdays = c6.number_input("Días para seguimiento de cotización", min_value=1, max_value=30,
                                value=int(sets["quote_followup_days"]))
        ok = st.form_submit_button("Guardar", disabled=not admin)
    if ok:
        from utils.validation import normalize_phone
        if phone and not normalize_phone(phone):
            st.error("El teléfono debe tener 10 dígitos.")
            return
        if url and not url.startswith(("https://", "http://localhost")):
            st.error("La URL pública debe iniciar con https://")
            return
        with session_scope() as s:
            for k, v in {"company_name": company, "advisor_name": advisor, "advisor_phone": normalize_phone(phone) or "",
                         "public_url": url.rstrip("/"), "inactive_days": inactive, "quote_followup_days": qdays}.items():
                repo.set_setting(s, k, str(v))
            repo.audit(s, data.current_user(), "Actualizar datos del negocio")
        st.success("Configuración guardada.")


def _privacy(admin: bool) -> None:
    sets = data.settings()
    st.markdown("El texto vigente se guarda con su **versión** y **huella SHA-256** en cada consentimiento, para "
                "poder demostrar qué aceptó cada prospecto y cuándo.")
    with st.form("privacy"):
        notice = st.text_area("Aviso de privacidad (Markdown)", value=sets["privacy_notice"], height=320)
        consent = st.text_area("Texto de consentimiento de contacto", value=sets["contact_consent_text"], height=90)
        version = st.text_input("Versión", value=sets["privacy_version"],
                                help="Cambia la versión cada vez que modifiques el texto (ej. v2-2026-11).")
        ok = st.form_submit_button("Guardar aviso", disabled=not admin)
    if ok:
        if (notice != sets["privacy_notice"] or consent != sets["contact_consent_text"]) and version == sets["privacy_version"]:
            st.error("Modificaste el texto: actualiza también la versión.")
            return
        with session_scope() as s:
            repo.set_setting(s, "privacy_notice", notice)
            repo.set_setting(s, "contact_consent_text", consent)
            repo.set_setting(s, "privacy_version", version.strip())
            repo.audit(s, data.current_user(), "Actualizar aviso de privacidad", f"versión {version}")
        st.success("Aviso actualizado. Los nuevos consentimientos usarán esta versión.")
    with st.expander("Vista previa"):
        st.markdown(sets["privacy_notice"])


def _users(admin: bool) -> None:
    st.markdown("##### Cambiar mi contraseña")
    with st.form("chpw", clear_on_submit=True):
        cur = st.text_input("Contraseña actual", type="password")
        new = st.text_input("Nueva contraseña", type="password")
        new2 = st.text_input("Confirmar", type="password")
        ok = st.form_submit_button("Actualizar")
    if ok:
        if new != new2:
            st.error("Las contraseñas no coinciden.")
        else:
            try:
                with session_scope() as s:
                    auth.change_password(s, data.current_user(), cur, new)
                st.success("Contraseña actualizada.")
            except ValueError as e:
                st.error(str(e))
    if not admin:
        return
    st.markdown("##### Crear usuario")
    with st.form("newuser", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        u = c1.text_input("Usuario")
        p = c2.text_input("Contraseña temporal", type="password")
        role = c3.selectbox("Rol", ["asesor", "admin"])
        ok = st.form_submit_button("Crear")
    if ok:
        try:
            with session_scope() as s:
                auth.create_user(s, u, p, role)
                repo.audit(s, data.current_user(), "Crear usuario", f"{u} ({role})")
            st.success(f"Usuario {u} creado.")
        except ValueError as e:
            st.error(str(e))
    with session_scope() as s:
        st.dataframe(auth.users_df(s), hide_index=True, use_container_width=True)


def _integrations() -> None:
    rows = [
        ("IA (Anthropic Claude)", "Configurado" if llm.is_configured() else "No configurado", "ANTHROPIC_API_KEY"),
        ("Google Ads API (Keyword Planner / Lead Forms)", google_ads.status(), "[google_ads]"),
        ("Meta Lead Ads", meta_ads.status(), "[meta]"),
        ("Google Trends (fuente autorizada)", google_trends.status(), "[google_trends]"),
        ("WhatsApp Business Platform", whatsapp_cloud.status(), "[whatsapp]"),
    ]
    st.dataframe([{"Integración": a, "Estado": b, "Secreto": c} for a, b, c in rows], hide_index=True,
                 use_container_width=True)
    st.caption("Las credenciales se leen exclusivamente de st.secrets / variables de entorno; nunca se guardan en la "
               "base de datos ni se muestran en pantalla. Respeta los términos de uso de cada plataforma.")


def _system(admin: bool) -> None:
    st.markdown(f"**Base de datos:** `{masked_url()}`")
    if st.button("Recalcular todos los Lead Scores"):
        with session_scope() as s:
            n = repo.recalc_all_scores(s, "todos")
        data.bump()
        st.success(f"{n:,} leads recalculados.")
    if admin:
        st.markdown("##### Bitácora de auditoría")
        with session_scope() as s:
            st.dataframe(repo.audit_df(s), hide_index=True, use_container_width=True)
