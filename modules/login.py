"""Acceso al panel privado: inicio de sesión y configuración inicial."""
from __future__ import annotations

import hmac
import time

import streamlit as st

from database.session import session_scope
from services import auth
from utils.config import APP_NAME, get_secret

MAX_ATTEMPTS = 5
LOCK_SECONDS = 60


def render() -> None:
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown('<div class="ila-brand"><div class="ila-brand-mark">IL</div><div>'
                    f'<div class="ila-brand-name">{APP_NAME}</div>'
                    '<div class="ila-brand-tag">Panel privado</div></div></div>', unsafe_allow_html=True)
        with session_scope() as s:
            auth.bootstrap_admin_from_secrets(s)
            n_users = auth.user_count(s)
        if n_users == 0:
            _setup()
        else:
            _login()
        st.caption("¿Buscas el formulario para prospectos? Está en la ruta pública **/registro**.")


def _setup() -> None:
    st.markdown("### Configuración inicial")
    token_required = get_secret("SETUP_TOKEN")
    st.write("No hay usuarios. Crea la cuenta de administrador.")
    if not token_required:
        st.warning("Define `SETUP_TOKEN` en `st.secrets` antes de publicar la app: sin él, cualquiera que abra la "
                   "app por primera vez podría crear el administrador.")
    with st.form("setup"):
        token = st.text_input("Token de configuración (SETUP_TOKEN)", type="password") if token_required else ""
        username = st.text_input("Usuario administrador")
        pw = st.text_input("Contraseña", type="password", help="Mínimo 10 caracteres, mayúsculas, minúsculas y números.")
        pw2 = st.text_input("Confirmar contraseña", type="password")
        ok = st.form_submit_button("Crear administrador", type="primary")
    if ok:
        if token_required and not hmac.compare_digest(str(token), str(token_required)):
            st.error("Token de configuración incorrecto.")
            return
        if pw != pw2:
            st.error("Las contraseñas no coinciden.")
            return
        try:
            with session_scope() as s:
                user = auth.create_user(s, username, pw, role="admin")
                st.session_state["user"] = {"username": user.username, "role": user.role}
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _login() -> None:
    st.markdown("### Iniciar sesión")
    locked_until = st.session_state.get("locked_until", 0)
    if time.time() < locked_until:
        st.error(f"Demasiados intentos. Espera {int(locked_until - time.time())} segundos.")
        return
    with st.form("login"):
        username = st.text_input("Usuario")
        pw = st.text_input("Contraseña", type="password")
        ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if ok:
        with session_scope() as s:
            user = auth.authenticate(s, username, pw)
            info = {"username": user.username, "role": user.role} if user else None
        if info:
            st.session_state["user"] = info
            st.session_state["login_attempts"] = 0
            st.rerun()
        attempts = st.session_state.get("login_attempts", 0) + 1
        st.session_state["login_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            st.session_state["locked_until"] = time.time() + LOCK_SECONDS
            st.session_state["login_attempts"] = 0
        st.error("Usuario o contraseña incorrectos.")
