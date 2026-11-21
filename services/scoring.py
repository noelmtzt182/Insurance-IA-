"""Algoritmo de Lead Scoring (0-100) con razones explicables.

Pesos:
  - Intención de compra ........ 30
  - Solicitud de cotización .... 25
  - Presupuesto declarado ...... 15
  - Información completa ....... 10
  - Interacción ................ 10
  - Solicitud de contacto ...... 10

La función es pura (no toca la base de datos) para facilitar pruebas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from utils.config import (
    BUDGET_RANGES,
    IDX_APPOINTMENT,
    IDX_QUOTE,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    STAGE_INDEX,
    today_mx,
)

WEIGHTS = {
    "Intención de compra": 30,
    "Solicitud de cotización": 25,
    "Presupuesto declarado": 15,
    "Información completa": 10,
    "Interacción": 10,
    "Solicitud de contacto": 10,
}

INTENT_POINTS = {"Alta": 30, "Media": 18, "Baja": 8}

# Puntos por rango de presupuesto declarado (índices de BUDGET_RANGES)
BUDGET_POINTS = {
    "No lo sé aún": 2,
    "Menos de $500": 5,
    "$500 a $1,000": 8,
    "$1,000 a $2,000": 11,
    "$2,000 a $4,000": 14,
    "Más de $4,000": 15,
}
assert set(BUDGET_POINTS) == set(BUDGET_RANGES)

COMPLETENESS_FIELDS = {
    "name": "nombre",
    "phone": "teléfono",
    "email": "correo",
    "city": "ciudad",
    "product": "producto",
    "budget_range": "presupuesto",
    "est_purchase_date": "fecha estimada",
    "source": "fuente",
}

INTERACTION_POINTS = [0, 4, 7, 10]  # 0, 1, 2, 3+ interacciones


@dataclass
class ScoreResult:
    score: int
    priority: str
    reasons: list[dict] = field(default_factory=list)


def classify(score: int) -> str:
    if score >= 80:
        return PRIORITY_HIGH
    if score >= 50:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def _get(lead: Any, key: str, default=None):
    if isinstance(lead, dict):
        return lead.get(key, default)
    return getattr(lead, key, default)


def _filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    try:  # NaN de pandas
        return value == value
    except Exception:
        return True


def intent_from_date(est: Optional[date], ref: date) -> tuple[Optional[str], str]:
    if not est:
        return None, "sin fecha estimada de contratación"
    days = (est - ref).days
    if days < 0:
        return "Media", f"fecha estimada vencida hace {-days} días"
    if days <= 30:
        return "Alta", f"planea contratar en {days} días"
    if days <= 90:
        return "Media", f"planea contratar en {days} días"
    return "Baja", f"planea contratar en {days} días"


def score_lead(lead: Any, ref_date: Optional[date] = None) -> ScoreResult:
    ref = ref_date or today_mx()
    reasons: list[dict] = []
    stage = _get(lead, "stage") or "Nuevo"
    stage_idx = STAGE_INDEX.get(stage, -1)
    max_idx = max(stage_idx, int(_get(lead, "max_stage_index", 0) or 0))

    # 1) Intención de compra (30)
    explicit = _get(lead, "purchase_intent")
    if explicit in INTENT_POINTS:
        level, detail = explicit, "intención declarada en diagnóstico/CRM"
    else:
        level, detail = intent_from_date(_get(lead, "est_purchase_date"), ref)
    pts = INTENT_POINTS.get(level, 0)
    reasons.append(_reason("Intención de compra", pts, f"{level or 'Sin definir'}: {detail}"))

    # 2) Solicitud de cotización (25)
    quote = bool(_get(lead, "quote_requested")) or _filled(_get(lead, "quote_amount")) or max_idx >= IDX_QUOTE
    reasons.append(
        _reason(
            "Solicitud de cotización",
            25 if quote else 0,
            "solicitó o recibió cotización" if quote else "no ha solicitado cotización",
        )
    )

    # 3) Presupuesto (15)
    budget = _get(lead, "budget_range")
    pts = BUDGET_POINTS.get(budget, 0) if budget else 0
    reasons.append(
        _reason("Presupuesto declarado", pts, f"rango: {budget}" if budget else "sin presupuesto declarado")
    )

    # 4) Información completa (10)
    missing = [label for k, label in COMPLETENESS_FIELDS.items() if not _filled(_get(lead, k))]
    filled = len(COMPLETENESS_FIELDS) - len(missing)
    pts = round(10 * filled / len(COMPLETENESS_FIELDS))
    detail = "todos los campos completos" if not missing else f"faltan: {', '.join(missing)}"
    reasons.append(_reason("Información completa", pts, detail))

    # 5) Interacción (10)
    n = int(_get(lead, "interactions_count", 0) or 0)
    if _get(lead, "diagnostic_completed"):
        n += 1
    pts = INTERACTION_POINTS[min(n, 3)]
    reasons.append(_reason("Interacción", pts, f"{n} interacción(es) registradas (incluye diagnóstico)"))

    # 6) Solicitud de contacto (10)
    contact = bool(_get(lead, "contact_requested")) or max_idx >= IDX_APPOINTMENT
    reasons.append(
        _reason(
            "Solicitud de contacto",
            10 if contact else 0,
            "pidió ser contactado o agendó cita" if contact else "no ha pedido contacto",
        )
    )

    total = max(0, min(100, sum(r["puntos"] for r in reasons)))
    return ScoreResult(score=total, priority=classify(total), reasons=reasons)


def _reason(factor: str, pts: int, detail: str) -> dict:
    return {"factor": factor, "puntos": int(pts), "maximo": WEIGHTS[factor], "detalle": detail}


# ---------------------------------------------------------------------------
# Acción recomendada y fecha sugerida de seguimiento
# (solo usa datos comerciales; nunca datos médicos ni características sensibles)
# ---------------------------------------------------------------------------
STAGE_ACTIONS = {
    "Nuevo": "Primer contacto por llamada o WhatsApp",
    "Contactado": "Calificar necesidad y presupuesto",
    "Calificado": "Agendar cita de asesoría",
    "Cita agendada": "Confirmar cita y preparar propuesta",
    "Cotización enviada": "Dar seguimiento a la cotización",
    "Negociación": "Resolver objeciones y cerrar",
    "Póliza emitida": "Bienvenida y solicitar referidos",
    "Perdido": "Sin acción (reactivar solo si el prospecto lo solicita)",
}
FOLLOWUP_DAYS = {PRIORITY_HIGH: 1, PRIORITY_MEDIUM: 3, PRIORITY_LOW: 7}


def recommended_action(lead: Any) -> str:
    action = STAGE_ACTIONS.get(_get(lead, "stage") or "Nuevo", "Dar seguimiento")
    if _get(lead, "stage") in ("Nuevo", "Contactado") and _get(lead, "priority") == PRIORITY_HIGH:
        action += " (hoy, prioridad alta)"
    return action


def suggested_followup(lead: Any, ref_date: Optional[date] = None) -> Optional[date]:
    from datetime import timedelta
    ref = ref_date or today_mx()
    stage = _get(lead, "stage")
    if stage in ("Póliza emitida", "Perdido"):
        return None
    nad = _get(lead, "next_action_date")
    if _filled(nad):
        return nad
    return ref + timedelta(days=FOLLOWUP_DAYS.get(_get(lead, "priority"), 7))
