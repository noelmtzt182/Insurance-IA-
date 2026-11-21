"""AI Campaign Generator: generar, editar, aprobar, guardar y exportar campañas."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database import repository as repo
from database.session import session_scope
from integrations import llm
from services import campaign_generator as cg
from utils import data
from utils.components import csv_bytes, demo_banner, flash, page_header
from utils.config import AD_PLATFORMS, CITIES, OBJECTIVES, PRODUCTS, SEGMENTS

LIST_FIELDS = [("segmentation", "Segmentación sugerida"), ("keywords", "Palabras clave"),
               ("negative_keywords", "Palabras clave negativas"), ("headlines", "Titulares"),
               ("descriptions", "Descripciones"), ("value_props", "Propuestas de valor"),
               ("ctas", "Llamadas a la acción"), ("landing_structure", "Estructura de landing page"),
               ("ab_tests", "Pruebas A/B"), ("kpis", "Indicadores para evaluar resultados")]


def render() -> None:
    page_header("AI Campaign Generator", "Generador de campañas asistido por IA",
                "Genera la propuesta, edítala y apruébala. La app NO publica campañas: tú las implementas en cada plataforma.")
    demo_banner()
    flash()
    ai_ready = llm.is_configured()

    with st.form("gen_form"):
        c1, c2, c3 = st.columns(3)
        product = c1.selectbox("Producto", PRODUCTS)
        audience = c2.selectbox("Público objetivo", SEGMENTS)
        location = c3.selectbox("Ubicación", ["México"] + CITIES)
        c4, c5, c6 = st.columns(3)
        platform = c4.selectbox("Plataforma publicitaria", AD_PLATFORMS)
        budget = c5.number_input("Presupuesto mensual (MXN)", min_value=0.0, value=15000.0, step=1000.0)
        objective = c6.selectbox("Objetivo comercial", OBJECTIVES)
        use_ai = st.toggle("Usar IA (Claude)", value=ai_ready, disabled=not ai_ready,
                           help=None if ai_ready else "Configura ANTHROPIC_API_KEY para habilitarla; mientras tanto se usan plantillas.")
        ok = st.form_submit_button("Generar campaña", type="primary")
    if ok:
        inputs = {"product": product, "audience": audience, "location": location, "platform": platform,
                  "budget": budget or None, "objective": objective}
        with st.spinner("Generando propuesta…"):
            try:
                content, variants, by = cg.generate(inputs, use_ai=use_ai)
            except RuntimeError as exc:
                st.warning(f"La IA no respondió ({exc}). Se usaron plantillas.")
                content, variants, by = cg.generate(inputs, use_ai=False)
        with session_scope() as s:
            plan = repo.save_plan(s, inputs, content, variants, by, is_demo=data.write_mode_is_demo())
            st.session_state["plan_id"] = plan.id
        st.success(f"Propuesta #{plan.id} generada con {by} y guardada como borrador. No ha sido publicada.")

    with session_scope() as s:
        plans = repo.plans_df(s, data.data_mode())
    if plans.empty:
        st.info("Genera tu primera propuesta con el formulario de arriba.")
        return
    st.markdown("##### Propuestas guardadas")
    ids = plans["ID"].tolist()
    current = st.session_state.get("plan_id")
    pid = st.selectbox("Selecciona una propuesta", ids, index=ids.index(current) if current in ids else 0,
                       format_func=lambda i: f"#{i} · {plans.set_index('ID').loc[i, 'Nombre']} · "
                                             f"{plans.set_index('ID').loc[i, 'Estado']}")
    st.session_state["plan_id"] = pid
    _editor(pid)
    with st.expander("Listado de propuestas"):
        st.dataframe(plans, use_container_width=True, hide_index=True)


def _editor(pid: int) -> None:
    with session_scope() as s:
        plan = repo.get_plan(s, pid)
        content = json.loads(plan.content)
        variants = [{"id": v.id, "code": v.code, "angle": v.angle, "headline": v.headline,
                     "description": v.description, "cta": v.cta, "status": v.status} for v in plan.variants]
        meta = {"name": plan.name, "platform": plan.platform, "status": plan.status, "by": plan.generated_by,
                "campaign_id": plan.campaign_id, "product": plan.product, "audience": plan.audience,
                "location": plan.location, "objective": plan.objective, "budget": plan.budget}
        camp_slug = plan.campaign.slug if plan.campaign else None

    st.markdown(f"**Estado:** {meta['status']} · **Generado por:** {meta['by']} · **Plataforma:** {meta['platform']}")
    st.caption(content.get("status_note", "Contenido generado. No ha sido publicado."))

    tab_c, tab_v, tab_x, tab_img = st.tabs(["Contenido de campaña", "Variantes creativas", "Aprobar y exportar",
                                            "Imágenes y historias"])
    with tab_img:
        _creatives(pid, meta, variants)
    with tab_c:
        with st.form(f"plan_content_{pid}"):
            name = st.text_input("Nombre de campaña", value=meta["name"])
            edited = {}
            cols = st.columns(2)
            for i, (field, label) in enumerate(LIST_FIELDS):
                edited[field] = cols[i % 2].text_area(label, value="\n".join(content.get(field, [])), height=150,
                                                      help="Un elemento por línea.")
            if st.form_submit_button("Guardar cambios"):
                new_content = dict(content)
                for f, txt in edited.items():
                    new_content[f] = [x.strip() for x in txt.splitlines() if x.strip()]
                with session_scope() as s:
                    repo.update_plan_content(s, pid, name, new_content)
                st.success("Contenido actualizado.")
                st.rerun()
        issues = [f"«{h}»: {', '.join(cg.compliance_issues(h))}" for h in content.get("headlines", []) +
                  content.get("descriptions", []) if cg.compliance_issues(h)]
        if issues:
            st.warning("Revisión de cumplimiento: " + "; ".join(issues))

    with tab_v:
        st.caption("Edita cada variante y márcala como Aprobada o Descartada. El código se usa como utm_content para "
                   "medir qué anuncio genera mejores leads.")
        for v in variants:
            with st.form(f"variant_{v['id']}"):
                st.markdown(f"**{v['angle']}** · código `{v['code']}`")
                c1, c2 = st.columns([2, 1])
                headline = c1.text_input("Titular", value=v["headline"])
                cta = c2.text_input("Llamada a la acción", value=v["cta"])
                desc = st.text_area("Descripción / texto principal", value=v["description"], height=80)
                status = st.radio("Estado", ["Borrador", "Aprobada", "Descartada"], horizontal=True,
                                  index=["Borrador", "Aprobada", "Descartada"].index(v["status"]))
                problems = cg.length_issues(meta["platform"], headline, desc) + \
                    [f"Frase de riesgo: {p}" for p in cg.compliance_issues(headline + " " + desc)]
                for p in problems:
                    st.caption(f"⚠ {p}")
                if st.form_submit_button("Guardar variante"):
                    with session_scope() as s:
                        repo.update_variant(s, v["id"], headline, desc, cta, status)
                    st.rerun()

    with tab_x:
        approved = [v for v in variants if v["status"] == "Aprobada"]
        st.write(f"Variantes aprobadas: **{len(approved)}** de {len(variants)}.")
        if meta["status"] != "Aprobada":
            if st.button("Aprobar propuesta y crear campaña para seguimiento", type="primary",
                         disabled=not approved):
                try:
                    with session_scope() as s:
                        camp = repo.approve_plan(s, pid, data.current_user())
                        cname = camp.name
                    data.bump()
                    flash(f"Propuesta aprobada. Se creó la campaña «{cname}» con estado «Aprobada (pendiente de "
                          "publicar)». Publícala manualmente en la plataforma y registra su inversión en Campañas y ROI.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if not approved:
                st.caption("Aprueba al menos una variante para continuar.")
        else:
            st.success("Propuesta aprobada. Campaña vinculada para medir ROI.")

        settings = data.settings()
        rows = []
        for v in variants:
            url = cg.build_utm_url(settings.get("public_url") or "", meta["platform"], camp_slug, v["code"]) \
                if camp_slug else ""
            rows.append({"Campaña": meta["name"], "Plataforma": meta["platform"], "Producto": meta["product"],
                         "Público": meta["audience"], "Ubicación": meta["location"], "Objetivo": meta["objective"],
                         "Presupuesto mensual": meta["budget"], "Variante": v["code"], "Ángulo": v["angle"],
                         "Titular": v["headline"], "Descripción": v["description"], "CTA": v["cta"],
                         "Estado variante": v["status"], "URL final con UTM": url,
                         "Palabras clave": " | ".join(content.get("keywords", [])),
                         "Negativas": " | ".join(content.get("negative_keywords", []))})
        export = pd.DataFrame(rows)
        st.dataframe(export, use_container_width=True, hide_index=True)
        st.download_button("Exportar campaña (CSV)", csv_bytes(export), f"campana_{pid}.csv", "text/csv",
                           type="primary")
        if not camp_slug:
            st.caption("Las URL con UTM se generan al aprobar la propuesta.")
        if st.button("Eliminar propuesta", help="Elimina solo la propuesta; la campaña creada se conserva."):
            with session_scope() as s:
                repo.delete_plan(s, pid)
            st.session_state.pop("plan_id", None)
            st.rerun()


def _creatives(pid: int, meta: dict, variants: list[dict]) -> None:
    """Genera publicación (1080×1350) e historia (1080×1920) por cada variante aprobada."""
    from services import creatives

    st.caption("Crea las imágenes de tus anuncios con el texto de cada variante aprobada, tus colores, tu foto y "
               "tu logo. Descárgalas y súbelas a Meta Ads Manager o publícalas en tus redes.")
    approved = [v for v in variants if v["status"] == "Aprobada"]
    if not approved:
        st.info("Primero marca al menos una variante como «Aprobada» en la pestaña «Variantes creativas».")
        return
    settings = data.settings()
    with st.form(f"creatives_{pid}"):
        c1, c2 = st.columns(2)
        photo = c1.file_uploader("Foto (opcional): tú, tu equipo o una familia", type=["jpg", "jpeg", "png"],
                                 help="Usa fotos propias o con derechos de uso. Si no subes foto, se usa un fondo "
                                      "con tus colores.")
        logo = c2.file_uploader("Logo (opcional, PNG con fondo transparente)", type=["png"])
        c3, c4 = st.columns(2)
        brand = c3.text_input("Nombre que aparece arriba (si no hay logo)", value=settings.get("company_name", ""))
        eyebrow = c4.text_input("Texto pequeño sobre el titular", value=meta["product"])
        opts = {v["id"]: f"{v['code']} · {v['angle']}" for v in approved}
        chosen = st.multiselect("Variantes", list(opts), default=list(opts), format_func=lambda i: opts[i])
        fmts = st.multiselect("Formatos", list(creatives.FORMATS), default=list(creatives.FORMATS),
                              format_func=lambda k: creatives.FORMATS[k]["label"])
        ok = st.form_submit_button("Crear imágenes", type="primary")
    if ok:
        if not chosen or not fmts:
            st.error("Elige al menos una variante y un formato.")
            return
        photo_b = photo.getvalue() if photo else None
        logo_b = logo.getvalue() if logo else None
        images, errors = {}, []
        with st.spinner("Creando imágenes…"):
            for v in approved:
                if v["id"] not in chosen:
                    continue
                for f in fmts:
                    try:
                        images[f"{v['code']}_{f}.png"] = creatives.render(
                            f, v["headline"], v["description"], v["cta"], eyebrow=eyebrow.strip(),
                            brand_name=brand.strip(), photo=photo_b, logo=logo_b)
                    except ValueError as e:
                        errors.append(f"{v['code']}: {e}")
                    except Exception:  # imagen dañada o formato no soportado
                        errors.append(f"{v['code']}: no se pudo leer la foto o el logo; prueba con otro archivo.")
        st.session_state[f"ila_imgs_{pid}"] = images
        for e in errors:
            st.error(e)
    images = st.session_state.get(f"ila_imgs_{pid}") or {}
    if not images:
        return
    st.download_button("Descargar todas (ZIP)", creatives.zip_images(images), f"imagenes_campana_{pid}.zip",
                       "application/zip", type="primary")
    cols = st.columns(3)
    for i, (name, png) in enumerate(images.items()):
        with cols[i % 3]:
            st.image(png, caption=name, use_container_width=True)
            st.download_button("Descargar PNG", png, name, "image/png", key=f"dl_{pid}_{name}")
    st.caption("Revisa cada imagen antes de publicarla. Las historias dejan libre la parte superior e inferior, "
               "donde Instagram y Facebook muestran sus botones.")
