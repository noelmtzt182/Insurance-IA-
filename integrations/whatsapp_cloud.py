"""Preparación para WhatsApp Business Platform (Cloud API) — integración futura.

Este adaptador NO se usa para envíos automáticos. Queda listo para cuando el
negocio tenga: número verificado, plantillas aprobadas por Meta y
consentimiento explícito de cada prospecto. En el MVP los mensajes se abren
con enlaces wa.me y los envía el asesor manualmente.

    [whatsapp]
    access_token = "..."
    phone_number_id = "..."
    graph_version = "v21.0"
    enabled = false          # debe activarse explícitamente
"""
from __future__ import annotations

import json
import urllib.request

from services.whatsapp import wa_number
from utils.config import get_secret


def _cfg() -> dict:
    return {"access_token": get_secret("access_token", section="whatsapp"),
            "phone_number_id": get_secret("phone_number_id", section="whatsapp"),
            "graph_version": get_secret("graph_version", section="whatsapp") or "v21.0",
            "enabled": str(get_secret("enabled", section="whatsapp") or "false").lower() == "true"}


def is_configured() -> bool:
    c = _cfg()
    return bool(c["access_token"] and c["phone_number_id"])


def status() -> str:
    c = _cfg()
    if not is_configured():
        return "No configurado (se usan enlaces wa.me con envío manual)"
    return "Configurado y habilitado" if c["enabled"] else "Configurado pero deshabilitado"


def send_template(phone: str, template_name: str, language: str = "es_MX", body_params: list[str] | None = None,
                  has_consent: bool = False) -> dict:
    """Envía una plantilla aprobada. Exige consentimiento y habilitación explícita."""
    c = _cfg()
    if not (is_configured() and c["enabled"]):
        raise RuntimeError("WhatsApp Cloud API no está habilitada.")
    if not has_consent:
        raise PermissionError("El prospecto no tiene consentimiento de contacto registrado.")
    number = wa_number(phone)
    if not number:
        raise ValueError("Teléfono inválido.")
    payload = {"messaging_product": "whatsapp", "to": number, "type": "template",
               "template": {"name": template_name, "language": {"code": language}}}
    if body_params:
        payload["template"]["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p}
                                                                             for p in body_params]}]
    req = urllib.request.Request(
        f"https://graph.facebook.com/{c['graph_version']}/{c['phone_number_id']}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {c['access_token']}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))
