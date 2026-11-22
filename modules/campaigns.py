"""Campañas y ROI."""
from __future__ import annotations


import pandas as pd
import plotly.express as px
import streamlit as st

from database import repository as repo
from database.session import session_scope
from services import metrics as m
from utils import data
from utils.components import csv_bytes, demo_banner, flash, kpi_row, page_header
from utils.config import CAMPAIGN_STATUS, DATA_ORIGINS, PLATFORMS, PRODUCTS, SEGMENTS, today_mx
from utils.theme import SERIES

FMT = {"Inversión": st.column_config.NumberColumn(format="$%,.0f"),
       "CPC": st.column_config.NumberColumn(format="$%.2f"), "CPL": st.column_config.NumberColumn(format="$%,.2f"),
       "CAC": st.column_config.NumberColumn(format="$%,.0f"),
       "Costo por cita": st.column_config.NumberColumn(format="$%,.0f"), "Comisiones": st.column_config.NumberColumn(format="$%,.0f"),
       "CTR %": st.column_config.NumberColumn(format="%.2f%%"),
       "Conversión %": st.column_config.NumberColumn(format="%.1f%%"),
       "ROAS comisiones": st.column_config.NumberColumn(format="%.2fx"),
       "Score promedio": st.column_config.NumberColumn(format="%.0f")}


def _opt_int(v):
    return None if v in (None, "") else int(v)


def _campaign_form(key: str, c: dict | None = None) -> dict | None:
    c = c or {}
    with st.form(key):
        a1, a2, a3, a4 = st.columns(4)
        name = a1.text_input("Campaña *", value=c.get("name", ""))
        platform = a2.selectbox("Plataforma", PLATFORMS, index=PLATFORMS.index(c["platform"]) if c.get("platform") in PLATFORMS else 0)
        product = a3.selectbox("Producto", [None] + PRODUCTS, format_func=lambda x: x or "Ambos / sin definir",
                               index=([None] + PRODUCTS).index(c.get("product")) if c.get("product") in PRODUCTS else 0)
        segment = a4.selectbox("Segmento", [None] + SEGMENTS, format_func=lambda x: x or "General",
                               index=([None] + SEGMENTS).index(c.get("segment")) if c.get("segment") in SEGMENTS else 0)
        b1, b2, b3, b4 = st.columns(4)
        status = b1.selectbox("Estado", CAMPAIGN_STATUS, index=CAMPAIGN_STATUS.index(c["status"]) if c.get("status") in CAMPAIGN_STATUS else 0)
        budget = b2.number_input("Presupuesto (MXN)", min_value=0.0, value=float(c.get("budget") or 0), step=1000.0)
        investment = b3.number_input("Inversión real (MXN)", min_value=0.0, value=float(c.get("investment") or 0), step=500.0)
        origin = b4.selectbox("Origen de los datos", [o for o in DATA_ORIGINS if o != "Demo"] if not c.get("is_demo") else DATA_ORIGINS,
                              index=DATA_ORIGINS.index(c["data_origin"]) if c.get("data_origin") in DATA_ORIGINS[:3] else 0,
                              help="Observado: tomado del administrador de anuncios. Importado: desde archivo/API. "
                                   "Estimado: proyección propia.")
        d1, d2, d3, d4 = st.columns(4)
        impressions = d1.number_input("Impresiones", min_value=0, value=int(c.get("impressions") or 0), step=1000)
        clicks = d2.number_input("Clics", min_value=0, value=int(c.get("clicks") or 0), step=10)
        start = d3.date_input("Inicio", value=c.get("start_date") or today_mx(), format="DD/MM/YYYY")
        end = d4.date_input("Fin (opcional)", value=c.get("end_date"), format="DD/MM/YYYY")
        st.caption("Resultados manuales: déjalos en blanco para usar los resultados atribuidos automáticamente desde el CRM.")
        e1, e2, e3, e4 = st.columns(4)
        leads_m = e1.text_input("Leads (manual)", value="" if c.get("leads_manual") is None else str(c["leads_manual"]))
        quotes_m = e2.text_input("Cotizaciones (manual)", value="" if c.get("quotes_manual") is None else str(c["quotes_manual"]))
        pol_m = e3.text_input("Pólizas (manual)", value="" if c.get("policies_manual") is None else str(c["policies_manual"]))
        com_m = e4.text_input("Comisiones MXN (manual)", value="" if c.get("commissions_manual") is None else str(c["commissions_manual"]))
        notes = st.text_input("Notas", value=c.get("notes") or "")
        ok = st.form_submit_button("Guardar campaña", type="primary")
    if not ok:
        return None
    try:
        out = {"name": name, "platform": platform, "product": product, "segment": segment, "status": status,
               "budget": budget or None, "investment": investment, "impressions": impressions or None,
               "clicks": clicks or None, "start_date": start, "end_date": end, "data_origin": origin,
               "leads_manual": _opt_int(leads_m), "quotes_manual": _opt_int(quotes_m),
               "policies_manual": _opt_int(pol_m), "commissions_manual": float(com_m) if com_m.strip() else None,
               "notes": notes or None}
    except ValueError:
        st.error("Los resultados manuales deben ser números.")
        return None
    return out


