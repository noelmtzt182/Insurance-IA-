"""Revenue Intelligence — dashboard de resultados de venta."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from database import sales_repository as srepo
from database.session import session_scope
from services import revenue
from services.metrics import fmt_int, fmt_money, fmt_pct, fmt_ratio
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, flash, kpi_row, page_header
from utils.config import today_mx
from utils.theme import SERIES

MONEY = {c: st.column_config.NumberColumn(format="$%,.0f") for c in
         ["Prima vendida", "Comisión esperada", "Comisión cobrada", "Inversión", "CAC", "Comisiones"]}
PCT = {c: st.column_config.NumberColumn(format="%.1f%%") for c in
       ["Conversión %", "Conversión con acción %", "Conversión sin acción %"]}


def render() -> None:
    page_header("Revenue Intelligence", "Resultados comerciales y rentabilidad",
                "La prima es lo que paga el cliente a la aseguradora; los ingresos del agente son las comisiones. "
                "ROAS y rentabilidad se calculan sobre comisiones.")
    demo_banner()
    flash()
    leads, camps, quotes = data.leads(), data.campaigns(), data.quotations()
    if leads.empty:
        empty_state("Sin datos de ventas en este conjunto.")
        return
    k = revenue.kpis(leads, camps, quotes)
    st.markdown("##### Ventas")
    kpi_row([("Prospectos", fmt_int(k["prospects"]), None), ("Cotizaciones", fmt_int(k["quotes"]),
             f"{k['quoted_leads']:,} prospectos cotizados"), ("Pólizas emitidas", fmt_int(k["policies"]), None),
             ("Conversión", fmt_pct(k["conversion"]), "Pólizas / prospectos")])
    st.markdown("##### Prima vs. ingresos del agente")
    kpi_row([("Prima total vendida", fmt_money(k["premium_sold"]), "Pagada por clientes a aseguradoras"),
             ("Comisiones esperadas", fmt_money(k["commission_expected"]), "Ingreso del agente"),
             ("Comisiones cobradas", fmt_money(k["commission_collected"]), fmt_pct(k["collection_rate"]) + " de lo esperado"),
             ("Comisiones por cobrar", fmt_money(k["commission_pending"]), None)])
    st.markdown("##### Adquisición y rentabilidad")
    kpi_row([("Costo de adquisición (CAC)", fmt_money(k["cac"]), "Inversión / pólizas"),
             ("ROAS (comisión esperada)", fmt_ratio(k["roas_expected"]), None),
             ("ROAS (comisión cobrada)", fmt_ratio(k["roas_collected"]), None),
             ("Resultado neto cobrado", fmt_money(k["net_profit_collected"]), "Comisión cobrada − inversión")])

    tabs = st.tabs(["Campañas", "Productos", "¿Quién contrata?", "Oportunidades perdidas", "Acciones comerciales",
                    "Cobranza de comisiones"])
    with tabs[0]:
        sc = revenue.sales_by_campaign(leads, camps)
        if sc.empty:
            st.caption("Sin campañas registradas.")
        else:
            fig = go.Figure()
            fig.add_bar(x=sc["Campaña"], y=sc["Inversión"], name="Inversión", marker_color=SERIES[0])
            fig.add_bar(x=sc["Campaña"], y=sc["Comisión esperada"], name="Comisión esperada", marker_color=SERIES[1])
            fig.add_bar(x=sc["Campaña"], y=sc["Comisión cobrada"], name="Comisión cobrada", marker_color=SERIES[2])
            fig.update_layout(barmode="group", title="¿Qué campañas generan más ventas? (MXN)", height=420,
                              xaxis_title=None, yaxis_title=None,
                              legend=dict(orientation="h", y=-0.35, x=0, xanchor="left", yanchor="top"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.dataframe(sc, hide_index=True, use_container_width=True,
                         column_config={**MONEY, **PCT, "ROAS (comisión esperada)": st.column_config.NumberColumn(format="%.2fx"),
                                        "ROAS (comisión cobrada)": st.column_config.NumberColumn(format="%.2fx")})
            st.download_button("Exportar CSV", csv_bytes(sc), "ventas_por_campana.csv", "text/csv")
    with tabs[1]:
        sp = revenue.sales_by_product(leads)
        st.dataframe(sp, hide_index=True, use_container_width=True, column_config={**MONEY, **PCT})
        if not sp.empty:
            fig = go.Figure(go.Bar(x=sp["Producto"], y=sp["Conversión %"], marker_color=SERIES[0],
                                   text=[fmt_pct(v) for v in sp["Conversión %"]], textposition="outside"))
            fig.update_layout(title="Conversión por producto (%)", height=320, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with tabs[2]:
        prof = revenue.buyer_profile(leads)
        if "_dias_cierre" in prof:
            d = prof.pop("_dias_cierre").iloc[0]
            st.markdown(f"Tiempo de captación a emisión: **{d['Días promedio a cierre']:.0f} días** en promedio "
                        f"(mediana {d['Mediana']:.0f}).")
        cols = st.columns(2)
        for i, (label, df) in enumerate(prof.items()):
            with cols[i % 2]:
                st.markdown(f"**{label}**")
                st.dataframe(df, hide_index=True, use_container_width=True, column_config=PCT)
        st.caption("Se analizan solo atributos comerciales (sin datos médicos ni características sensibles).")
    with tabs[3]:
        lost = revenue.lost_opportunities(leads)
        if not lost:
            st.caption("No hay oportunidades marcadas como perdidas.")
        else:
            r = lost["resumen"].iloc[0]
            st.markdown(f"**{int(r['Perdidos']):,}** oportunidades perdidas; **{int(r['Con cotización']):,}** ya tenían "
                        f"cotización (prima cotizada {fmt_money(r['Prima cotizada perdida'])}).")
            c1, c2 = st.columns(2)
            c1.dataframe(lost["por_etapa"], hide_index=True, use_container_width=True)
            c2.dataframe(lost["por_motivo"], hide_index=True, use_container_width=True)
            obj = data.objections()
            if not obj.empty:
                lost_obj = obj[obj["lead_stage"] == "Perdido"]["category"].value_counts()
                if len(lost_obj):
                    st.markdown("**Objeciones registradas en oportunidades perdidas**")
                    st.dataframe(lost_obj.rename_axis("Objeción").reset_index(name="Veces"), hide_index=True)
    with tabs[4]:
        eff = revenue.action_effectiveness(leads, data.activity(), data.objections())
        st.dataframe(eff, hide_index=True, use_container_width=True,
                     column_config={**PCT, "Diferencia (pp)": st.column_config.NumberColumn(format="%+.1f")})
        st.caption("Asociación observada entre acciones y contratación; no implica causalidad. Útil para decidir "
                   "qué prácticas reforzar y probar.")
    with tabs[5]:
        _commissions(leads)


def _commissions(leads) -> None:
    pol = leads[leads["stage"] == "Póliza emitida"].copy()
    if pol.empty:
        st.caption("Sin pólizas emitidas.")
        return
    pol["Por cobrar"] = pol["commission"].fillna(0) - pol["commission_paid"].fillna(0)
    show = pol[["id", "name", "product", "policy_number", "policy_date", "policy_premium", "commission",
                "commission_paid", "commission_paid_date", "Por cobrar"]].rename(columns={
        "id": "ID", "name": "Cliente", "product": "Producto", "policy_number": "Póliza", "policy_date": "Emisión",
        "policy_premium": "Prima anual", "commission": "Comisión esperada", "commission_paid": "Comisión cobrada",
        "commission_paid_date": "Fecha de cobro"})
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="$%,.0f") for c in
                                ["Prima anual", "Comisión esperada", "Comisión cobrada", "Por cobrar"]})
    pending = pol[pol["Por cobrar"] > 0]
    if pending.empty:
        st.success("Todas las comisiones registradas están cobradas.")
        return
    with st.form("commission_paid"):
        c1, c2, c3 = st.columns([2, 1, 1])
        lid = c1.selectbox("Póliza", pending["id"].tolist(),
                           format_func=lambda i: f"{pending.set_index('id').loc[i, 'name']} · "
                                                 f"{pending.set_index('id').loc[i, 'policy_number']}")
        amount = c2.number_input("Monto cobrado (MXN)", min_value=0.0,
                                 value=float(pending.set_index("id").loc[pending["id"].iloc[0], "commission"] or 0))
        when = c3.date_input("Fecha de cobro", value=today_mx(), format="DD/MM/YYYY")
        if st.form_submit_button("Registrar cobro", type="primary"):
            try:
                with session_scope() as s:
                    srepo.register_commission_payment(s, int(lid), amount, when, author=data.current_user())
                data.bump()
                flash("Cobro de comisión registrado.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
