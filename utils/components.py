"""Componentes de interfaz reutilizables."""
from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import streamlit as st

from utils.config import DATA_MODES


def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="ila-eyebrow">{html.escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.markdown(f"# {title}")
    if subtitle:
        st.markdown(f'<div class="ila-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, help_text: Optional[str] = None) -> None:
    help_html = (f'<div class="ila-kpi-help" title="{html.escape(help_text)}">{html.escape(help_text)}</div>'
                 if help_text else "")
    st.markdown(
        f'<div class="ila-kpi" title="{html.escape(label)}: {html.escape(value)}">'
        f'<div class="ila-kpi-label">{html.escape(label)}</div>'
        f'<div class="ila-kpi-value">{html.escape(value)}</div>{help_html}</div>',
        unsafe_allow_html=True,
    )


def stage_strip(counts: dict) -> None:
    items = "".join(f'<span class="ila-stage">{html.escape(k)}<b>{v:,}</b></span>' for k, v in counts.items())
    st.markdown(f'<div class="ila-stages">{items}</div>', unsafe_allow_html=True)


def flash(message: Optional[str] = None, kind: str = "success") -> None:
    """Guarda un mensaje para mostrarlo tras st.rerun(), o lo muestra si ya existe."""
    if message is not None:
        st.session_state["_flash"] = (kind, message)
        return
    pending = st.session_state.pop("_flash", None)
    if pending:
        getattr(st, pending[0])(pending[1])


def kpi_row(items: list[tuple], per_row: int = 4) -> None:
    """Tarjetas KPI en filas de hasta `per_row` columnas (legibles en pantallas medianas)."""
    for start in range(0, len(items), per_row):
        chunk = items[start:start + per_row]
        cols = st.columns(per_row)
        for col, item in zip(cols, chunk):
            with col:
                kpi(*item)


def data_mode() -> str:
    return st.session_state.get("data_mode", "reales")


def demo_banner() -> None:
    mode = data_mode()
    if mode == "demo":
        st.markdown('<div class="ila-banner"><b>Datos demo.</b> Estás viendo registros sintéticos generados '
                    'para demostración; no representan resultados comerciales reales.</div>', unsafe_allow_html=True)
    elif mode == "todos":
        st.markdown('<div class="ila-banner"><b>Vista combinada.</b> Se muestran datos reales <i>y</i> sintéticos '
                    'de demostración. No uses esta vista para reportar resultados.</div>', unsafe_allow_html=True)


def mode_label() -> str:
    return DATA_MODES[data_mode()]


def current_user() -> str:
    return st.session_state.get("user", {}).get("username", "")


def csv_bytes(df: pd.DataFrame) -> bytes:
    # utf-8-sig para que Excel en español abra acentos correctamente
    return df.to_csv(index=False).encode("utf-8-sig")


def empty_state(message: str) -> None:
    st.info(message, icon="ℹ️")
