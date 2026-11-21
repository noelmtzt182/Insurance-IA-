"""Motor A — Demand Intelligence.

Genera oportunidades de palabras clave con una heurística transparente.
NO inventa volúmenes de búsqueda, CPC ni competencia: esas columnas quedan
vacías salvo que se conecte Google Ads Keyword Planner con credenciales
autorizadas (ver integrations/google_ads.py).
"""
from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Optional

import pandas as pd

from utils.config import PRODUCT_GMM, PRODUCT_VIDA, now_mx

LINES = {
    "Seguros de vida": PRODUCT_VIDA,
    "Gastos médicos mayores": PRODUCT_GMM,
    "Seguros familiares": None,
    "Seguros para profesionistas independientes": None,
    "Seguros para empresarios": None,
    "Seguros colectivos": None,
}

BASE_TERMS = {
    PRODUCT_VIDA: ["seguro de vida", "seguro de vida familiar", "seguro de vida temporal", "seguro de vida con ahorro"],
    PRODUCT_GMM: ["seguro de gastos médicos mayores", "seguro de gastos médicos", "seguro médico privado",
                  "seguro médico familiar"],
}
COLLECTIVE_TERMS = {
    PRODUCT_VIDA: ["seguro de vida colectivo", "seguro de vida para empleados", "seguro de vida grupo"],
    PRODUCT_GMM: ["seguro de gastos médicos colectivo", "seguro médico para empleados", "gastos médicos para empresas"],
}

SEGMENT_MODIFIERS = {
    "Profesionistas independientes": ["para trabajadores independientes", "para freelancers",
                                      "para profesionistas independientes", "sin prestaciones"],
    "Padres de familia": ["para padres de familia", "para proteger a mi familia", "para mis hijos"],
    "Empresarios": ["para empresarios", "para dueños de negocio", "persona clave empresa"],
    "Emprendedores": ["para emprendedores", "para emprendedores sin prestaciones"],
    "Directivos": ["para directivos", "para ejecutivos", "complementario a prestaciones"],
    "Pequeñas y medianas empresas": ["para pymes", "para empleados de pyme", "para empresas pequeñas"],
}

INTENT_MODIFIERS = {
    "Alta": ["cotizar", "cotización", "contratar", "agente de", "asesor de", "precio"],
    "Media": ["mejor", "comparar", "qué cubre", "opiniones", "cuál conviene"],
    "Baja": ["qué es", "cómo funciona", "vale la pena", "para qué sirve"],
}

OBJECTIVE_BOOST = {
    "Solicitudes de cotización": {"Alta": 2, "Media": 0, "Baja": -1},
    "Generar leads": {"Alta": 1, "Media": 1, "Baja": 0},
    "Agendar citas": {"Alta": 2, "Media": 1, "Baja": -1},
    "Reconocimiento local": {"Alta": 0, "Media": 1, "Baja": 1},
}

SOURCE_HEURISTIC = "Heurística (sin métricas de búsqueda)"
SOURCE_KEYWORD_PLANNER = "Google Ads Keyword Planner"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def classify_intent(keyword: str) -> str:
    k = _norm(keyword)
    for level in ("Alta", "Baja", "Media"):
        if any(_norm(m) in k for m in INTENT_MODIFIERS[level]):
            return level
    # Términos de producto sin modificador: intención comercial media
    return "Media"


def match_type(intent: str) -> str:
    return "Exacta / frase" if intent == "Alta" else "Frase" if intent == "Media" else "Amplia con lista de negativas"


