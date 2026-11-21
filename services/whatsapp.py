"""Plantillas de WhatsApp y enlaces wa.me.

La app solo *prepara* el mensaje y abre WhatsApp; el envío lo realiza el asesor
manualmente. Nunca se afirma que el mensaje fue enviado automáticamente.
"""
from __future__ import annotations

from urllib.parse import quote

from utils.validation import normalize_phone

TEMPLATES = {
    "Primer contacto": (
        "Hola {nombre}, soy {asesor} de {empresa}. Recibimos tu solicitud de información sobre "
        "{producto}. ¿Te parece si platicamos unos minutos para conocer lo que necesitas? "
        "Puedes responder este mensaje con el horario que te acomode."
    ),
    "Seguimiento": (
        "Hola {nombre}, te escribe {asesor} de {empresa}. Quería dar seguimiento a tu interés en "
        "{producto}. ¿Tienes alguna duda que pueda resolverte?"
    ),
    "Seguimiento de cotización": (
        "Hola {nombre}, soy {asesor} de {empresa}. ¿Pudiste revisar la cotización de {producto} que te "
        "compartí? Con gusto resuelvo tus dudas sobre coberturas, condiciones y alternativas."
    ),
    "Confirmación de cita": (
        "Hola {nombre}, te escribe {asesor} de {empresa} para confirmar nuestra cita el {fecha} a las "
        "{hora} para revisar tu {producto}. Por favor confírmame si sigue en pie."
    ),
    "Recuperación de leads inactivos": (
        "Hola {nombre}, te escribe {asesor} de {empresa}. Hace un tiempo nos pediste información sobre "
        "{producto}. ¿Sigue siendo de tu interés? Si prefieres no recibir más mensajes, respóndeme «BAJA» "
        "y no volveré a contactarte."
    ),
}

# Preparación para WhatsApp Business Platform (Cloud API): nombre sugerido de
# plantilla aprobada por Meta para cada plantilla interna.
CLOUD_TEMPLATE_NAMES = {
    "Primer contacto": "primer_contacto",
    "Seguimiento": "seguimiento_general",
    "Seguimiento de cotización": "seguimiento_cotizacion",
    "Confirmación de cita": "confirmacion_cita",
    "Recuperación de leads inactivos": "recuperacion_lead",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_message(template: str, **ctx) -> str:
    base = TEMPLATES.get(template, template)
    first_name = (ctx.get("nombre") or "").split(" ")[0]
    ctx = {**ctx, "nombre": first_name or "¿cómo estás?"}
    return base.format_map(_SafeDict({k: (v if v not in (None, "") else "—") for k, v in ctx.items()}))


def wa_number(phone: str) -> str | None:
    digits = normalize_phone(phone)
    return f"52{digits}" if digits else None


def wa_link(phone: str, message: str) -> str | None:
    number = wa_number(phone)
    if not number:
        return None
    return f"https://wa.me/{number}?text={quote(message)}"
