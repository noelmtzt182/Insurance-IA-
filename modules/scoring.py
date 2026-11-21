"""Lead Scoring transparente."""
from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import repository as repo
from database.session import session_scope
from services.scoring import WEIGHTS, recommended_action, suggested_followup
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, kpi_row, page_header
from utils.config import PRIORITIES, PRODUCTS
from utils.theme import PRIORITY_COLORS, SERIES


def render() -> None:
    page_header("Lead Scoring", "Calificación transparente de 0 a 100",
                "El score se recalcula automáticamente cada vez que cambia la información comercial del lead.")
    demo_banner()
    with st.expander("¿Cómo se calcula?", expanded=False):
        st.dataframe(pd.DataFrame([{"Variable": k, "Puntos máximos": v} for k, v in WEIGHTS.items()]),
                     hide_index=True, use_container_width=False)
        st.markdown("**Clasificación:** 80–100 Alta prioridad · 50–79 Media · 0–49 Exploratorio.  \n"
                    "El algoritmo **no usa datos médicos ni características personales sensibles** (edad, género, "
                    "salud, etc.): solo intención, solicitudes, presupuesto declarado, completitud e interacción.")

    leads = data.leads()
    if leads.empty:
        empty_state("No hay leads para calificar.")
        return
    counts = leads["priority"].value_counts()
    kpi_row([(p, f"{int(counts.get(p, 0)):,}", None) for p in PRIORITIES] +
            [("Score promedio", f"{leads['score'].mean():.0f}", None)])

    c1, c2 = st.columns([1.4, 1])
    with c1:
        fig = px.histogram(leads, x="score", color="priority", nbins=20, color_discrete_map=PRIORITY_COLORS,
                           category_orders={"priority": PRIORITIES}, title="Distribución de Lead Score")
        fig.update_traces(marker_line_color="#FFFFFF", marker_line_width=1)
        fig.update_layout(height=340, bargap=0.05, xaxis_title="Score", yaxis_title="Leads", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c2:
        by_prod = leads.groupby(["product", "priority"]).size().reset_index(name="Leads")
        fig = px.bar(by_prod, x="product", y="Leads", color="priority", color_discrete_map=PRIORITY_COLORS,
                     category_orders={"priority": PRIORITIES}, title="Prioridad por producto")
        fig.update_layout(height=340, xaxis_title=None, yaxis_title=None, legend_title_text="")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    f1, f2, f3 = st.columns(3)
    pr = f1.multiselect("Prioridad", PRIORITIES, default=PRIORITIES)
    pd_ = f2.multiselect("Producto", PRODUCTS, default=PRODUCTS)
    only_active = f3.toggle("Solo leads activos", value=True)
    view = leads[leads["priority"].isin(pr) & leads["product"].isin(pd_)]
    if only_active:
        view = view[~view["stage"].isin(["Póliza emitida", "Perdido"])]
    view = view.sort_values("score", ascending=False).copy()
    view["Acción recomendada"] = [recommended_action(r) for r in view.to_dict("records")]
    view["Fecha de seguimiento"] = [suggested_followup(r) for r in view.to_dict("records")]
    view["Explicación"] = [" · ".join(f"{x['factor']}: {x['puntos']}/{x['maximo']}" for x in json.loads(r or "[]"))
                           for r in view["score_reasons"]]
    table = view[["id", "name", "product", "stage", "score", "priority", "Explicación", "Acción recomendada",
                  "Fecha de seguimiento"]].rename(columns={"id": "ID", "name": "Nombre", "product": "Producto",
                                                           "stage": "Etapa", "score": "Score", "priority": "Prioridad"})
    event = st.dataframe(table, use_container_width=True, hide_index=True, on_select="rerun",
                         selection_mode="single-row", key="score_table",
                         column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                                        "Fecha de seguimiento": st.column_config.DateColumn(format="DD/MM/YYYY")})
    c1, c2 = st.columns(2)
    c1.download_button("Exportar CSV", csv_bytes(table), "lead_scoring.csv", "text/csv")
    if c2.button("Recalcular todos los scores"):
        with session_scope() as s:
            n = repo.recalc_all_scores(s, data.data_mode())
        data.bump()
        st.success(f"{n} leads recalculados.")

    rows = event.selection.rows if event and event.selection else []
    if rows:
        r = view.iloc[rows[0]]
        st.markdown(f"##### #{r['id']} · {r['name']} — {r['score']}/100 ({r['priority']})")
        reasons = pd.DataFrame(json.loads(r["score_reasons"] or "[]"))
        if not reasons.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(y=reasons["factor"], x=reasons["maximo"], orientation="h", name="Máximo",
                                 marker_color="#E1E6EE", hoverinfo="skip"))
            fig.add_trace(go.Bar(y=reasons["factor"], x=reasons["puntos"], orientation="h", name="Obtenido",
                                 marker_color=SERIES[0], text=reasons["puntos"], textposition="outside",
                                 hovertemplate="%{y}: %{x} pts<extra></extra>"))
            fig.update_layout(barmode="overlay", height=300, yaxis=dict(autorange="reversed"), xaxis_title="Puntos")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.dataframe(reasons.rename(columns={"factor": "Factor", "puntos": "Puntos", "maximo": "Máximo",
                                                 "detalle": "Razón"}), hide_index=True, use_container_width=True)
        st.markdown(f"**Acción recomendada:** {r['Acción recomendada']}  \n"
                    f"**Seguimiento sugerido:** {r['Fecha de seguimiento'] or '—'}")
    else:
        st.caption("Selecciona una fila para ver el desglose del score.")
