"""Captación de Leads: formulario interno, importación CSV, duplicados y landing pública."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import repository as repo
from database.session import session_scope
from modules.forms import lead_form
from services import capture
from utils import data
from utils.components import demo_banner, page_header
from utils.config import PRODUCTS, SOURCES


def render() -> None:
    page_header("Captación de Leads", "Entrada de prospectos",
                "Todos los canales registran fuente, campaña, UTM, consentimiento y versión del aviso de privacidad.")
    demo_banner()
    t1, t2, t3, t4 = st.tabs(["Formulario interno", "Importar CSV", "Revisar duplicados", "Landing pública"])
    with t1:
        _internal_form()
    with t2:
        _csv_import()
    with t3:
        _duplicates()
    with t4:
        _public_link()


def _internal_form() -> None:
    settings = data.settings()
    with session_scope() as s:
        camps = repo.campaign_options(s, data.data_mode())
    raw = lead_form("internal_lead_form", public=False, settings=settings, campaigns=camps)
    if raw is not None:
        with session_scope() as s:
            lead_id, errors, dup = capture.ingest(s, raw, channel="captura_interna", author=data.current_user(),
                                                  is_demo=data.write_mode_is_demo())
        if errors:
            for e in errors:
                st.error(e)
        else:
            data.bump()
            st.success(f"Lead #{lead_id} guardado y calificado." +
                       (" ⚠ Se marcó como posible duplicado para revisión." if dup else ""))
    recent = data.leads()
    if not recent.empty:
        st.markdown("##### Últimos leads captados")
        st.dataframe(recent.head(15)[["id", "created_at", "name", "product", "source", "campaign", "score",
                                      "priority", "dup_status"]]
                     .rename(columns={"id": "ID", "created_at": "Fecha", "name": "Nombre", "product": "Producto",
                                      "source": "Fuente", "campaign": "Campaña", "score": "Score",
                                      "priority": "Prioridad", "dup_status": "Duplicado"}),
                     use_container_width=True, hide_index=True)


def _csv_import() -> None:
    st.markdown("Importa leads de otros formularios, eventos o plataformas. **Solo importa registros con "
                "consentimiento de contacto** obtenido legítimamente.")
    up = st.file_uploader("Archivo CSV (UTF-8)", type=["csv"])
    if up is None:
        st.caption("Columnas reconocidas: nombre, telefono, correo, ciudad, producto, presupuesto, fecha_estimada, "
                   "fuente, segmento, utm_source, utm_medium, utm_campaign, utm_term, utm_content, ad_id, "
                   "consentimiento (si/no).")
        return
    try:
        df = pd.read_csv(up, dtype=str, encoding="utf-8-sig")
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        st.error(f"No se pudo leer el archivo: {exc}")
        return
    if len(df) > 5000:
        st.error("Máximo 5,000 filas por importación.")
        return
    st.write(f"{len(df):,} filas detectadas.")
    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
    auto = capture.auto_mapping(df.columns.tolist())
    st.markdown("##### Mapeo de columnas")
    mapping = {}
    cols = st.columns(4)
    options = ["(no importar)"] + df.columns.tolist()
    for i, field in enumerate(capture.IMPORT_FIELDS):
        sel = cols[i % 4].selectbox(field, options, index=options.index(auto[field]) if field in auto else 0,
                                    key=f"map_{field}")
        if sel != "(no importar)":
            mapping[field] = sel
    with session_scope() as s:
        camps = repo.campaign_options(s, data.data_mode())
    c1, c2, c3 = st.columns(3)
    default_product = c1.selectbox("Producto por defecto (si falta)", [None] + PRODUCTS,
                                   format_func=lambda x: x or "Ninguno (rechazar fila)")
    default_source = c2.selectbox("Fuente por defecto", SOURCES, index=SOURCES.index("Otro"))
    opts = {None: "Sin campaña"} | camps
    campaign_id = c3.selectbox("Asignar campaña", list(opts), format_func=lambda k: opts[k])
    skip = st.checkbox("Omitir filas que coincidan con leads existentes (en lugar de marcarlas para revisión)")
    attest = False
    if "consent" not in mapping:
        attest = st.checkbox("Declaro que todos los registros del archivo otorgaron consentimiento de contacto y "
                             "conocieron el aviso de privacidad (queda registrado con mi usuario).")
    if not mapping.get("name") or not mapping.get("phone"):
        st.warning("Mapea al menos las columnas de nombre y teléfono.")
        return
    if st.button("Importar", type="primary", disabled=("consent" not in mapping and not attest)):
        with session_scope() as s:
            report = capture.import_dataframe(s, df, mapping, default_product=default_product,
                                              default_source=default_source, campaign_id=campaign_id,
                                              consent_attested=attest, author=data.current_user(),
                                              skip_duplicates=skip)
            repo.audit(s, data.current_user(), "Importación CSV",
                       f"{up.name}: {report['creados']} creados, {len(report['errores'])} con error")
        data.bump()
        st.success(f"Importación terminada: {report['creados']} creados, {report['duplicados_marcados']} marcados "
                   f"como posible duplicado, {report['omitidos_duplicado']} omitidos.")
        if report["errores"]:
            st.warning(f"{len(report['errores'])} filas con errores (no importadas):")
            st.dataframe(pd.DataFrame(report["errores"]), use_container_width=True, hide_index=True)


def _duplicates() -> None:
    st.markdown("Los posibles duplicados (mismo teléfono normalizado o correo) **no se eliminan**: revísalos y decide.")
    with session_scope() as s:
        dups = repo.duplicates_df(s, data.data_mode())
    if dups.empty:
        st.success("No hay posibles duplicados pendientes de revisión.")
        return
    st.dataframe(dups, use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns([1.2, 1, 1])
    lid = c1.selectbox("Lead a revisar (ID nuevo)", dups["ID nuevo"].tolist())
    if c2.button("No es duplicado"):
        with session_scope() as s:
            repo.resolve_duplicate(s, int(lid), "no_duplicado", data.current_user())
        data.bump()
        st.rerun()
    if c3.button("Confirmar duplicado", help="Se conserva el registro, se excluye de métricas y se completan datos "
                                             "faltantes del original."):
        with session_scope() as s:
            repo.resolve_duplicate(s, int(lid), "confirmar", data.current_user())
        data.bump()
        st.rerun()


def _public_link() -> None:
    settings = data.settings()
    base = (settings.get("public_url") or "http://localhost:8501").rstrip("/")
    st.markdown("La landing pública es independiente del panel: los prospectos **no pueden** ver registros comerciales.")
    st.code(f"{base}/registro", language=None)
    st.caption("Agrega parámetros UTM para atribuir campañas (usa el constructor en AI Lead Acquisition → Captura). "
               "Configura la URL pública en Configuración → Negocio.")
    page = st.session_state.get("_pages", {}).get("landing")
    if page:
        st.page_link(page, label="Ver la landing pública →")