def render() -> None:
    page_header("Campañas y ROI", "Inversión, resultados y rentabilidad",
                "CPL = Inversión/Leads · CPC = Inversión/Clics · CTR = Clics/Impresiones×100 · CAC = Inversión/Pólizas · "
                "Conversión = Pólizas/Leads×100 · ROAS = Comisiones/Inversión.")
    demo_banner()
    flash()
    camps = data.campaigns()
    leads = data.leads()
    ct = m.campaign_table(camps, leads)
    acq = m.overall_acquisition(ct)
    kpi_row([("Inversión", m.fmt_money(acq["investment"]), None), ("CTR", m.fmt_pct(acq["CTR"], 2), None),
             ("CPC", m.fmt_money(acq["CPC"], 2), None), ("CPL", m.fmt_money(acq["CPL"], 2), None),
             ("Costo por cita", m.fmt_money(acq["cost_per_appt"]), None), ("CAC", m.fmt_money(acq["CAC"]), None),
             ("ROAS comisiones", m.fmt_ratio(acq["ROAS"]), None)])

    t1, t2, t3, t4 = st.tabs(["Resultados", "Registrar campaña", "Editar / eliminar", "Importar métricas CSV"])
    with t1:
        if ct.empty:
            st.info("Registra tu primera campaña o aprueba una propuesta del generador.")
        else:
            st.dataframe(ct.drop(columns=["id"]), use_container_width=True, hide_index=True, column_config=FMT)
            st.caption("«Origen de datos» describe las métricas de plataforma (observado/importado/estimado/demo); "
                       "«Origen resultados» indica si leads/pólizas vienen del CRM o se capturaron manualmente. "
                       "Un «—» significa que el indicador no es calculable (división entre cero o dato faltante).")
            st.download_button("Exportar CSV", csv_bytes(ct.drop(columns=["id"])), "campanas_roi.csv", "text/csv")
            c1, c2 = st.columns(2)
            with c1:
                p = ct.dropna(subset=["CPL"]).sort_values("CPL")
                fig = px.bar(p, x="CPL", y="Campaña", orientation="h", title="CPL por campaña (MXN)")
                fig.update_traces(marker_color=SERIES[0], hovertemplate="%{y}: $%{x:,.2f}<extra></extra>")
                fig.update_layout(height=360, yaxis=dict(autorange="reversed", title=None), xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            with c2:
                p = ct.dropna(subset=["ROAS comisiones"]).sort_values("ROAS comisiones", ascending=False)
                fig = px.bar(p, x="ROAS comisiones", y="Campaña", orientation="h", title="ROAS de comisiones")
                fig.update_traces(marker_color=SERIES[0], hovertemplate="%{y}: %{x:.2f}x<extra></extra>")
                fig.add_vline(x=1, line_dash="dot", line_color="#6B7585")
                fig.update_layout(height=360, yaxis=dict(autorange="reversed", title=None), xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with t2:
        new = _campaign_form("new_campaign")
        if new:
            try:
                with session_scope() as s:
                    repo.create_campaign(s, new, is_demo=data.write_mode_is_demo())
                data.bump()
                flash("Campaña registrada.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    with t3:
        if camps.empty:
            st.caption("Sin campañas.")
        else:
            cid = st.selectbox("Campaña", camps["id"].tolist(), format_func=lambda i: camps.set_index("id").loc[i, "name"])
            row = camps.set_index("id").loc[cid].to_dict()
            row = {k: (None if (not isinstance(v, str) and pd.isna(v)) else v) for k, v in row.items()}
            st.caption(f"utm_campaign: `{row['slug']}`")
            upd = _campaign_form(f"edit_campaign_{cid}", row)
            if upd:
                try:
                    with session_scope() as s:
                        repo.update_campaign(s, int(cid), upd)
                    data.bump()
                    flash("Campaña actualizada.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if st.checkbox("Quiero eliminar esta campaña (los leads se conservan sin campaña)", key=f"delc_{cid}"):
                if st.button("Eliminar campaña"):
                    with session_scope() as s:
                        repo.delete_campaign(s, int(cid))
                        repo.audit(s, data.current_user(), "Eliminar campaña", row["name"])
                    data.bump()
                    st.rerun()
    with t4:
        st.markdown("Actualiza inversión, impresiones y clics desde un reporte exportado de la plataforma. "
                    "Columnas: `campana`, `inversion`, `impresiones`, `clics` (coincidencia por nombre de campaña). "
                    "Los valores quedan con origen **Importado**.")
        up = st.file_uploader("Reporte CSV", type=["csv"], key="metrics_csv")
        if up is not None:
            try:
                rep = pd.read_csv(up, encoding="utf-8-sig")
            except (UnicodeDecodeError, pd.errors.ParserError) as exc:
                st.error(f"No se pudo leer el archivo: {exc}")
                return
            rep.columns = [c.strip().lower() for c in rep.columns]
            st.dataframe(rep.head(), hide_index=True)
            if "campana" not in rep.columns:
                st.error("Falta la columna «campana».")
            elif st.button("Aplicar métricas"):
                by_name = {n.lower(): i for i, n in zip(camps["id"], camps["name"])} if not camps.empty else {}
                updated, missing = 0, []
                with session_scope() as s:
                    for _, r in rep.iterrows():
                        cid = by_name.get(str(r["campana"]).strip().lower())
                        if cid is None:
                            missing.append(str(r["campana"]))
                            continue
                        ch = {"data_origin": "Importado"}
                        for col, field, conv in (("inversion", "investment", float), ("impresiones", "impressions", int),
                                                 ("clics", "clicks", int)):
                            if col in rep.columns and pd.notna(r[col]):
                                ch[field] = conv(r[col])
                        try:
                            repo.update_campaign(s, int(cid), ch)
                            updated += 1
                        except ValueError as e:
                            missing.append(f"{r['campana']} ({e})")
                data.bump()
                st.success(f"{updated} campañas actualizadas.")
                if missing:
                    st.warning("Sin coincidencia o con error: " + ", ".join(missing))
