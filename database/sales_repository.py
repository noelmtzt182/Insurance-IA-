"""Acceso a datos del AI Sales & Conversion Engine.

Usa la MISMA base de datos y reutiliza las operaciones del CRM existente
(register_quote, register_policy, change_stage, add_note, set_next_action,
add_reminder) para que todos los módulos compartan la información.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import repository as repo
from database.models import AgentMessage, KnowledgeItem, Lead, Note, Objection, Quotation
from utils.config import PRODUCT_GMM, now_mx, today_mx

MAX_PDF_BYTES = 5 * 1024 * 1024
QUOTE_STATUSES = ["Registrada", "Enviada", "Aceptada", "Rechazada", "Vencida"]
OBJECTION_STATUSES = ["Pendiente", "Resuelta", "No resuelta"]


# ---------------------------------------------------------------------------
# Cotizaciones oficiales
# ---------------------------------------------------------------------------
def annual_premium(amount: Optional[float], period: str) -> Optional[float]:
    if amount is None:
        return None
    return float(amount) * 12 if period == "Mensual" else float(amount)


def validate_quotation(data: dict) -> list[str]:
    errors = []
    if not data.get("official_confirmed"):
        errors.append("Confirma que los datos provienen de una cotización oficial de una aseguradora autorizada.")
    if not (data.get("insurer") or "").strip():
        errors.append("Indica la aseguradora.")
    if data.get("premium_period") not in ("Mensual", "Anual"):
        errors.append("Periodo de prima inválido.")
    if not data.get("premium_amount") or data["premium_amount"] <= 0:
        errors.append("La prima debe ser mayor a cero.")
    for f, label in (("sum_insured", "suma asegurada"), ("deductible", "deducible"),
                     ("coinsurance_cap", "tope de coaseguro")):
        if data.get(f) is not None and data[f] < 0:
            errors.append(f"La {label} no puede ser negativa.")
    pct = data.get("coinsurance_pct")
    if pct is not None and not 0 <= pct <= 100:
        errors.append("El coaseguro debe estar entre 0 % y 100 %.")
    if data.get("valid_until") and data.get("issue_date") and data["valid_until"] < data["issue_date"]:
        errors.append("La vigencia no puede ser anterior a la fecha de emisión.")
    pdf = data.get("pdf_data")
    if pdf is not None:
        if len(pdf) > MAX_PDF_BYTES:
            errors.append("El PDF excede 5 MB.")
        elif not pdf.startswith(b"%PDF"):
            errors.append("El archivo no es un PDF válido.")
    return errors


QUOTE_FIELDS = ["insurer", "product", "plan_name", "premium_amount", "premium_period", "sum_insured", "deductible",
                "coinsurance_pct", "coinsurance_cap", "hospital_network", "issue_date", "valid_until",
                "observations", "pdf_filename", "pdf_data", "official_confirmed"]


def add_quotation(s: Session, lead_id: int, data: dict, author: Optional[str] = None) -> Quotation:
    """Registra la cotización oficial y actualiza el CRM con la operación existente register_quote."""
    errors = validate_quotation(data)
    if errors:
        raise ValueError(" ".join(errors))
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    q = Quotation(lead_id=lead_id, created_by=author, **{k: data.get(k) for k in QUOTE_FIELDS})
    q.product = data.get("product") or lead.product
    if q.product != PRODUCT_GMM:
        q.hospital_network = q.hospital_network or None
    s.add(q)
    s.flush()
    repo.register_quote(s, lead_id, annual_premium(q.premium_amount, q.premium_period), q.insurer,
                        q.issue_date or today_mx(), author=author)
    return q


def set_quotation_status(s: Session, quotation_id: int, status: str, author: Optional[str] = None) -> Quotation:
    if status not in QUOTE_STATUSES:
        raise ValueError("Estado inválido.")
    q = s.get(Quotation, quotation_id)
    if q is None:
        raise ValueError("Cotización no encontrada.")
    q.status = status
    if status == "Enviada":
        q.sent_at = now_mx()
    if status in ("Aceptada", "Rechazada"):
        q.responded_at = now_mx()
    if status == "Aceptada":
        q.lead.accepted_quotation_id = q.id
        if q.lead.stage in ("Cotización enviada", "Cita agendada", "Calificado", "Contactado", "Nuevo"):
            repo.change_stage(s, q.lead_id, "Negociación", author=author)
    s.add(Note(lead_id=q.lead_id, kind="Cotización", author=author,
               text=f"Cotización #{q.id} ({q.insurer}) marcada como {status}."))
    s.flush()
    return q


def issue_policy_from_quotation(s: Session, quotation_id: int, policy_number: str, commission: float,
                                policy_date: date, author: Optional[str] = None) -> Lead:
    q = s.get(Quotation, quotation_id)
    if q is None:
        raise ValueError("Cotización no encontrada.")
    q.status = "Aceptada"
    q.responded_at = q.responded_at or now_mx()
    q.lead.accepted_quotation_id = q.id
    return repo.register_policy(s, q.lead_id, policy_number, annual_premium(q.premium_amount, q.premium_period),
                                commission, policy_date, author=author)


def register_commission_payment(s: Session, lead_id: int, amount: float, paid_date: date,
                                author: Optional[str] = None) -> Lead:
    lead = s.get(Lead, lead_id)
    if lead is None or lead.stage != "Póliza emitida":
        raise ValueError("Solo se registran cobros de comisión para pólizas emitidas.")
    if amount is None or amount < 0:
        raise ValueError("El monto cobrado no puede ser negativo.")
    lead.commission_paid = float(amount)
    lead.commission_paid_date = paid_date
    s.add(Note(lead_id=lead_id, kind="Sistema", author=author,
               text=f"Comisión cobrada registrada: ${amount:,.2f} el {paid_date:%d/%m/%Y}."))
    s.flush()
    return lead


QUOTE_COLUMNS = ["id", "lead_id", "lead_name", "created_at", "insurer", "product", "plan_name", "premium_amount",
                 "premium_period", "annual_premium", "sum_insured", "deductible", "coinsurance_pct", "coinsurance_cap",
                 "hospital_network", "issue_date", "valid_until", "observations", "has_pdf", "status", "sent_at",
                 "responded_at", "lead_stage", "is_demo"]


def quotations_df(s: Session, mode: str = "reales", lead_id: Optional[int] = None) -> pd.DataFrame:
    stmt = select(Quotation, Lead).join(Lead)
    if mode == "reales":
        stmt = stmt.where(Lead.is_demo.is_(False))
    elif mode == "demo":
        stmt = stmt.where(Lead.is_demo.is_(True))
    if lead_id:
        stmt = stmt.where(Quotation.lead_id == lead_id)
    rows = s.execute(stmt.order_by(Quotation.created_at.desc())).all()
    out = []
    for q, l in rows:
        out.append({"id": q.id, "lead_id": l.id, "lead_name": l.name, "created_at": q.created_at, "insurer": q.insurer,
                    "product": q.product, "plan_name": q.plan_name, "premium_amount": q.premium_amount,
                    "premium_period": q.premium_period, "annual_premium": annual_premium(q.premium_amount, q.premium_period),
                    "sum_insured": q.sum_insured, "deductible": q.deductible, "coinsurance_pct": q.coinsurance_pct,
                    "coinsurance_cap": q.coinsurance_cap, "hospital_network": q.hospital_network,
                    "issue_date": q.issue_date, "valid_until": q.valid_until, "observations": q.observations,
                    "has_pdf": bool(q.pdf_filename), "status": q.status, "sent_at": q.sent_at,
                    "responded_at": q.responded_at, "lead_stage": l.stage, "is_demo": l.is_demo})
    return pd.DataFrame(out, columns=QUOTE_COLUMNS)


def get_quotation_pdf(s: Session, quotation_id: int) -> tuple[Optional[str], Optional[bytes]]:
    q = s.get(Quotation, quotation_id)
    return (q.pdf_filename, q.pdf_data) if q else (None, None)


# ---------------------------------------------------------------------------
# Objeciones
# ---------------------------------------------------------------------------
def add_objection(s: Session, lead_id: int, category: str, text: str = "", response: str = "",
                  status: str = "Pendiente", source: str = "agente", author: Optional[str] = None) -> Objection:
    if status not in OBJECTION_STATUSES:
        raise ValueError("Estado de objeción inválido.")
    o = Objection(lead_id=lead_id, category=category, text=(text or "").strip() or None,
                  response=(response or "").strip() or None, status=status, source=source, author=author)
    s.add(o)
    repo.add_note(s, lead_id, f"Objeción registrada: {category}" + (f" — «{text.strip()}»" if text and text.strip() else ""),
                  kind="Nota", author=author)
    s.flush()
    return o


def set_objection_status(s: Session, objection_id: int, status: str, response: Optional[str] = None) -> None:
    o = s.get(Objection, objection_id)
    if o is None or status not in OBJECTION_STATUSES:
        raise ValueError("Objeción o estado inválido.")
    o.status = status
    if response:
        o.response = response
    s.flush()


def objections_df(s: Session, mode: str = "reales", lead_id: Optional[int] = None) -> pd.DataFrame:
    stmt = select(Objection, Lead).join(Lead)
    if mode == "reales":
        stmt = stmt.where(Lead.is_demo.is_(False))
    elif mode == "demo":
        stmt = stmt.where(Lead.is_demo.is_(True))
    if lead_id:
        stmt = stmt.where(Objection.lead_id == lead_id)
    rows = s.execute(stmt.order_by(Objection.created_at.desc())).all()
    return pd.DataFrame([{"id": o.id, "lead_id": l.id, "lead_name": l.name, "created_at": o.created_at,
                          "category": o.category, "text": o.text, "response": o.response, "status": o.status,
                          "source": o.source, "lead_stage": l.stage} for o, l in rows],
                        columns=["id", "lead_id", "lead_name", "created_at", "category", "text", "response",
                                 "status", "source", "lead_stage"])


# ---------------------------------------------------------------------------
# Conversación del AI Sales Agent
# ---------------------------------------------------------------------------
def add_agent_message(s: Session, lead_id: int, role: str, text: str, intent: Optional[str] = None,
                      sources: Optional[list] = None, channel: str = "panel") -> AgentMessage:
    m = AgentMessage(lead_id=lead_id, role=role, text=text[:4000], intent=intent, channel=channel,
                     sources=json.dumps(sources, ensure_ascii=False) if sources else None)
    s.add(m)
    s.flush()
    return m


def agent_messages_df(s: Session, lead_id: int) -> pd.DataFrame:
    rows = s.scalars(select(AgentMessage).where(AgentMessage.lead_id == lead_id)
                     .order_by(AgentMessage.created_at, AgentMessage.id)).all()
    return pd.DataFrame([{"id": m.id, "created_at": m.created_at, "role": m.role, "text": m.text, "intent": m.intent,
                          "sources": json.loads(m.sources) if m.sources else [], "channel": m.channel} for m in rows],
                        columns=["id", "created_at", "role", "text", "intent", "sources", "channel"])


def request_handoff(s: Session, lead_id: int, reason: str, author: Optional[str] = None, channel: str = "panel") -> None:
    """Transfiere la conversación al agente humano: nota + recordatorio para hoy."""
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    repo.add_note(s, lead_id, f"Transferencia al agente humano ({channel}): {reason}", kind="Nota", author=author)
    if not repo.pending_reminder_exists(s, lead_id, "Transferencia a agente"):
        repo.add_reminder(s, lead_id, today_mx(), "Transferencia a agente",
                          f"El prospecto requiere atención personal: {reason}", template="Seguimiento",
                          created_by=author or "asistente")
    add_agent_message(s, lead_id, "asistente", "Conversación transferida al agente humano.", intent="transferencia",
                      channel=channel)


def request_appointment(s: Session, lead_id: int, preferred: date, slot: str, author: Optional[str] = None,
                        channel: str = "panel", confirm: bool = False) -> None:
    """Solicitud de cita. Si la registra el agente (confirm=True) pasa a 'Cita agendada'."""
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    lead.contact_requested = True
    action = f"Cita con el agente ({slot})"
    repo.set_next_action(s, lead_id, action, preferred, author=author)
    if confirm:
        if lead.stage not in ("Cotización enviada", "Negociación", "Póliza emitida"):
            repo.change_stage(s, lead_id, "Cita agendada", author=author)
    elif not repo.pending_reminder_exists(s, lead_id, "Solicitud de cita"):
        repo.add_reminder(s, lead_id, today_mx(), "Solicitud de cita",
                          f"El prospecto solicitó cita para el {preferred:%d/%m/%Y} ({slot}). Confirma por teléfono o WhatsApp.",
                          template="Confirmación de cita", created_by=author or "asistente")
    repo.rescore(lead)
    s.flush()


# ---------------------------------------------------------------------------
# Base de conocimiento validada
# ---------------------------------------------------------------------------
def add_knowledge(s: Session, data: dict, author: Optional[str] = None) -> KnowledgeItem:
    for f in ("topic", "question", "answer", "source"):
        if not (data.get(f) or "").strip():
            raise ValueError("Tema, pregunta, respuesta y fuente son obligatorios.")
    item = KnowledgeItem(product=data.get("product") or "General", insurer=(data.get("insurer") or "").strip() or None,
                         topic=data["topic"].strip(), question=data["question"].strip(), answer=data["answer"].strip(),
                         keywords=(data.get("keywords") or "").strip() or None, source=data["source"].strip(),
                         validated_by=author, validated_at=today_mx(), active=True)
    s.add(item)
    s.flush()
    return item


def set_knowledge_active(s: Session, item_id: int, active: bool) -> None:
    item = s.get(KnowledgeItem, item_id)
    if item:
        item.active = active
        s.flush()


def knowledge_items(s: Session, product: Optional[str] = None, only_active: bool = True) -> list[dict]:
    stmt = select(KnowledgeItem)
    if only_active:
        stmt = stmt.where(KnowledgeItem.active.is_(True))
    if product:
        stmt = stmt.where(or_(KnowledgeItem.product == product, KnowledgeItem.product == "General"))
    return [{"id": k.id, "product": k.product, "insurer": k.insurer, "topic": k.topic, "question": k.question,
             "answer": k.answer, "keywords": k.keywords, "source": k.source, "validated_by": k.validated_by,
             "validated_at": k.validated_at, "active": k.active} for k in s.scalars(stmt.order_by(KnowledgeItem.topic))]


# ---------------------------------------------------------------------------
# Historial comercial consolidado
# ---------------------------------------------------------------------------
def lead_history(s: Session, lead_id: int) -> dict:
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    diags = [{"fecha": d.created_at, "producto": d.product, "necesidad": d.need_level, "intencion": d.intent,
              "resultado": json.loads(d.result) if d.result and d.result.startswith("{") else {}}
             for d in sorted(lead.diagnostics, key=lambda d: d.created_at, reverse=True)]
    return {
        "lead": {c: getattr(lead, c) for c in repo.LEAD_COLUMNS},
        "notes": repo.notes_df(s, lead_id),
        "quotations": quotations_df(s, "todos", lead_id),
        "objections": objections_df(s, "todos", lead_id),
        "diagnostics": diags,
        "messages": agent_messages_df(s, lead_id),
    }


def activity_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    """Actividades comerciales (notas no automáticas) de todos los leads, para análisis de efectividad."""
    stmt = select(Note.lead_id, Note.kind).join(Lead).where(Note.kind != "Sistema")
    if mode == "reales":
        stmt = stmt.where(Lead.is_demo.is_(False))
    elif mode == "demo":
        stmt = stmt.where(Lead.is_demo.is_(True))
    return pd.DataFrame(s.execute(stmt).all(), columns=["lead_id", "kind"])
