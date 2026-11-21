"""Modelos de datos (SQLAlchemy 2.0, portables entre SQLite y PostgreSQL)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from utils.config import now_mx


def new_uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    """Campaña publicitaria (registrada o generada). Nunca se publica desde la app."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)  # utm_campaign
    platform: Mapped[str] = mapped_column(String(60), default="Otro")
    product: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    segment: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    objective: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="Borrador")
    budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # presupuesto planeado
    investment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # inversión real
    impressions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    clicks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Resultados capturados manualmente. NULL => se usan los atribuidos desde el CRM.
    leads_manual: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quotes_manual: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    policies_manual: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    commissions_manual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_origin: Mapped[str] = mapped_column(String(20), default="Observado")  # Observado/Importado/Estimado/Demo
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, onupdate=now_mx)

    leads: Mapped[list["Lead"]] = relationship(back_populates="campaign")
    plans: Mapped[list["CampaignPlan"]] = relationship(back_populates="campaign")


class CampaignPlan(Base):
    """Propuesta de campaña generada por IA o plantillas (editable y aprobable)."""

    __tablename__ = "campaign_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    product: Mapped[str] = mapped_column(String(60))
    audience: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(40))
    budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    objective: Mapped[str] = mapped_column(String(60))
    content: Mapped[str] = mapped_column(Text)  # JSON con segmentación, keywords, landing, KPIs…
    generated_by: Mapped[str] = mapped_column(String(80))  # "Plantillas" o "IA (modelo)"
    status: Mapped[str] = mapped_column(String(30), default="Borrador")  # Borrador / Aprobada
    approved_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, onupdate=now_mx)

    campaign: Mapped[Optional[Campaign]] = relationship(back_populates="plans")
    variants: Mapped[list["AdVariant"]] = relationship(back_populates="plan", cascade="all, delete-orphan",
                                                       order_by="AdVariant.code")


class AdVariant(Base):
    __tablename__ = "ad_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("campaign_plans.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)  # se usa como utm_content / ad_id
    angle: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    cta: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="Borrador")  # Borrador / Aprobada / Descartada

    plan: Mapped[CampaignPlan] = relationship(back_populates="variants")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), default=new_uid, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, onupdate=now_mx)

    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(20), index=True)  # 10 dígitos normalizados
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    segment: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    product: Mapped[str] = mapped_column(String(60))
    budget_range: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    est_purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    purchase_intent: Mapped[str] = mapped_column(String(20), default="Sin definir")
    quote_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    diagnostic_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    interactions_count: Mapped[int] = mapped_column(Integer, default=0)

    # Atribución
    source: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"),
                                                       nullable=True, index=True)
    ad_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    click_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # gclid / fbclid
    capture_channel: Mapped[str] = mapped_column(String(40), default="landing_publica")
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    # Embudo
    stage: Mapped[str] = mapped_column(String(30), default="Nuevo", index=True)
    max_stage_index: Mapped[int] = mapped_column(Integer, default=0)
    lost_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    next_action: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    next_action_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    quote_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quote_insurer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quote_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    policy_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    policy_premium: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commission: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # comisión esperada
    policy_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Migración 1 (Sales & Conversion Engine)
    commission_paid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # comisión cobrada
    commission_paid_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    accepted_quotation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    priority: Mapped[str] = mapped_column(String(30), default="Exploratorio")
    score_reasons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Consentimiento
    consent_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_privacy: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    privacy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Deduplicación (nunca se borra automáticamente)
    duplicate_of: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    dup_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    campaign: Mapped[Optional[Campaign]] = relationship(back_populates="leads")
    notes: Mapped[list["Note"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    consents: Mapped[list["Consent"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    objections: Mapped[list["Objection"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    agent_messages: Mapped[list["AgentMessage"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class Note(Base):
    """Notas y actividades comerciales del lead."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    author: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="Nota")
    text: Mapped[str] = mapped_column(Text)

    lead: Mapped[Lead] = relationship(back_populates="notes")


class Consent(Base):
    """Registro verificable: qué texto aceptó, versión, huella SHA-256, canal y fecha."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    consent_type: Mapped[str] = mapped_column(String(40))  # contacto | aviso_privacidad
    notice_version: Mapped[str] = mapped_column(String(40))
    notice_sha256: Mapped[str] = mapped_column(String(64))
    text_snapshot: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(40))
    recorded_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="consents")


class Diagnostic(Base):
    __tablename__ = "diagnostics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    product: Mapped[str] = mapped_column(String(60))
    answers: Mapped[str] = mapped_column(Text)
    need_level: Mapped[str] = mapped_column(String(20))
    intent: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(Text)

    lead: Mapped[Optional[Lead]] = relationship(back_populates="diagnostics")


class Reminder(Base):
    """Recordatorio interno de seguimiento. No envía mensajes por sí mismo."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    rule: Mapped[str] = mapped_column(String(60))
    template: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Pendiente", index=True)  # Pendiente/Hecho/Descartado
    created_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="reminders")


class KeywordOpportunity(Base):
    """Oportunidad de búsqueda. Las métricas solo se llenan con datos de Keyword Planner."""

    __tablename__ = "keyword_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    product: Mapped[str] = mapped_column(String(60))
    segment: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    intent: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(60))  # "Heurística" | "Google Ads Keyword Planner"
    avg_monthly_searches: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competition: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    low_bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, onupdate=now_mx)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, onupdate=now_mx)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="asesor")  # admin | asesor
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    """Bitácora de acciones sensibles (exportaciones, borrados, cambios de configuración)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# AI Sales & Conversion Engine
# ---------------------------------------------------------------------------
class Quotation(Base):
    """Cotización OFICIAL emitida por una aseguradora autorizada (capturada por el agente).

    La app nunca genera ni estima estas cifras: solo registra lo que entrega la aseguradora.
    """

    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    created_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    insurer: Mapped[str] = mapped_column(String(120))
    product: Mapped[str] = mapped_column(String(60))
    plan_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    premium_amount: Mapped[float] = mapped_column(Float)
    premium_period: Mapped[str] = mapped_column(String(10))  # Mensual | Anual
    sum_insured: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    deductible: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coinsurance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coinsurance_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hospital_network: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_filename: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pdf_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    official_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="Registrada", index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="quotations")


class Objection(Base):
    __tablename__ = "objections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    author: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Pendiente")  # Pendiente | Resuelta | No resuelta
    source: Mapped[str] = mapped_column(String(30), default="agente")  # agente | asistente | coach

    lead: Mapped[Lead] = relationship(back_populates="objections")


class AgentMessage(Base):
    """Mensajes de la conversación del AI Sales Agent con un prospecto."""

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
    role: Mapped[str] = mapped_column(String(20))  # prospecto | asistente | agente
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    channel: Mapped[str] = mapped_column(String(30), default="panel")  # panel | landing

    lead: Mapped[Lead] = relationship(back_populates="agent_messages")


class KnowledgeItem(Base):
    """Información de producto validada por el agente (fuente obligatoria)."""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product: Mapped[str] = mapped_column(String(60))  # producto o "General"
    insurer: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    topic: Mapped[str] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(250))
    validated_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    validated_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(200))
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=now_mx)
