"""Cotizaciones — Smart Quotation Manager."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from database import sales_repository as srepo
from database.session import session_scope
from modules.sales_agent import lead_picker
from services import quotations as qsvc
from services.metrics import fmt_money
from utils import data
from utils.components import csv_bytes, demo_banner, empty_state, flash, kpi_row, page_header
from utils.config import PRODUCT_GMM, PRODUCTS, today_mx

STATUS_HELP = "Registrada → Enviada al prospecto → Aceptada / Rechazada / Vencida"


def render() -> None:
    page_header("Cotizaciones", "Smart Quotation Manager",
                "Registra cotizaciones OFICIALES de aseguradoras autorizadas, adjunta el PDF y compara hasta tres "
                "alternativas. La app no genera ni estima cotizaciones.")
    demo_banner()
    flash()
    leads = data.leads()
    quotes = data.quotations()
    if leads.empty:
        empty_state("No hay prospectos. Capta o selecciona datos en Configuración.")
        return
    exp = qsvc.expiring(quotes)
    kpi_row([("Cotizaciones", f"{len(quotes):,}", None),
             ("Enviadas sin respuesta", f"{int((quotes['status'] == 'Enviada').sum()):,}", None),
             ("Aceptadas", f"{int((quotes['status'] == 'Aceptada').sum()):,}", None),
             ("Por vencer (5 días)", f"{len(exp):,}", None)])
    t1, t2, t3 = st.tabs(["Registrar cotización", "Cotizaciones y estados", "Comparar alternativas"])
    with t1:
        _register(leads)
    with t2:
        _list(quotes)
    with t3:
        _compare(leads, quotes)


def _register(leads) -> None:
    lid = lead_picker(leads, "q_lead", active_only=True)
    if lid is None:
        empty_state("No hay prospectos activos.")
        return
    lead = leads.set_index("id").loc[lid]
    with st.form("quote_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        insurer = c1.text_input("Aseguradora *")
        product = c2.selectbox("Producto", PRODUCTS, index=PRODUCTS.index(lead["product"]))
        plan = c3.text_input("Plan / producto comercial")
        c4, c5, c6 = st.columns(3)
        period = c4.radio("Periodo de la prima", ["Anual", "Mensual"], horizontal=True)
        premium = c5.number_input("Prima (MXN) *", min_value=0.0, step=100.0)
        sum_insured = c6.number_input("Suma asegurada (MXN)", min_value=0.0, step=100000.0)
        st.caption("Datos de gastos médicos mayores (deja en 0 o vacío si no aplica o no viene en la cotización).")
        c7, c8, c9, c10 = st.columns(4)
        deductible = c7.number_input("Deducible (MXN)", min_value=0.0, step=1000.0)
        coins = c8.number_input("Coaseguro (%)", min_value=0.0, max_value=100.0, step=1.0)
        cap = c9.number_input("Tope de coaseguro (MXN)", min_value=0.0, step=1000.0)
        network = c10.text_input("Red hospitalaria")
        c11, c12 = st.columns(2)
        issue = c11.date_input("Fecha de la cotización", value=today_mx(), format="DD/MM/YYYY")
        valid = c12.date_input("Vigente hasta", value=today_mx() + timedelta(days=30),
                               format="DD/MM/YYYY")
        obs = st.text_area("Observaciones (exclusiones, periodos de espera, condiciones relevantes)", height=80)
        pdf = st.file_uploader("PDF de la cotización oficial (máx. 5 MB)", type=["pdf"])
        official = st.checkbox("Confirmo que estos datos provienen de una cotización oficial emitida por una "
                               "aseguradora autorizada.")
        ok = st.form_submit_button("Registrar cotización", type="primary")
    if ok:
        gmm = product == PRODUCT_GMM
        payload = {"insurer": insurer.strip(), "product": product, "plan_name": plan.strip() or None,
                   "premium_amount": premium, "premium_period": period, "sum_insured": sum_insured or None,
                   "deductible": (deductible or None) if gmm else None, "coinsurance_pct": (coins or None) if gmm else None,
                   "coinsurance_cap": (cap or None) if gmm else None,
                   "hospital_network": (network.strip() or None) if gmm else None, "issue_date": issue,
                   "valid_until": valid, "observations": obs.strip() or None, "official_confirmed": official,
                   "pdf_filename": pdf.name if pdf else None, "pdf_data": pdf.getvalue() if pdf else None}
        try:
            with session_scope() as s:
                q = srepo.add_quotation(s, int(lid), payload, author=data.current_user())
                qid = q.id
            data.bump()
            flash(f"Cotización #{qid} registrada. El prospecto pasó a «Cotización enviada» y su score se recalculó.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _list(quotes) -> None:
    if quotes.empty:
        empty_state("Sin cotizaciones registradas.")
        return
    c1, c2 = st.columns([2, 1])
    q = c1.text_input("Buscar por prospecto o aseguradora", key="q_search")
    status = c2.multiselect("Estado", srepo.QUOTE_STATUSES, placeholder="Todos", key="q_status")
    view = quotes
    if q:
        ql = q.lower()
        view = view[view["lead_name"].str.lower().str.contains(ql, regex=False) |
                    view["insurer"].str.lower().str.contains(ql, regex=False)]
    if status:
        view = view[view["status"].isin(status)]
    show = view[["id", "lead_name", "insurer", "product", "plan_name", "premium_amount", "premium_period",
                 "annual_premium", "sum_insured", "deductible", "coinsurance_pct", "valid_until", "status", "has_pdf"]]
    st.dataframe(show.rename(columns={"id": "ID", "lead_name": "Prospecto", "insurer": "Aseguradora",
                                      "product": "Producto", "plan_name": "Plan", "premium_amount": "Prima",
                                      "premium_period": "Periodo", "annual_premium": "Prima anual",
                                      "sum_insured": "Suma asegurada", "deductible": "Deducible",
                                      "coinsurance_pct": "Coaseguro %", "valid_until": "Vigencia", "status": "Estado",
                                      "has_pdf": "PDF"}),
                 hide_index=True, use_container_width=True,
                 column_config={"Prima": st.column_config.NumberColumn(format="$%,.2f"),
                                "Prima anual": st.column_config.NumberColumn(format="$%,.0f"),
                                "Suma asegurada": st.column_config.NumberColumn(format="$%,.0f"),
                                "Deducible": st.column_config.NumberColumn(format="$%,.0f"),
                                "Vigencia": st.column_config.DateColumn(format="DD/MM/YYYY")})
    st.download_button("Exportar CSV", csv_bytes(show), "cotizaciones.csv", "text/csv")
    if view.empty:
        return
    st.markdown("##### Gestionar cotización")
    ids = view["id"].tolist()
    qid = st.selectbox("Cotización", ids, format_func=lambda i: f"#{i} · {view.set_index('id').loc[i, 'lead_name']} · "
                                                              f"{view.set_index('id').loc[i, 'insurer']}")
    row = view.set_index("id").loc[qid]
    c1, c2 = st.columns([1, 1])
    with c1:
        new = st.selectbox("Estado", srepo.QUOTE_STATUSES, index=srepo.QUOTE_STATUSES.index(row["status"]),
                           help=STATUS_HELP, key=f"qs_{qid}")
        if st.button("Actualizar estado", key=f"qsb_{qid}"):
            with session_scope() as s:
                srepo.set_quotation_status(s, int(qid), new, author=data.current_user())
            data.bump()
            flash(f"Cotización #{qid}: {new}.")
            st.rerun()
        if row["has_pdf"]:
            with session_scope() as s:
                fname, blob = srepo.get_quotation_pdf(s, int(qid))
            st.download_button("Descargar PDF oficial", blob, fname or f"cotizacion_{qid}.pdf", "application/pdf")
    with c2, st.form(f"policy_from_q_{qid}"):
        st.markdown(f"**Registrar póliza emitida** (prima anual {fmt_money(row['annual_premium'], 2)})")
        number = st.text_input("Número de póliza")
        commission = st.number_input("Comisión esperada (MXN)", min_value=0.0, step=100.0,
                                     help="Ingreso del agente; no confundir con la prima.")
        pdate = st.date_input("Fecha de emisión", value=today_mx(), format="DD/MM/YYYY")
        if st.form_submit_button("Registrar póliza", type="primary", disabled=row["lead_stage"] == "Póliza emitida"):
            try:
                with session_scope() as s:
                    srepo.issue_policy_from_quotation(s, int(qid), number, commission, pdate, author=data.current_user())
                data.bump()
                flash("Póliza registrada: los indicadores de ventas se actualizaron.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _compare(leads, quotes) -> None:
    if quotes.empty:
        empty_state("Registra al menos dos cotizaciones de un prospecto para compararlas.")
        return
    with_q = leads[leads["id"].isin(quotes["lead_id"])]
    lid = lead_picker(with_q, "cmp_lead")
    lq = quotes[quotes["lead_id"] == lid]
    if len(lq) < 2:
        st.info("Este prospecto tiene menos de dos cotizaciones. Registra otra alternativa para comparar.")
        return
    opts = {int(r.id): f"#{r.id} · {r.insurer} · {r.plan_name or ''} · {r.status}" for r in lq.itertuples()}
    sel = st.multiselect("Selecciona 2 o 3 cotizaciones", list(opts), default=list(opts)[:3],
                         format_func=lambda i: opts[i], max_selections=qsvc.MAX_COMPARE)
    if len(sel) < 2:
        st.caption("Selecciona al menos dos.")
        return
    res = qsvc.compare(lq[lq["id"].isin(sel)])
    st.dataframe(res["table"], use_container_width=True)
    st.markdown("##### Diferencias de precio, cobertura y condiciones")
    for f in res["findings"]:
        st.markdown(f"- {f}")
    st.download_button("Exportar comparativo (CSV)", csv_bytes(res["table"].reset_index(names="Concepto")),
                       f"comparativo_{lid}.csv", "text/csv")
