"""Executive Dashboard."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from services import metrics as m
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, kpi_row, page_header
from utils.config import PRODUCTS, today_mx
from utils.theme import PRIORITY_COLORS, PRODUCT_COLORS, SERIES

CHART_CFG = {"displayModeBar": False}


def _filters(df: pd.DataFrame) -> pd.DataFrame:
    c1, c2, c3 = st.columns([2, 1.2, 1.2])
    min_d = df["created_at"].min().date() if not df.empty else today_mx() - timedelta(days=90)
    # La clave depende del conjunto de datos para que el rango se recalcule al cambiar entre reales y demo
    rng = c1.date_input("Periodo de captación", value=(max(min_d, today_mx() - timedelta(days=180)), today_mx()),
                        format="DD/MM/YYYY", key=f"dash_range_{data.data_mode()}_{min_d}")
    prod = c2.selectbox("Producto", ["Todos"] + PRODUCTS, key="dash_prod")
    src = c3.selectbox("Fuente", ["Todas"] + sorted(df["source"].dropna().unique().tolist()), key="dash_src")
    if isinstance(rng, tuple) and len(rng) == 2:
        d = df["created_at"].dt.normalize()
        df = df[(d >= pd.Timestamp(rng[0])) & (d <= pd.Timestamp(rng[1]))]
    if prod != "Todos":
        df = df[df["product"] == prod]
    if src != "Todas":
        df = df[df["source"] == src]
    return df


def _bar(df, x, y, title, color=SERIES[0], horizontal=False, text_fmt=None):
    fig = px.bar(df, x=y if horizontal else x, y=x if horizontal else y, orientation="h" if horizontal else "v",
                 title=title)
    fig.update_traces(marker_color=color, marker_line_width=0, hovertemplate="%{y}: %{x}<extra></extra>" if horizontal
                      else "%{x}: %{y}<extra></extra>")
    if horizontal:
        fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title=None)
    else:
        fig.update_layout(xaxis_title=None, yaxis_title=None)
    fig.update_layout(height=320)
    return fig


def render() -> None:
    page_header("Executive Dashboard", "Resultados de adquisición y conversión",
                "Todos los indicadores se calculan en tiempo real con los registros de la base de datos.")
    demo_banner()
    leads_all = data.leads()
    camps = data.campaigns()
    if leads_all.empty and camps.empty:
        empty_state("Aún no hay datos en este conjunto. Capta leads desde la landing pública, registra campañas o "
                    "carga datos demo en Configuración.")
        return
    df = _filters(leads_all) if not leads_all.empty else leads_all
    k = m.lead_kpis(df)
    ct = m.campaign_table(camps, df)
    acq = m.overall_acquisition(ct)

    st.markdown("##### Adquisición")
    kpi_row([
        ("Inversión publicitaria", m.fmt_money(acq["investment"]), "Campañas registradas"),
        ("Impresiones", m.fmt_int(acq["impressions"]), None),
        ("Clics", m.fmt_int(acq["clicks"]), None),
        ("CTR", m.fmt_pct(acq["CTR"], 2), "Clics / impresiones"),
        ("CPC", m.fmt_money(acq["CPC"], 2), "Inversión / clics"),
        ("Leads", m.fmt_int(k["total"]), "En el periodo filtrado"),
        ("CPL", m.fmt_money(acq["CPL"], 2), "Inversión / leads atribuidos"),
    ])
    st.markdown("##### Comercial")
    kpi_row([
        ("Leads calificados", m.fmt_int(k["qualified"]), m.fmt_pct(m.safe_div(k["qualified"], k["total"], 100))),
        ("Citas", m.fmt_int(k["appointments"]), None),
        ("Cotizaciones", m.fmt_int(k["quotes"]), None),
        ("Pólizas emitidas", m.fmt_int(k["policies"]), None),
        ("Conversión", m.fmt_pct(k["conversion"]), "Pólizas / leads"),
        ("CAC", m.fmt_money(acq["CAC"], 0), "Inversión / pólizas atribuidas"),
        ("Comisiones", m.fmt_money(k["commissions"]), "Pólizas emitidas"),
    ])
    st.write("")
    if df.empty:
        empty_state("No hay leads en el periodo seleccionado.")
        return

    c1, c2 = st.columns(2)
    with c1:
        fun = m.funnel_counts(df)
        fig = go.Figure(go.Funnel(y=fun["Etapa"], x=fun["Leads"], textinfo="value+percent initial",
                                  marker=dict(color=SERIES[0]),
                                  connector=dict(line=dict(color="#E1E6EE", width=1)),
                                  hovertemplate="%{y}: %{x} leads<extra></extra>"))
        fig.update_layout(title="Funnel comercial", height=360)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
    with c2:
        wk = m.weekly_series(df)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=wk["Semana"], y=wk["Leads"], name="Leads", mode="lines+markers",
                                 line=dict(color=SERIES[0], width=2), marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=wk["Semana"], y=wk["Pólizas"], name="Pólizas", mode="lines+markers",
                                 line=dict(color=SERIES[1], width=2), marker=dict(size=8)))
        fig.update_layout(title="Evolución semanal", height=360, hovermode="x unified", xaxis_title=None,
                          yaxis_title=None, xaxis=dict(tickformat="%d %b", automargin=True))
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

    c3, c4 = st.columns(2)
    with c3:
        by_src = df.groupby(df["source"].fillna("Sin dato")).size().reset_index(name="Leads").sort_values("Leads", ascending=False)
        st.plotly_chart(_bar(by_src, "source", "Leads", "Leads por fuente", horizontal=True),
                        use_container_width=True, config=CHART_CFG)
    with c4:
        by_c = df.groupby(df["campaign"].fillna("Sin campaña")).size().reset_index(name="Leads").sort_values("Leads", ascending=False).head(12)
        st.plotly_chart(_bar(by_c, "campaign", "Leads", "Leads por campaña", horizontal=True),
                        use_container_width=True, config=CHART_CFG)

    c5, c6 = st.columns(2)
    with c5:
        pc = m.product_conversion(df)
        fig = go.Figure()
        for _, r in pc.iterrows():
            fig.add_trace(go.Bar(x=[r["Producto"]], y=[r["Leads"]], name=r["Producto"],
                                 marker_color=PRODUCT_COLORS.get(r["Producto"], SERIES[2]),
                                 text=[f"{int(r['Leads'])} leads · {m.fmt_pct(r['Conversión %'])} conv."],
                                 textposition="outside", hovertemplate="%{x}: %{y} leads<extra></extra>"))
        fig.update_layout(title="Leads por producto", height=340, showlegend=False, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
    with c6:
        by_city = df.groupby(df["city"].fillna("Sin dato")).size().reset_index(name="Leads").sort_values("Leads", ascending=False).head(12)
        st.plotly_chart(_bar(by_city, "city", "Leads", "Leads por ciudad (top 12)", horizontal=True),
                        use_container_width=True, config=CHART_CFG)

    c7, c8 = st.columns(2)
    with c7:
        fig = px.histogram(df, x="score", color="priority", nbins=20, title="Distribución de Lead Score",
                           color_discrete_map=PRIORITY_COLORS,
                           category_orders={"priority": list(PRIORITY_COLORS)})
        fig.update_traces(marker_line_color="#FFFFFF", marker_line_width=1)
        fig.update_layout(height=360, xaxis_title="Score", yaxis_title="Leads", bargap=0.05, legend_title_text="")
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)
    with c8:
        if ct.empty:
            empty_state("Registra campañas para ver la conversión por campaña.")
        else:
            cc = ct.dropna(subset=["Conversión %"]).sort_values("Conversión %", ascending=False).head(12)
            fig = _bar(cc, "Campaña", "Conversión %", "Conversión por campaña (%)", color=SERIES[0],
                       horizontal=True)
            fig.update_traces(hovertemplate="%{y}: %{x:.1f}%<extra></extra>")
            st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

    if not ct.empty:
        ch = ct.groupby("Plataforma").agg(Inversión=("Inversión", "sum"), Comisiones=("Comisiones", "sum")).reset_index()
        ch_long = ch.melt(id_vars="Plataforma", var_name="Concepto", value_name="MXN")
        fig = px.bar(ch_long, x="Plataforma", y="MXN", color="Concepto", barmode="group",
                     title="Rentabilidad por canal (MXN)",
                     color_discrete_map={"Inversión": SERIES[0], "Comisiones": SERIES[1]})
        fig.update_layout(height=340, xaxis_title=None, yaxis_title=None, legend_title_text="")
        st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

    with st.expander("Ver tabla de campañas y exportar"):
        st.dataframe(ct.drop(columns=["id"]), use_container_width=True, hide_index=True)
        st.download_button("Exportar indicadores de campañas (CSV)", csv_bytes(ct.drop(columns=["id"])),
                           "indicadores_campanas.csv", "text/csv")
