"""Motor C — Automated Lead Capture.

Punto único de entrada para leads de cualquier origen (landing, formularios
internos, CSV, Google Ads Lead Forms, Meta Lead Ads, formularios externos).
Valida, normaliza, registra atribución/UTM, marca posibles duplicados (sin
borrar nada) y calcula el Lead Score.
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from database import repository as repo
from utils.config import BUDGET_RANGES, PRODUCT_GMM, PRODUCT_VIDA, SEGMENTS, SOURCES, today_mx
from utils.validation import validate_lead

UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower().strip())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace(" ", "_")


def attribution_from_params(params: dict) -> dict:
    """Extrae UTM, identificador de anuncio y click id de los parámetros de la URL."""
    out = {}
    for k in UTM_KEYS:
        v = params.get(k)
        if v:
            out[k] = str(v)[:150]
    ad = params.get("ad_id") or params.get("utm_content")
    if ad:
        out["ad_id"] = str(ad)[:80]
    click = params.get("gclid") or params.get("fbclid") or params.get("li_fat_id")
    if click:
        out["click_id"] = str(click)[:200]
    return out


def map_product(value) -> Optional[str]:
    v = _norm(value or "")
    if not v:
        return None
    if "vida" in v or v == "life":
        return PRODUCT_VIDA
    if "gmm" in v or "medic" in v or "gastos" in v or "salud" in v:
        return PRODUCT_GMM
    return None


def map_source(value) -> Optional[str]:
    if not value:
        return None
    v = _norm(value)
    for src in SOURCES:
        if _norm(src) == v or _norm(src).split("_")[0] == v:
            return src
    if "face" in v or v in ("fb", "meta"):
        return "Facebook Ads"
    if "google" in v:
        return "Google Ads"
    if "insta" in v:
        return "Instagram"
    if "linked" in v:
        return "LinkedIn"
    if "refer" in v:
        return "Referido"
    return "Otro"


def ingest(s: Session, raw: dict, *, channel: str, author: Optional[str] = None, require_consent: bool = True,
           is_demo: bool = False) -> tuple[Optional[int], list[str], bool]:
    """Valida y crea un lead. Devuelve (id, errores, es_posible_duplicado)."""
    data, errors = validate_lead(raw, require_consent=require_consent, today=today_mx())
    if errors:
        return None, errors, False
    lead = repo.create_lead(s, data, channel=channel, recorded_by=author, is_demo=is_demo)
    return lead.id, [], lead.dup_status is not None


# ---------------------------------------------------------------------------
# Importación CSV
# ---------------------------------------------------------------------------
FIELD_ALIASES = {
    "name": ["nombre", "name", "full_name", "nombre_completo", "cliente"],
    "phone": ["telefono", "phone", "phone_number", "celular", "movil", "whatsapp", "tel"],
    "email": ["correo", "email", "correo_electronico", "e-mail", "mail"],
    "city": ["ciudad", "city", "municipio"],
    "product": ["producto", "product", "seguro", "interes", "producto_de_interes"],
    "budget_range": ["presupuesto", "budget", "presupuesto_mensual"],
    "est_purchase_date": ["fecha_estimada", "fecha_contratacion", "fecha_estimada_de_contratacion"],
    "source": ["fuente", "source", "origen", "canal"],
    "segment": ["segmento", "segment", "perfil"],
    "utm_source": ["utm_source"], "utm_medium": ["utm_medium"], "utm_campaign": ["utm_campaign", "campana", "campaign"],
    "utm_term": ["utm_term"], "utm_content": ["utm_content"], "ad_id": ["ad_id", "anuncio", "id_anuncio"],
    "external_id": ["lead_id", "id_externo", "external_id"],
    "consent": ["consentimiento", "consent", "autoriza_contacto", "acepta_contacto"],
}
IMPORT_FIELDS = list(FIELD_ALIASES)


def auto_mapping(columns: list[str]) -> dict:
    norm_cols = {_norm(c): c for c in columns}
    mapping = {}
    for field, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if _norm(a) in norm_cols:
                mapping[field] = norm_cols[_norm(a)]
                break
    return mapping


def _truthy(v) -> bool:
    return _norm(v) in ("si", "sí", "yes", "true", "1", "x", "acepto", "s")


def _parse_date(v) -> Optional[date]:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(v, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


def import_dataframe(s: Session, df: pd.DataFrame, mapping: dict, *, default_product: Optional[str],
                     default_source: str, campaign_id: Optional[int], consent_attested: bool, author: str,
                     skip_duplicates: bool = False, channel: str = "importacion_csv") -> dict:
    """Importa filas. Reglas:
    * Solo se importan registros con consentimiento (columna o declaración del usuario).
    * Los duplicados se marcan para revisión (o se omiten si se elige), nunca se borran.
    """
    report = {"creados": 0, "duplicados_marcados": 0, "omitidos_duplicado": 0, "errores": []}
    for i, row in df.iterrows():
        get = lambda f: row[mapping[f]] if f in mapping and mapping[f] in row and pd.notna(row[mapping[f]]) else None
        consent = _truthy(get("consent")) if "consent" in mapping else consent_attested
        budget = get("budget_range")
        segment = get("segment")
        raw = {
            "name": get("name"), "phone": str(get("phone") or ""), "email": get("email"), "email_required": False,
            "city": get("city") or "Sin dato", "product": map_product(get("product")) or default_product,
            "budget_range": budget if budget in BUDGET_RANGES else None,
            "est_purchase_date": _parse_date(get("est_purchase_date")),
            "source": map_source(get("source")) or default_source,
            "segment": segment if segment in SEGMENTS else None,
            "campaign_id": campaign_id,
            "consent_contact": consent, "consent_privacy": consent,
        }
        for k in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ad_id", "external_id"):
            if get(k) is not None:
                raw[k] = str(get(k))
        if skip_duplicates and repo.find_duplicates(s, raw["phone"], raw.get("email")):
            report["omitidos_duplicado"] += 1
            continue
        lead_id, errors, dup = ingest(s, raw, channel=channel, author=author, require_consent=True)
        if errors:
            report["errores"].append({"fila": int(i) + 2, "errores": " ".join(errors)})
        else:
            report["creados"] += 1
            report["duplicados_marcados"] += int(dup)
    return report