def generate_opportunities(line: str, segment: Optional[str], city: Optional[str], state: Optional[str],
                           objective: str, budget: Optional[float] = None, max_items: int = 40,
                           ref: Optional[datetime] = None) -> pd.DataFrame:
    """Devuelve oportunidades heurísticas ordenadas por prioridad."""
    ref = ref or now_mx()
    products = [LINES[line]] if LINES.get(line) else [PRODUCT_VIDA, PRODUCT_GMM]
    collective = line == "Seguros colectivos" or segment == "Pequeñas y medianas empresas"
    if line == "Seguros familiares" and not segment:
        segment = "Padres de familia"
    if line == "Seguros para profesionistas independientes" and not segment:
        segment = "Profesionistas independientes"
    if line == "Seguros para empresarios" and not segment:
        segment = "Empresarios"

    location = city or state
    candidates: list[tuple[str, str]] = []
    for product in products:
        bases = (COLLECTIVE_TERMS if collective else BASE_TERMS)[product]
        for base in bases:
            candidates.append((base, product))
            for lvl in ("Alta", "Media", "Baja"):
                mod = INTENT_MODIFIERS[lvl][0]
                candidates.append((f"{mod} {base}" if lvl != "Media" else f"{mod} {base}", product))
            if segment and segment in SEGMENT_MODIFIERS:
                for m in SEGMENT_MODIFIERS[segment][:3]:
                    candidates.append((f"{base} {m}", product))
                candidates.append((f"cotizar {base} {SEGMENT_MODIFIERS[segment][0]}", product))
            if location:
                candidates.append((f"{base} en {location}", product))
                candidates.append((f"cotizar {base} en {location}", product))
                candidates.append((f"agente de {base} en {location}", product))

    seen, rows = set(), []
    boost = OBJECTIVE_BOOST.get(objective, {"Alta": 1, "Media": 0, "Baja": 0})
    for kw, product in candidates:
        kw = " ".join(kw.split())
        key = _norm(kw)
        if key in seen:
            continue
        seen.add(key)
        intent = classify_intent(kw)
        points = {"Alta": 4, "Media": 2, "Baja": 1}[intent] + boost[intent]
        reasons = [f"intención {intent.lower()}"]
        if location and _norm(location) in key:
            points += 1
            reasons.append("término local")
        if segment and any(_norm(m) in key for m in SEGMENT_MODIFIERS.get(segment, [])):
            points += 1
            reasons.append("ajuste al segmento")
        priority = "Alta" if points >= 5 else "Media" if points >= 3 else "Baja"
        rows.append({
            "keyword": kw, "intent": intent, "segment": segment or "General", "product": product,
            "location": location or "México", "priority": priority, "_points": points,
            "match_type": match_type(intent), "rationale": ", ".join(reasons), "source": SOURCE_HEURISTIC,
            "updated_at": ref, "avg_monthly_searches": None, "competition": None, "low_bid": None, "high_bid": None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["_points", "keyword"], ascending=[False, True]).drop(columns="_points").head(max_items)
    return df.reset_index(drop=True)


def budget_guidance(budget: Optional[float], n_high: int) -> str:
    """Guía cualitativa: no calcula clics ni CPC (no hay datos reales sin Keyword Planner)."""
    if not budget:
        return "Sin presupuesto definido: empieza con las oportunidades de prioridad Alta y mide CPL real antes de ampliar."
    if budget < 10_000:
        return (f"Con un presupuesto acotado conviene concentrarse en pocas palabras de intención alta "
                f"(hay {n_high} de prioridad Alta) y en la ubicación más cercana a tu operación.")
    return ("El presupuesto permite probar 2 o 3 grupos de anuncios (intención alta, segmento, local) y "
            "comparar CPL y calidad de lead tras al menos 2 semanas.")


DISPLAY_COLUMNS = {
    "keyword": "Palabra clave", "intent": "Intención estimada", "segment": "Segmento", "product": "Producto",
    "location": "Ubicación", "priority": "Prioridad", "match_type": "Concordancia sugerida",
    "rationale": "Razón", "source": "Fuente de información", "updated_at": "Actualización",
    "avg_monthly_searches": "Búsquedas mensuales", "competition": "Competencia",
    "low_bid": "Puja baja (MXN)", "high_bid": "Puja alta (MXN)",
}
