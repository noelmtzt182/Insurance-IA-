"""AI Sales Agent — asistente comercial que acompaña al prospecto.

Fuentes de respuesta, en orden:
  1. Base de conocimiento VALIDADA por el agente (tabla knowledge_items, con fuente).
  2. Glosario general de conceptos de seguros (definiciones educativas, no condiciones de una aseguradora).
Si ninguna fuente responde la pregunta, el asistente NO improvisa: lo dice y ofrece transferir al agente humano.
Nunca menciona primas, coberturas, exclusiones ni condiciones que no estén en la base validada.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from services import sales_coach
from services.whatsapp import render_message
from utils.config import PRODUCT_GMM, PRODUCT_VIDA, STAGE_INDEX, today_mx

GLOSSARY_SOURCE = "Glosario general (concepto; las condiciones específicas dependen de cada póliza)"

# Cada concepto se activa solo si el mensaje menciona explícitamente uno de sus términos.
GLOSSARY = [
    {"topic": "Suma asegurada", "terms": ["suma asegurada"],
     "answer": "La suma asegurada es el monto máximo que la aseguradora pagaría según la póliza. En vida, es lo que "
               "recibirían los beneficiarios; en gastos médicos, es el límite para gastos cubiertos."},
    {"topic": "Deducible", "terms": ["deducible"],
     "answer": "El deducible es la cantidad inicial de un gasto médico cubierto que paga el asegurado antes de que "
               "la aseguradora empiece a pagar. Un deducible más alto suele reducir la prima, y viceversa."},
    {"topic": "Coaseguro", "terms": ["coaseguro"],
     "answer": "El coaseguro es el porcentaje del gasto (después del deducible) que paga el asegurado. Muchas pólizas "
               "tienen un tope de coaseguro, que limita cuánto pagarías por ese concepto."},
    {"topic": "Prima", "terms": ["que es la prima", "que es una prima", "la prima", "forma de pago", "pago fraccionado"],
     "answer": "La prima es lo que pagas por tu seguro, de forma anual o fraccionada (por ejemplo, mensual). "
               "Su monto lo determina la aseguradora en una cotización oficial."},
    {"topic": "Beneficiarios", "terms": ["beneficiario"],
     "answer": "Los beneficiarios son las personas que designas para recibir la suma asegurada de un seguro de vida. "
               "Puedes designar a una o varias y, en general, actualizarlas."},
    {"topic": "Periodo de espera", "terms": ["periodo de espera", "periodos de espera", "carencia"],
     "answer": "Algunas coberturas solo aplican después de cierto tiempo desde la contratación (periodo de espera). "
               "Cuáles y cuánto tiempo depende de las condiciones de cada póliza."},
    {"topic": "Preexistencias", "terms": ["preexistencia", "preexistente"],
     "answer": "Una preexistencia es un padecimiento que existía antes de contratar. Cómo se trata depende de las "
               "condiciones de la aseguradora; tu asesor puede revisarlo contigo directamente."},
    {"topic": "Red hospitalaria", "terms": ["red hospitalaria", "nivel hospitalario"],
     "answer": "La red hospitalaria es el conjunto de hospitales donde la póliza de gastos médicos tiene convenio. "
               "Cada plan incluye distintos niveles de hospitales."},
    {"topic": "Pago directo y reembolso", "terms": ["pago directo", "reembolso"],
     "answer": "En pago directo la aseguradora paga al hospital en convenio; en reembolso pagas tú y luego solicitas "
               "la devolución de los gastos cubiertos presentando tus comprobantes."},
    {"topic": "Seguro temporal y con ahorro", "terms": ["temporal", "con ahorro", "dotal", "vitalicio", "tipos de seguro de vida"],
     "answer": "Un seguro de vida temporal protege por un plazo definido; otros planes combinan protección con un "
               "componente de ahorro o son vitalicios. Cuál conviene depende de tus objetivos."},
    {"topic": "Proceso de contratación", "terms": ["como contrato", "proceso de contratacion", "pasos para contratar",
                                                   "que documentos", "requisitos para contratar"],
     "answer": "En general: 1) revisamos tus necesidades, 2) te presentamos cotizaciones oficiales, 3) llenas la "
               "solicitud de la aseguradora, 4) la aseguradora evalúa y, si acepta, emite la póliza."},
]


def _glossary_match(text: str) -> Optional[dict]:
    t = _norm(text)
    for g in GLOSSARY:
        if any(_norm(term) in t for term in g["terms"]):
            return g
    return None


STOPWORDS = set("el la los las un una unos unas de del al a y o que es en para por con mi me se lo le su sus "
                "como cual cuales cuando donde quien tengo tiene tienen hay mas muy ya si no te tu yo nos "
                "esto esta este eso ese seguro seguros".split())

INTENT_PATTERNS = [
    ("baja", ["darme de baja", "no me contacten", "ya no me escriban", "no me interesa", "dejen de", "stop", " baja"]),
    ("transferencia", ["hablar con", "con una persona", "humano", "con el asesor", "con un asesor", "con el agente",
                       "llamenme", "marquenme"]),
    ("cita", ["cita", "agendar", "reunion", "videollamada", "podemos vernos", "me llamas", "llamada"]),
    ("intencion_compra", ["quiero contratar", "me interesa contratar", "como lo contrato", "quiero cotizar",
                          "me lo quedo", "quiero el seguro", "vamos a hacerlo", "quiero una cotizacion"]),
    ("precio", ["cuanto cuesta", "precio", "cual es el costo", "que costo tiene", "cuanto sale", "cuanto pagaria", "cuanto es al mes", "tarifa"]),
]

HANDOFF_TEXT = ("No tengo información validada para responder eso con precisión y prefiero no darte un dato "
                "incorrecto. ¿Quieres que tu asesor te responda directamente?")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", _norm(text)) if len(w) > 2 and w not in STOPWORDS}


def classify(text: str) -> tuple[str, Optional[str]]:
    """Devuelve (intención, categoría de objeción si aplica)."""
    t = " " + _norm(text) + " "
    for intent, patterns in INTENT_PATTERNS:
        if any(_norm(p) in t for p in patterns):
            return intent, None
    obj = sales_coach.detect_objection(text)
    if obj:
        return "objecion", obj
    if re.match(r"^\s*(hola|buen[oa]s|que tal|saludos)\b", t.strip()) and len(_tokens(text)) <= 2:
        return "saludo", None
    return "pregunta", None


def _best_match(text: str, items: list[dict], fields: tuple[str, ...]) -> tuple[Optional[dict], int]:
    q = _tokens(text)
    best, best_score = None, 0
    for it in items:
        vocab = set()
        for f in fields:
            vocab |= _tokens(it.get(f) or "")
        score = len(q & vocab)
        if score > best_score:
            best, best_score = it, score
    return best, best_score


@dataclass
class AgentReply:
    intent: str
    reply: str
    sources: list[str] = field(default_factory=list)
    objection: Optional[str] = None
    handoff_suggested: bool = False
    intent_signal: Optional[str] = None  # Alta / Media / Baja
    appointment_suggested: bool = False
    opt_out: bool = False


def respond(text: str, product: Optional[str], knowledge: list[dict], name: str = "") -> AgentReply:
    """Respuesta determinística basada SOLO en fuentes validadas."""
    intent, objection = classify(text)
    first = (name or "").split(" ")[0]
    hi = f"{first}, " if first else ""
    if intent == "baja":
        return AgentReply(intent, "Entendido. Registramos tu solicitud y no volveremos a contactarte. Gracias por tu tiempo.",
                          opt_out=True)
    if intent == "transferencia":
        return AgentReply(intent, f"Claro {hi}te comunico con tu asesor. Te contactará por el medio que autorizaste.",
                          handoff_suggested=True)
    if intent == "cita":
        return AgentReply(intent, f"Con gusto {hi}agendamos una llamada con tu asesor. Indícame el día y horario que "
                                  "prefieras y te confirmamos.", appointment_suggested=True, intent_signal="Alta")
    if intent == "intencion_compra":
        return AgentReply(intent, f"¡Excelente{', ' + first if first else ''}! El siguiente paso es que tu asesor te presente cotizaciones "
                                  "oficiales de aseguradoras autorizadas. ¿Agendamos una llamada breve?",
                          appointment_suggested=True, intent_signal="Alta")
    if intent == "precio":
        return AgentReply(intent, "No puedo darte un precio: la prima depende de la aseguradora, la cobertura y tu "
                                  "perfil, y solo puede darse en una cotización oficial. Tu asesor puede prepararla "
                                  "sin compromiso. ¿Quieres que te contacte?",
                          handoff_suggested=True, intent_signal="Media")
    if intent == "objecion":
        play = sales_coach.OBJECTIONS[objection]
        return AgentReply(intent, play["response"], sources=["Guía de venta consultiva (AI Sales Coach)"],
                          objection=objection, intent_signal="Media")
    if intent == "saludo":
        return AgentReply(intent, "¡Hola! Soy el asistente de tu asesor. Puedo explicarte conceptos de seguros, resolver "
                                  "dudas frecuentes o agendar una llamada. ¿En qué te ayudo?")

    # Pregunta: base validada primero, luego glosario
    kb = [k for k in knowledge if not product or k["product"] in (product, "General")]
    item, score = _best_match(text, kb, ("question", "keywords", "topic"))
    if item and score >= 2:
        src = item["source"] + (f" · {item['insurer']}" if item.get("insurer") else "")
        return AgentReply("producto", item["answer"], sources=[src])
    gl = _glossary_match(text)
    if gl:
        return AgentReply("concepto", gl["answer"] + " Las condiciones exactas dependen de cada póliza; tu asesor puede "
                                                    "mostrártelas en la cotización oficial.",
                          sources=[f"{GLOSSARY_SOURCE}: {gl['topic']}"])
    return AgentReply("sin_informacion", HANDOFF_TEXT, handoff_suggested=True)


# ---------------------------------------------------------------------------
# Copiloto del agente: necesidades, intención, siguientes acciones y mensajes
# ---------------------------------------------------------------------------
def protection_needs(lead: dict, diagnostics: list[dict]) -> list[str]:
    needs = []
    for d in diagnostics[:1]:
        res = d.get("resultado") or {}
        needs += res.get("findings", [])
    if not needs:
        if lead.get("product") == PRODUCT_VIDA:
            needs.append("Interés en seguro de vida: confirmar dependientes económicos, deudas y metas a proteger.")
        else:
            needs.append("Interés en gastos médicos mayores: confirmar cobertura actual, asegurados y hospitales de preferencia.")
        needs.append("Aún no completa el diagnóstico: propón hacerlo juntos para identificar necesidades.")
    if lead.get("segment"):
        needs.append(f"Segmento declarado: {lead['segment']}.")
    if lead.get("budget_range"):
        needs.append(f"Presupuesto declarado: {lead['budget_range']}.")
    return needs


def purchase_intent(lead: dict, today: Optional[date] = None) -> tuple[str, list[str]]:
    today = today or today_mx()
    signals, pts = [], 0
    if lead.get("purchase_intent") == "Alta":
        pts += 3
        signals.append("Declaró intención alta")
    elif lead.get("purchase_intent") == "Media":
        pts += 2
        signals.append("Declaró intención media")
    est = lead.get("est_purchase_date")
    if est and (est - today).days <= 30:
        pts += 2
        signals.append("Fecha estimada de contratación ≤ 30 días")
    if lead.get("quote_requested"):
        pts += 1
        signals.append("Solicitó cotización")
    idx = STAGE_INDEX.get(lead.get("stage"), 0)
    if idx >= STAGE_INDEX["Cita agendada"]:
        pts += 2
        signals.append(f"Avanzó a {lead.get('stage')}")
    if (lead.get("score") or 0) >= 80:
        pts += 1
        signals.append("Lead Score ≥ 80")
    level = "Alta" if pts >= 5 else "Media" if pts >= 2 else "Baja"
    return level, signals or ["Sin señales claras todavía"]


def next_actions(lead: dict, quotations, objections, today: Optional[date] = None) -> list[dict]:
    """Acciones recomendadas priorizadas para un prospecto."""
    today = today or today_mx()
    acts = []
    stage = lead.get("stage")
    if stage in ("Póliza emitida", "Perdido"):
        return [{"Prioridad": "Baja", "Acción": sales_coach.STAGE_FOLLOW_UP.get(stage, ""), "Fecha": None}]
    if not lead.get("consent_contact"):
        acts.append({"Prioridad": "Alta", "Acción": "No contactar: el prospecto no tiene consentimiento de contacto.",
                     "Fecha": None})
        return acts
    pending = objections[objections["status"] == "Pendiente"] if len(objections) else objections
    for o in (pending.to_dict("records") if len(pending) else []):
        acts.append({"Prioridad": "Alta", "Acción": f"Atender objeción «{o['category']}»: "
                     + sales_coach.OBJECTIONS.get(o["category"], {}).get("follow_up", "dar seguimiento."),
                     "Fecha": today})
    if len(quotations):
        for q in quotations.to_dict("records"):
            vu = q.get("valid_until")
            if q["status"] in ("Registrada", "Enviada") and vu and 0 <= (vu - today).days <= 5:
                acts.append({"Prioridad": "Alta", "Acción": f"La cotización de {q['insurer']} vence el {vu:%d/%m}: "
                             "confirma decisión o solicita actualización.", "Fecha": today})
        if (quotations["status"] == "Registrada").any():
            acts.append({"Prioridad": "Media", "Acción": "Hay cotizaciones registradas sin enviar: compártelas y "
                         "márcalas como Enviadas.", "Fecha": today})
        if len(quotations) >= 2 and stage in ("Cotización enviada", "Negociación"):
            acts.append({"Prioridad": "Media", "Acción": "Envía el comparativo de alternativas y agenda una revisión guiada.",
                         "Fecha": today + timedelta(days=1)})
    elif STAGE_INDEX.get(stage, 0) >= STAGE_INDEX["Calificado"]:
        acts.append({"Prioridad": "Media", "Acción": "Solicita cotizaciones oficiales a las aseguradoras y regístralas.",
                     "Fecha": today + timedelta(days=2)})
    if not lead.get("diagnostic_completed"):
        acts.append({"Prioridad": "Media", "Acción": "Completa el diagnóstico de necesidades con el prospecto.",
                     "Fecha": today + timedelta(days=1)})
    acts.append({"Prioridad": "Media" if stage != "Nuevo" else "Alta",
                 "Acción": sales_coach.STAGE_FOLLOW_UP.get(stage, "Dar seguimiento."),
                 "Fecha": lead.get("next_action_date") or today + timedelta(days=1)})
    order = {"Alta": 0, "Media": 1, "Baja": 2}
    return sorted(acts, key=lambda a: order[a["Prioridad"]])


def prepared_messages(lead: dict, settings: dict, objections) -> dict[str, str]:
    ctx = {"nombre": lead.get("name"), "asesor": settings.get("advisor_name"), "empresa": settings.get("company_name"),
           "producto": str(lead.get("product") or "").lower(),
           "fecha": lead["next_action_date"].strftime("%d/%m/%Y") if lead.get("next_action_date") else None}
    stage = lead.get("stage")
    msgs = {}
    base = {"Nuevo": "Primer contacto", "Cotización enviada": "Seguimiento de cotización",
            "Cita agendada": "Confirmación de cita"}.get(stage, "Seguimiento")
    msgs[f"Plantilla: {base}"] = render_message(base, **ctx)
    first = (lead.get("name") or "").split(" ")[0]
    msgs["Solicitud de cita"] = (f"Hola {first}, soy {ctx['asesor']} de {ctx['empresa']}. Para revisar tus opciones de "
                                 f"{ctx['producto']} con calma, ¿te parece una llamada de 15 minutos? Dime qué día y "
                                 "horario te acomodan.")
    pend = objections[objections["status"] == "Pendiente"] if len(objections) else objections
    for o in (pend.to_dict("records") if len(pend) else [])[:2]:
        play = sales_coach.OBJECTIONS.get(o["category"])
        if play:
            msgs[f"Respuesta a objeción: {o['category']}"] = f"Hola {first}. " + play["response"]
    return msgs
