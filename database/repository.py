"""Capa de acceso a datos.

Todas las operaciones usan el ORM de SQLAlchemy con parámetros enlazados: no
existe concatenación de SQL con datos capturados por usuarios.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Iterable, Optional

import pandas as pd
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from database.models import (
    AdVariant,
    AuditLog,
    Campaign,
    CampaignPlan,
    Consent,
    Diagnostic,
    KeywordOpportunity,
    Lead,
    Note,
    Reminder,
    Setting,
)
from services.scoring import score_lead
from utils.config import (
    ALL_STAGES,
    DEFAULT_PRIVACY_NOTICE,
    DUP_CLEARED,
    DUP_CONFIRMED,
    DUP_POSSIBLE,
    IDX_QUOTE,
    STAGE_INDEX,
    STAGE_LOST,
    UTM_SOURCE_MAP,
    now_mx,
)
from utils.validation import normalize_phone

# ---------------------------------------------------------------------------
# Configuración y bitácora
# ---------------------------------------------------------------------------
SETTING_DEFAULTS = {
    "company_name": "Tu Agencia de Seguros",
    "advisor_name": "Tu asesor",
    "advisor_phone": "",
    "public_url": "",
    "privacy_notice": DEFAULT_PRIVACY_NOTICE,
    "privacy_version": "v1",
    "contact_consent_text": (
        "Autorizo que un asesor me contacte por teléfono, WhatsApp o correo electrónico para "
        "brindarme información y, en su caso, una cotización del producto de mi interés."
    ),
    "inactive_days": "14",
    "quote_followup_days": "3",
}


def get_settings(s: Session) -> dict:
    values = dict(SETTING_DEFAULTS)
    for row in s.scalars(select(Setting)):
        values[row.key] = row.value
    return values


def get_setting(s: Session, key: str) -> str:
    row = s.get(Setting, key)
    return row.value if row else SETTING_DEFAULTS.get(key, "")


def set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=str(value)))
    else:
        row.value = str(value)
    s.flush()


def audit(s: Session, username: Optional[str], action: str, detail: str = "") -> None:
    s.add(AuditLog(username=username, action=action, detail=detail[:2000]))
    s.flush()


def audit_df(s: Session, limit: int = 200) -> pd.DataFrame:
    rows = s.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return pd.DataFrame([{"Fecha": r.created_at, "Usuario": r.username, "Acción": r.action, "Detalle": r.detail}
                         for r in rows], columns=["Fecha", "Usuario", "Acción", "Detalle"])


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _mode_filter(stmt, model, mode: str):
    if mode == "reales":
        return stmt.where(model.is_demo.is_(False))
    if mode == "demo":
        return stmt.where(model.is_demo.is_(True))
    return stmt


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len] or "campana"


def rescore(lead: Lead) -> None:
    result = score_lead(lead)
    lead.score = result.score
    lead.priority = result.priority
    lead.score_reasons = json.dumps(result.reasons, ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Deduplicación (por teléfono normalizado o correo en minúsculas)
# ---------------------------------------------------------------------------
def find_duplicates(s: Session, phone: Optional[str], email: Optional[str], is_demo: bool = False,
                    exclude_id: Optional[int] = None) -> list[int]:
    conds = []
    phone = normalize_phone(phone)
    if phone:
        conds.append(Lead.phone == phone)
    if email:
        conds.append(func.lower(Lead.email) == email.strip().lower())
    if not conds:
        return []
    stmt = select(Lead.id).where(or_(*conds), Lead.is_demo.is_(is_demo),
                                 or_(Lead.dup_status.is_(None), Lead.dup_status != DUP_CONFIRMED))
    if exclude_id:
        stmt = stmt.where(Lead.id != exclude_id)
    return list(s.scalars(stmt.order_by(Lead.created_at)))


def duplicates_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    stmt = _mode_filter(select(Lead).where(Lead.dup_status == DUP_POSSIBLE), Lead, mode)
    rows = []
    for d in s.scalars(stmt.order_by(Lead.created_at.desc())):
        o = s.get(Lead, d.duplicate_of) if d.duplicate_of else None
        rows.append({
            "ID nuevo": d.id, "Nombre nuevo": d.name, "Teléfono": d.phone, "Correo nuevo": d.email,
            "Fuente nueva": d.source, "Fecha nuevo": d.created_at,
            "ID original": o.id if o else None, "Nombre original": o.name if o else None,
            "Correo original": o.email if o else None, "Etapa original": o.stage if o else None,
        })
    return pd.DataFrame(rows, columns=["ID nuevo", "Nombre nuevo", "Teléfono", "Correo nuevo", "Fuente nueva",
                                       "Fecha nuevo", "ID original", "Nombre original", "Correo original",
                                       "Etapa original"])


def resolve_duplicate(s: Session, lead_id: int, decision: str, author: Optional[str] = None) -> None:
    """decision: 'no_duplicado' | 'confirmar'. Nunca borra registros."""
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    if decision == "no_duplicado":
        lead.dup_status = DUP_CLEARED
        text = "Revisión de duplicado: no es duplicado."
    elif decision == "confirmar":
        lead.dup_status = DUP_CONFIRMED
        text = f"Revisión de duplicado: confirmado como duplicado del lead #{lead.duplicate_of}. Se excluye de métricas."
        if lead.duplicate_of:
            original = s.get(Lead, lead.duplicate_of)
            if original is not None:
                for f in ("email", "city", "segment", "budget_range", "est_purchase_date"):
                    if not getattr(original, f) and getattr(lead, f):
                        setattr(original, f, getattr(lead, f))
                original.interactions_count = (original.interactions_count or 0) + 1
                s.add(Note(lead_id=original.id, kind="Sistema", author=author,
                           text=f"Se recibió un registro duplicado (#{lead.id}) vía {lead.source or lead.capture_channel}."))
                rescore(original)
    else:
        raise ValueError("Decisión inválida.")
    s.add(Note(lead_id=lead.id, kind="Sistema", author=author, text=text))
    s.flush()


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
LEAD_EDITABLE = {
    "name", "phone", "email", "city", "segment", "product", "budget_range", "est_purchase_date", "source",
    "campaign_id", "ad_id", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "click_id",
    "external_id", "purchase_intent", "quote_requested", "contact_requested", "owner", "next_action",
    "next_action_date", "lost_reason", "quote_amount", "quote_insurer", "quote_date", "policy_number",
    "policy_premium", "commission", "policy_date",
}


def resolve_attribution(s: Session, data: dict) -> dict:
    """Completa campaña y fuente a partir de los parámetros UTM."""
    out = dict(data)
    if not out.get("campaign_id") and out.get("utm_campaign"):
        camp = s.scalar(select(Campaign).where(Campaign.slug == slugify(out["utm_campaign"]),
                                               Campaign.is_demo.is_(False)))
        if camp:
            out["campaign_id"] = camp.id
    if not out.get("source") and out.get("utm_source"):
        out["source"] = UTM_SOURCE_MAP.get(str(out["utm_source"]).lower().strip(), "Otro")
    if not out.get("ad_id") and out.get("utm_content"):
        out["ad_id"] = out["utm_content"]
    return out


def create_lead(s: Session, data: dict, *, channel: str = "landing_publica", recorded_by: Optional[str] = None,
                is_demo: bool = False) -> Lead:
    """Crea un lead, registra consentimiento verificable, marca posibles duplicados y lo califica."""
    data = resolve_attribution(s, data)
    lead = Lead(**{k: v for k, v in data.items() if k in LEAD_EDITABLE})
    lead.stage = data.get("stage", "Nuevo")
    lead.max_stage_index = STAGE_INDEX.get(lead.stage, 0)
    lead.capture_channel = channel
    lead.is_demo = is_demo
    lead.interactions_count = 0
    lead.diagnostic_completed = False
    lead.purchase_intent = data.get("purchase_intent") or "Sin definir"
    lead.quote_requested = bool(data.get("quote_requested"))
    lead.contact_requested = bool(data.get("contact_requested"))
    lead.consent_contact = bool(data.get("consent_contact"))
    lead.consent_privacy = bool(data.get("consent_privacy"))
    lead.created_at = data.get("created_at") or now_mx()
    lead.updated_at = lead.created_at
    settings = get_settings(s)
    if lead.consent_contact or lead.consent_privacy:
        lead.consent_at = lead.created_at
        lead.privacy_version = settings["privacy_version"]

    dups = find_duplicates(s, lead.phone, lead.email, is_demo=is_demo)
    if dups:
        lead.duplicate_of = dups[0]
        lead.dup_status = DUP_POSSIBLE
    s.add(lead)
    s.flush()

    for ctype, text in (("aviso_privacidad", settings["privacy_notice"]),
                        ("contacto", settings["contact_consent_text"])):
        accepted = lead.consent_privacy if ctype == "aviso_privacidad" else lead.consent_contact
        if accepted and not is_demo:
            s.add(Consent(lead_id=lead.id, consent_type=ctype, notice_version=settings["privacy_version"],
                          notice_sha256=_sha(text), text_snapshot=text, channel=channel,
                          recorded_by=recorded_by, accepted_at=lead.created_at))
    if not is_demo:
        msg = f"Lead creado vía {channel.replace('_', ' ')}."
        if dups:
            msg += f" Posible duplicado del lead #{dups[0]} (mismo teléfono o correo). Pendiente de revisión."
        s.add(Note(lead_id=lead.id, kind="Sistema", author=recorded_by or "sistema", text=msg))
    rescore(lead)
    s.flush()
    return lead


def external_id_exists(s: Session, external_id: str) -> bool:
    return s.scalar(select(Lead.id).where(Lead.external_id == str(external_id))) is not None


def get_lead(s: Session, lead_id: int) -> Optional[Lead]:
    return s.get(Lead, lead_id)


def update_lead(s: Session, lead_id: int, changes: dict, author: Optional[str] = None) -> Lead:
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} no existe")
    changed = []
    for key, value in changes.items():
        if key in LEAD_EDITABLE and getattr(lead, key) != value:
            setattr(lead, key, value)
            changed.append(key)
    if changes.get("stage") and changes["stage"] != lead.stage:
        change_stage(s, lead_id, changes["stage"], author=author, rescore_now=False)
        changed.append("stage")
    if changed:
        lead.updated_at = now_mx()
        s.add(Note(lead_id=lead.id, kind="Sistema", author=author, text="Datos actualizados: " + ", ".join(changed)))
        rescore(lead)
    s.flush()
    return lead


def change_stage(s: Session, lead_id: int, stage: str, author: Optional[str] = None,
                 lost_reason: Optional[str] = None, rescore_now: bool = True) -> Lead:
    if stage not in ALL_STAGES:
        raise ValueError(f"Etapa inválida: {stage}")
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} no existe")
    old = lead.stage
    if old == stage:
        return lead
    lead.stage = stage
    if stage in STAGE_INDEX:
        lead.max_stage_index = max(lead.max_stage_index or 0, STAGE_INDEX[stage])
    if stage == STAGE_LOST:
        lead.lost_reason = lost_reason or lead.lost_reason
    lead.updated_at = now_mx()
    s.add(Note(lead_id=lead.id, kind="Sistema", author=author,
               text=f"Etapa: {old} → {stage}" + (f" (motivo: {lost_reason})" if lost_reason else "")))
    if rescore_now:
        rescore(lead)
    s.flush()
    return lead


def register_quote(s: Session, lead_id: int, amount: float, insurer: Optional[str], quote_date: date,
                   author: Optional[str] = None) -> Lead:
    if amount is None or amount <= 0:
        raise ValueError("El monto de la cotización debe ser mayor a cero.")
    lead = s.get(Lead, lead_id)
    lead.quote_amount = float(amount)
    lead.quote_insurer = (insurer or "").strip() or None
    lead.quote_date = quote_date
    lead.quote_requested = True
    lead.interactions_count = (lead.interactions_count or 0) + 1
    s.add(Note(lead_id=lead.id, kind="Cotización", author=author,
               text=f"Cotización registrada: ${amount:,.2f} MXN anual" + (f" ({insurer})" if insurer else "")))
    if lead.stage != STAGE_LOST and STAGE_INDEX.get(lead.stage, 0) < IDX_QUOTE:
        change_stage(s, lead_id, "Cotización enviada", author=author, rescore_now=False)
    lead.updated_at = now_mx()
    rescore(lead)
    s.flush()
    return lead


def register_policy(s: Session, lead_id: int, policy_number: str, premium: float, commission: float,
                    policy_date: date, author: Optional[str] = None) -> Lead:
    if not (policy_number or "").strip():
        raise ValueError("Indica el número de póliza.")
    if premium is None or premium <= 0:
        raise ValueError("La prima debe ser mayor a cero.")
    if commission is None or commission < 0:
        raise ValueError("La comisión no puede ser negativa.")
    lead = s.get(Lead, lead_id)
    lead.policy_number = policy_number.strip()
    lead.policy_premium = float(premium)
    lead.commission = float(commission)
    lead.policy_date = policy_date
    s.add(Note(lead_id=lead.id, kind="Sistema", author=author,
               text=f"Póliza {lead.policy_number} emitida. Prima ${premium:,.2f}, comisión ${commission:,.2f}."))
    change_stage(s, lead_id, "Póliza emitida", author=author, rescore_now=False)
    rescore(lead)
    s.flush()
    return lead


def add_note(s: Session, lead_id: int, text: str, kind: str = "Nota", author: Optional[str] = None) -> Note:
    text = (text or "").strip()
    if not text:
        raise ValueError("La nota está vacía.")
    lead = s.get(Lead, lead_id)
    if lead is None:
        raise ValueError("Lead no encontrado.")
    note = Note(lead_id=lead_id, text=text[:4000], kind=kind, author=author)
    s.add(note)
    if kind != "Sistema":
        lead.interactions_count = (lead.interactions_count or 0) + 1
        if kind in ("Llamada", "WhatsApp", "Correo", "Reunión"):
            lead.last_contact_at = now_mx()
        lead.updated_at = now_mx()
        rescore(lead)
    s.flush()
    return note


def set_next_action(s: Session, lead_id: int, action: str, when: Optional[date], author: Optional[str] = None) -> Lead:
    lead = s.get(Lead, lead_id)
    lead.next_action = (action or "").strip() or None
    lead.next_action_date = when
    lead.updated_at = now_mx()
    s.add(Note(lead_id=lead_id, kind="Sistema", author=author,
               text=f"Seguimiento agendado: {lead.next_action or '—'}" + (f" el {when:%d/%m/%Y}" if when else "")))
    s.flush()
    return lead


def delete_lead(s: Session, lead_id: int, author: Optional[str] = None) -> None:
    """Eliminación manual (derecho de cancelación ARCO). Nunca se invoca automáticamente."""
    lead = s.get(Lead, lead_id)
    if lead is not None:
        audit(s, author, "Eliminar lead", f"Lead #{lead.id} eliminado manualmente (ARCO/cancelación).")
        s.delete(lead)
        s.flush()


def notes_df(s: Session, lead_id: int) -> pd.DataFrame:
    rows = s.scalars(select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at.desc(), Note.id.desc())).all()
    return pd.DataFrame([{"Fecha": n.created_at, "Tipo": n.kind, "Autor": n.author or "", "Detalle": n.text}
                         for n in rows], columns=["Fecha", "Tipo", "Autor", "Detalle"])


def consents_df(s: Session, lead_id: int) -> pd.DataFrame:
    rows = s.scalars(select(Consent).where(Consent.lead_id == lead_id)).all()
    return pd.DataFrame(
        [{"Tipo": c.consent_type, "Fecha": c.accepted_at, "Versión": c.notice_version, "Canal": c.channel,
          "Registrado por": c.recorded_by or "prospecto", "SHA-256": c.notice_sha256} for c in rows],
        columns=["Tipo", "Fecha", "Versión", "Canal", "Registrado por", "SHA-256"])


LEAD_COLUMNS = [
    "id", "uid", "created_at", "updated_at", "name", "phone", "email", "city", "segment", "product",
    "budget_range", "est_purchase_date", "purchase_intent", "quote_requested", "contact_requested",
    "diagnostic_completed", "interactions_count", "source", "campaign_id", "ad_id", "utm_source", "utm_medium",
    "utm_campaign", "utm_term", "utm_content", "click_id", "capture_channel", "stage", "max_stage_index",
    "lost_reason", "owner", "next_action", "next_action_date", "last_contact_at", "quote_amount", "quote_insurer",
    "quote_date", "policy_number", "policy_premium", "commission", "policy_date", "score", "priority",
    "score_reasons", "consent_contact", "consent_privacy", "consent_at", "privacy_version", "duplicate_of",
    "dup_status", "is_demo", "commission_paid", "commission_paid_date", "accepted_quotation_id",
]


def leads_df(s: Session, mode: str = "reales", include_confirmed_dups: bool = False) -> pd.DataFrame:
    stmt = _mode_filter(select(Lead), Lead, mode)
    if not include_confirmed_dups:
        stmt = stmt.where(or_(Lead.dup_status.is_(None), Lead.dup_status != DUP_CONFIRMED))
    rows = s.scalars(stmt.order_by(Lead.created_at.desc())).all()
    df = pd.DataFrame([{c: getattr(r, c) for c in LEAD_COLUMNS} for r in rows], columns=LEAD_COLUMNS)
    camps = {c.id: c.name for c in s.scalars(select(Campaign))}
    df["campaign"] = df["campaign_id"].map(camps)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["updated_at"] = pd.to_datetime(df["updated_at"])
    return df


def recalc_all_scores(s: Session, mode: str = "todos") -> int:
    n = 0
    for lead in s.scalars(_mode_filter(select(Lead), Lead, mode)):
        rescore(lead)
        n += 1
    s.flush()
    return n


# ---------------------------------------------------------------------------
# Diagnósticos
# ---------------------------------------------------------------------------
def save_diagnostic(s: Session, product: str, answers: dict, result: dict, lead_id: Optional[int] = None,
                    author: Optional[str] = None) -> Diagnostic:
    diag = Diagnostic(lead_id=lead_id, product=product, answers=json.dumps(answers, ensure_ascii=False, default=str),
                      need_level=result["need_level"], intent=result["intent"],
                      result=json.dumps(result, ensure_ascii=False, default=str))
    s.add(diag)
    if lead_id:
        lead = s.get(Lead, lead_id)
        if lead is not None:
            lead.diagnostic_completed = True
            if result.get("intent") in ("Alta", "Media", "Baja"):
                lead.purchase_intent = result["intent"]
            declared = answers.get("presupuesto")
            if declared and (declared != "No lo sé aún" or not lead.budget_range):
                lead.budget_range = declared
            lead.updated_at = now_mx()
            s.add(Note(lead_id=lead_id, kind="Sistema", author=author or "prospecto",
                       text=f"Diagnóstico de {product}: necesidad {result['need_level']}, intención {result['intent']}."))
            rescore(lead)
    s.flush()
    return diag


def diagnostics_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    stmt = select(Diagnostic, Lead.name).join(Lead, Diagnostic.lead_id == Lead.id, isouter=True)
    if mode == "reales":
        stmt = stmt.where(or_(Lead.is_demo.is_(False), Diagnostic.lead_id.is_(None)))
    elif mode == "demo":
        stmt = stmt.where(Lead.is_demo.is_(True))
    rows = s.execute(stmt.order_by(Diagnostic.created_at.desc()).limit(500)).all()
    return pd.DataFrame([{"Fecha": d.created_at, "Lead": name or "Sin vincular", "Producto": d.product,
                          "Necesidad": d.need_level, "Intención": d.intent} for d, name in rows],
                        columns=["Fecha", "Lead", "Producto", "Necesidad", "Intención"])


# ---------------------------------------------------------------------------
# Campañas
# ---------------------------------------------------------------------------
CAMPAIGN_FIELDS = {"name", "platform", "product", "segment", "location", "objective", "status", "budget",
                   "investment", "impressions", "clicks", "start_date", "end_date", "leads_manual", "quotes_manual",
                   "policies_manual", "commissions_manual", "data_origin", "notes"}


def _unique_slug(s: Session, base: str, is_demo: bool, exclude_id: Optional[int] = None) -> str:
    slug, i = base, 2
    while True:
        stmt = select(Campaign.id).where(Campaign.slug == slug, Campaign.is_demo.is_(is_demo))
        if exclude_id:
            stmt = stmt.where(Campaign.id != exclude_id)
        if s.scalar(stmt) is None:
            return slug
        slug, i = f"{base}-{i}", i + 1


def _validate_campaign_numbers(data: dict) -> None:
    for f in ("budget", "investment", "impressions", "clicks", "leads_manual", "quotes_manual", "policies_manual",
              "commissions_manual"):
        v = data.get(f)
        if v is not None and v < 0:
            raise ValueError(f"El campo {f} no puede ser negativo.")
    if data.get("impressions") is not None and data.get("clicks") is not None and data["clicks"] > data["impressions"]:
        raise ValueError("Los clics no pueden ser mayores que las impresiones.")


def create_campaign(s: Session, data: dict, is_demo: bool = False) -> Campaign:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("La campaña necesita un nombre.")
    _validate_campaign_numbers(data)
    if s.scalar(select(Campaign).where(func.lower(Campaign.name) == name.lower(), Campaign.is_demo.is_(is_demo))):
        raise ValueError(f"Ya existe una campaña llamada «{name}».")
    camp = Campaign(**{k: v for k, v in data.items() if k in CAMPAIGN_FIELDS}, is_demo=is_demo)
    camp.name = name
    camp.slug = _unique_slug(s, slugify(data.get("slug") or name), is_demo)
    s.add(camp)
    s.flush()
    return camp


def update_campaign(s: Session, campaign_id: int, changes: dict) -> Campaign:
    camp = s.get(Campaign, campaign_id)
    if camp is None:
        raise ValueError("La campaña no existe.")
    merged = {f: getattr(camp, f) for f in CAMPAIGN_FIELDS}
    merged.update({k: v for k, v in changes.items() if k in CAMPAIGN_FIELDS})
    _validate_campaign_numbers(merged)
    for k, v in changes.items():
        if k in CAMPAIGN_FIELDS:
            setattr(camp, k, v)
    s.flush()
    return camp


def delete_campaign(s: Session, campaign_id: int) -> None:
    camp = s.get(Campaign, campaign_id)
    if camp is not None:
        for lead in camp.leads:
            lead.campaign_id = None
        for plan in camp.plans:
            plan.campaign_id = None
        s.delete(camp)
        s.flush()


CAMPAIGN_COLUMNS = ["id", "name", "slug", "platform", "product", "segment", "location", "objective", "status",
                    "budget", "investment", "impressions", "clicks", "start_date", "end_date", "leads_manual",
                    "quotes_manual", "policies_manual", "commissions_manual", "data_origin", "notes", "is_demo"]


def campaigns_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    rows = s.scalars(_mode_filter(select(Campaign), Campaign, mode).order_by(Campaign.name)).all()
    return pd.DataFrame([{c: getattr(r, c) for c in CAMPAIGN_COLUMNS} for r in rows], columns=CAMPAIGN_COLUMNS)


def campaign_options(s: Session, mode: str = "reales") -> dict[int, str]:
    rows = s.scalars(_mode_filter(select(Campaign), Campaign, mode).order_by(Campaign.name)).all()
    return {c.id: c.name for c in rows}


# ---------------------------------------------------------------------------
# Planes de campaña (generador) y variantes
# ---------------------------------------------------------------------------
def save_plan(s: Session, inputs: dict, content: dict, variants: list[dict], generated_by: str,
              is_demo: bool = False) -> CampaignPlan:
    plan = CampaignPlan(
        name=content.get("campaign_name") or "Campaña sin nombre", product=inputs["product"],
        audience=inputs["audience"], location=inputs["location"], platform=inputs["platform"],
        budget=inputs.get("budget"), objective=inputs["objective"],
        content=json.dumps(content, ensure_ascii=False), generated_by=generated_by, is_demo=is_demo,
    )
    s.add(plan)
    s.flush()
    base = slugify(plan.name, 30)
    for i, v in enumerate(variants):
        s.add(AdVariant(plan_id=plan.id, code=f"{base}-{plan.id}-{chr(97 + i)}", angle=v.get("angle", "")[:120],
                        headline=v["headline"][:200], description=v["description"], cta=v.get("cta", "")[:60]))
    s.flush()
    return plan


def update_plan_content(s: Session, plan_id: int, name: str, content: dict) -> CampaignPlan:
    plan = s.get(CampaignPlan, plan_id)
    plan.name = name.strip() or plan.name
    plan.content = json.dumps(content, ensure_ascii=False)
    s.flush()
    return plan


def update_variant(s: Session, variant_id: int, headline: str, description: str, cta: str, status: str) -> AdVariant:
    v = s.get(AdVariant, variant_id)
    v.headline, v.description, v.cta, v.status = headline.strip(), description.strip(), cta.strip(), status
    s.flush()
    return v


def approve_plan(s: Session, plan_id: int, username: str) -> Campaign:
    """Aprueba la propuesta y crea (o vincula) la campaña para seguimiento de ROI.

    La campaña queda como "Aprobada (pendiente de publicar)": la app NO la publica.
    """
    plan = s.get(CampaignPlan, plan_id)
    if plan is None:
        raise ValueError("Propuesta no encontrada.")
    if not any(v.status == "Aprobada" for v in plan.variants):
        raise ValueError("Aprueba al menos una variante creativa antes de aprobar la campaña.")
    plan.status = "Aprobada"
    plan.approved_by = username
    plan.approved_at = now_mx()
    if plan.campaign_id is None:
        name = plan.name
        if s.scalar(select(Campaign).where(func.lower(Campaign.name) == name.lower(),
                                           Campaign.is_demo.is_(plan.is_demo))):
            name = f"{name} ({plan.id})"
        camp = create_campaign(s, {"name": name, "platform": plan.platform, "product": plan.product,
                                   "segment": plan.audience, "location": plan.location, "objective": plan.objective,
                                   "budget": plan.budget, "status": "Aprobada (pendiente de publicar)",
                                   "data_origin": "Observado",
                                   "notes": f"Creada desde la propuesta #{plan.id} ({plan.generated_by})."},
                               is_demo=plan.is_demo)
        plan.campaign_id = camp.id
    audit(s, username, "Aprobar propuesta de campaña", f"Propuesta #{plan.id} → campaña #{plan.campaign_id}")
    s.flush()
    return s.get(Campaign, plan.campaign_id)


def plans_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    rows = s.scalars(_mode_filter(select(CampaignPlan), CampaignPlan, mode).order_by(CampaignPlan.created_at.desc())).all()
    return pd.DataFrame([{"ID": p.id, "Nombre": p.name, "Plataforma": p.platform, "Producto": p.product,
                          "Público": p.audience, "Ubicación": p.location, "Estado": p.status,
                          "Generado por": p.generated_by, "Variantes": len(p.variants), "Creada": p.created_at}
                         for p in rows],
                        columns=["ID", "Nombre", "Plataforma", "Producto", "Público", "Ubicación", "Estado",
                                 "Generado por", "Variantes", "Creada"])


def get_plan(s: Session, plan_id: int) -> Optional[CampaignPlan]:
    return s.get(CampaignPlan, plan_id)


def delete_plan(s: Session, plan_id: int) -> None:
    plan = s.get(CampaignPlan, plan_id)
    if plan is not None:
        s.delete(plan)
        s.flush()


def variants_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    stmt = select(AdVariant, CampaignPlan).join(CampaignPlan)
    stmt = _mode_filter(stmt, CampaignPlan, mode)
    rows = s.execute(stmt).all()
    return pd.DataFrame([{"code": v.code, "campaign_id": p.campaign_id, "plan": p.name, "angle": v.angle,
                          "headline": v.headline, "status": v.status} for v, p in rows],
                        columns=["code", "campaign_id", "plan", "angle", "headline", "status"])


# ---------------------------------------------------------------------------
# Recordatorios
# ---------------------------------------------------------------------------
def pending_reminder_exists(s: Session, lead_id: int, rule: str) -> bool:
    return s.scalar(select(Reminder.id).where(Reminder.lead_id == lead_id, Reminder.rule == rule,
                                              Reminder.status == "Pendiente")) is not None


def add_reminder(s: Session, lead_id: int, due: date, rule: str, message: str, template: Optional[str] = None,
                 created_by: Optional[str] = None) -> Reminder:
    r = Reminder(lead_id=lead_id, due_date=due, rule=rule, message=message, template=template, created_by=created_by)
    s.add(r)
    s.flush()
    return r


def set_reminder_status(s: Session, reminder_id: int, status: str, author: Optional[str] = None) -> None:
    r = s.get(Reminder, reminder_id)
    if r is None:
        raise ValueError("Recordatorio no encontrado.")
    r.status = status
    r.done_at = now_mx() if status != "Pendiente" else None
    s.add(Note(lead_id=r.lead_id, kind="Sistema", author=author, text=f"Recordatorio «{r.rule}» marcado como {status}."))
    s.flush()


def reminders_df(s: Session, mode: str = "reales", status: Optional[str] = "Pendiente") -> pd.DataFrame:
    stmt = select(Reminder, Lead).join(Lead)
    stmt = _mode_filter(stmt, Lead, mode)
    if status:
        stmt = stmt.where(Reminder.status == status)
    rows = s.execute(stmt.order_by(Reminder.due_date, Reminder.id)).all()
    return pd.DataFrame([{"id": r.id, "lead_id": l.id, "Vence": r.due_date, "Regla": r.rule, "Lead": l.name,
                          "Teléfono": l.phone, "Producto": l.product, "Etapa": l.stage, "Score": l.score,
                          "Plantilla": r.template, "Mensaje": r.message, "Estado": r.status,
                          "Consentimiento": l.consent_contact} for r, l in rows],
                        columns=["id", "lead_id", "Vence", "Regla", "Lead", "Teléfono", "Producto", "Etapa", "Score",
                                 "Plantilla", "Mensaje", "Estado", "Consentimiento"])


# ---------------------------------------------------------------------------
# Oportunidades de palabras clave
# ---------------------------------------------------------------------------
def save_keywords(s: Session, rows: Iterable[dict], is_demo: bool = False) -> int:
    n = 0
    for r in rows:
        existing = s.scalar(select(KeywordOpportunity).where(
            func.lower(KeywordOpportunity.keyword) == r["keyword"].lower(),
            KeywordOpportunity.location == r.get("location"), KeywordOpportunity.is_demo.is_(is_demo)))
        target = existing or KeywordOpportunity(is_demo=is_demo)
        for k in ("keyword", "product", "segment", "location", "intent", "priority", "source",
                  "avg_monthly_searches", "competition", "low_bid", "high_bid"):
            setattr(target, k, r.get(k))
        target.updated_at = now_mx()
        if existing is None:
            s.add(target)
        n += 1
    s.flush()
    return n


def keywords_df(s: Session, mode: str = "reales") -> pd.DataFrame:
    rows = s.scalars(_mode_filter(select(KeywordOpportunity), KeywordOpportunity, mode)
                     .order_by(KeywordOpportunity.updated_at.desc())).all()
    cols = ["id", "keyword", "product", "segment", "location", "intent", "priority", "source",
            "avg_monthly_searches", "competition", "low_bid", "high_bid", "updated_at"]
    return pd.DataFrame([{c: getattr(r, c) for c in cols} for r in rows], columns=cols)


def delete_keyword(s: Session, kw_id: int) -> None:
    row = s.get(KeywordOpportunity, kw_id)
    if row is not None:
        s.delete(row)
        s.flush()


# ---------------------------------------------------------------------------
# Datos demo
# ---------------------------------------------------------------------------
def count_records(s: Session) -> dict:
    def c(model, demo):
        return s.scalar(select(func.count(model.id)).where(model.is_demo.is_(demo))) or 0
    return {"leads_reales": c(Lead, False), "leads_demo": c(Lead, True),
            "campanas_reales": c(Campaign, False), "campanas_demo": c(Campaign, True)}


def delete_demo_data(s: Session) -> int:
    demo_ids = list(s.scalars(select(Lead.id).where(Lead.is_demo.is_(True))))
    if demo_ids:
        from database.models import AgentMessage, Objection, Quotation
        for model in (Diagnostic, Note, Consent, Reminder, Quotation, Objection, AgentMessage):
            s.execute(delete(model).where(model.lead_id.in_(demo_ids)))
        s.execute(delete(Lead).where(Lead.id.in_(demo_ids)))
    plan_ids = list(s.scalars(select(CampaignPlan.id).where(CampaignPlan.is_demo.is_(True))))
    if plan_ids:
        s.execute(delete(AdVariant).where(AdVariant.plan_id.in_(plan_ids)))
        s.execute(delete(CampaignPlan).where(CampaignPlan.id.in_(plan_ids)))
    s.execute(delete(Campaign).where(Campaign.is_demo.is_(True)))
    s.execute(delete(KeywordOpportunity).where(KeywordOpportunity.is_demo.is_(True)))
    s.flush()
    return len(demo_ids)
