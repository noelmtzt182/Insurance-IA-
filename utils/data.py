"""Carga de datos con caché invalidada por huella de la base de datos.

La huella (conteo + última actualización) se consulta en cada render, de modo
que cualquier cambio —incluidos leads capturados en la landing pública por otra
sesión— se refleja de inmediato en todos los módulos.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from database import repository as repo
from database.models import Campaign, Lead, Objection, Quotation, Reminder
from database import sales_repository as srepo
from database.session import session_scope


def data_mode() -> str:
    return st.session_state.get("data_mode", "reales")


def _fingerprint() -> tuple:
    with session_scope() as s:
        lc, lu = s.execute(select(func.count(Lead.id), func.max(Lead.updated_at))).one()
        cc, cu = s.execute(select(func.count(Campaign.id), func.max(Campaign.updated_at))).one()
        rc = s.scalar(select(func.count(Reminder.id)))
        qc, qm = s.execute(select(func.count(Quotation.id), func.max(Quotation.id))).one()
        oc = s.scalar(select(func.count(Objection.id)))
    return (lc, str(lu), cc, str(cu), rc, qc, qm, oc, st.session_state.get("data_version", 0))


@st.cache_data(show_spinner=False, max_entries=16)
def _leads(mode: str, fp: tuple) -> pd.DataFrame:
    with session_scope() as s:
        return repo.leads_df(s, mode)


@st.cache_data(show_spinner=False, max_entries=16)
def _campaigns(mode: str, fp: tuple) -> pd.DataFrame:
    with session_scope() as s:
        return repo.campaigns_df(s, mode)


def leads(mode: str | None = None) -> pd.DataFrame:
    return _leads(mode or data_mode(), _fingerprint()).copy()


def campaigns(mode: str | None = None) -> pd.DataFrame:
    return _campaigns(mode or data_mode(), _fingerprint()).copy()


def bump() -> None:
    """Invalida la caché tras una escritura de esta sesión."""
    st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1


def settings() -> dict:
    with session_scope() as s:
        return repo.get_settings(s)


def current_user() -> str:
    return (st.session_state.get("user") or {}).get("username", "")


def is_admin() -> bool:
    return (st.session_state.get("user") or {}).get("role") == "admin"


def write_mode_is_demo() -> bool:
    """Los registros creados desde el panel son demo solo si se está viendo exclusivamente demo."""
    return data_mode() == "demo"


@st.cache_data(show_spinner=False, max_entries=16)
def _quotations(mode: str, fp: tuple) -> pd.DataFrame:
    with session_scope() as s:
        return srepo.quotations_df(s, mode)


@st.cache_data(show_spinner=False, max_entries=16)
def _objections(mode: str, fp: tuple) -> pd.DataFrame:
    with session_scope() as s:
        return srepo.objections_df(s, mode)


@st.cache_data(show_spinner=False, max_entries=16)
def _activity(mode: str, fp: tuple) -> pd.DataFrame:
    with session_scope() as s:
        return srepo.activity_df(s, mode)


def quotations(mode: str | None = None) -> pd.DataFrame:
    return _quotations(mode or data_mode(), _fingerprint()).copy()


def objections(mode: str | None = None) -> pd.DataFrame:
    return _objections(mode or data_mode(), _fingerprint()).copy()


def activity(mode: str | None = None) -> pd.DataFrame:
    return _activity(mode or data_mode(), _fingerprint()).copy()


def lead_options(leads: pd.DataFrame, active_only: bool = False, limit: int = 1500) -> dict:
    """Opciones para selectbox de prospectos: {id: etiqueta}."""
    df = leads
    if active_only:
        df = df[~df["stage"].isin(["Póliza emitida", "Perdido"])]
    df = df.sort_values("score", ascending=False).head(limit)
    return {int(r.id): f"#{r.id} · {r.name} · {r.product} · {r.stage} · score {r.score}" for r in df.itertuples()}
