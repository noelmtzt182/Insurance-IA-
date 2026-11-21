"""Diagnóstico Inteligente (uso interno del asesor)."""
from __future__ import annotations

import streamlit as st

from database import repository as repo
from database.session import session_scope
from modules.forms import diagnostic_form, show_diagnosis
from utils import data
from utils.components import demo_banner, page_header
from utils.config import PRODUCTS


def render() -> None:
    page_header("Diagnóstico Inteligente", "Cuestionario orientativo",
                "Sin datos médicos sensibles. No genera cotizaciones, primas ni condiciones de aseguramiento.")
    demo_banner()
    leads = data.leads()
    c1, c2 = st.columns([2, 1])
    options = {None: "Sin vincular a un lead"}
    if not leads.empty:
        active = leads[~leads["stage"].isin(["Póliza emitida", "Perdido"])].head(500)
        options |= {int(r.id): f"#{r.id} · {r.name} · {r.product}" for r in active.itertuples()}
    lead_id = c1.selectbox("Vincular a lead (actualiza su intención, presupuesto y score)", list(options),
                           format_func=lambda k: options[k])
    default_product = PRODUCTS[0]
    city = ""
    if lead_id:
        row = leads.set_index("id").loc[lead_id]
        default_product, city = row["product"], row["city"] or ""
    product = c2.radio("Producto", PRODUCTS, index=PRODUCTS.index(default_product), key=f"dx_prod_{lead_id}")
    out = diagnostic_form(f"internal_dx_{lead_id}_{product}", product, default_city=city)
    if out:
        answers, result = out
        with session_scope() as s:
            repo.save_diagnostic(s, product, answers, result, lead_id=lead_id, author=data.current_user())
        data.bump()
        st.session_state["internal_dx"] = result
        if lead_id:
            st.success("Diagnóstico guardado y Lead Score actualizado.")
    if st.session_state.get("internal_dx"):
        show_diagnosis(st.session_state["internal_dx"])

    with st.expander("Historial de diagnósticos"):
        with session_scope() as s:
            st.dataframe(repo.diagnostics_df(s, data.data_mode()), use_container_width=True, hide_index=True)
