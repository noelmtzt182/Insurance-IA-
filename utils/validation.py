"""Validación y normalización de formularios."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from utils.config import BUDGET_RANGES, PRODUCTS, SOURCES

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .\-]{3,120}$")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Devuelve 10 dígitos de un teléfono mexicano o None si no es válido.

    Acepta formatos como "55 1234 5678", "+52 55 1234 5678", "5215512345678".
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 13 and digits.startswith("521"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("52"):
        digits = digits[2:]
    if len(digits) != 10:
        return None
    return digits


def clean_text(value: Optional[str], max_len: int = 200) -> Optional[str]:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value[:max_len] or None


def validate_lead(data: dict, require_consent: bool = True, today: Optional[date] = None) -> tuple[dict, list[str]]:
    """Valida los datos de un lead. Devuelve (datos_limpios, errores)."""
    errors: list[str] = []
    out = dict(data)

    name = clean_text(data.get("name"), 120)
    if not name or not NAME_RE.match(name):
        errors.append("Escribe un nombre válido (mínimo 3 letras, sin números).")
    out["name"] = name

    phone = normalize_phone(data.get("phone"))
    if not phone:
        errors.append("El teléfono debe tener 10 dígitos (ej. 55 1234 5678).")
    out["phone"] = phone

    email = clean_text(data.get("email"), 200)
    if email:
        email = email.lower()
        if not EMAIL_RE.match(email):
            errors.append("El correo electrónico no tiene un formato válido.")
    elif data.get("email_required", True):
        errors.append("El correo electrónico es obligatorio.")
    out["email"] = email
    out.pop("email_required", None)

    out["city"] = clean_text(data.get("city"), 100)
    if not out["city"]:
        errors.append("Indica tu ciudad.")

    if data.get("product") not in PRODUCTS:
        errors.append("Selecciona un producto de interés.")

    if data.get("budget_range") and data["budget_range"] not in BUDGET_RANGES:
        errors.append("Rango de presupuesto inválido.")

    if data.get("source") and data["source"] not in SOURCES:
        errors.append("Fuente de adquisición inválida.")

    est = data.get("est_purchase_date")
    ref = today or date.today()
    if est and isinstance(est, date) and (est - ref).days > 3 * 365:
        errors.append("La fecha estimada de contratación no puede ser mayor a 3 años.")

    if require_consent:
        if not data.get("consent_contact"):
            errors.append("Debes autorizar que te contactemos para continuar.")
        if not data.get("consent_privacy"):
            errors.append("Debes aceptar el aviso de privacidad para continuar.")

    return out, errors
