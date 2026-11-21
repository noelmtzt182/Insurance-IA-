"""Servicio receptor seguro de leads externos (opcional, se ejecuta aparte).

Streamlit no recibe peticiones POST, por eso este pequeño servidor (solo
biblioteca estándar) recibe leads de:

  * POST /webhooks/form          Formularios externos / landing pages propias.
        Encabezado X-Signature: hex(HMAC-SHA256(cuerpo, WEBHOOK_SECRET))
  * POST /webhooks/google-ads    Webhook de Google Ads Lead Forms (valida google_key).

Ejecución (detrás de HTTPS, p. ej. un proxy o un servicio administrado):
    WEBHOOK_SECRET=... DATABASE_URL=postgresql+psycopg2://... python -m integrations.webhook_server

Comparte la misma base de datos que la app, por lo que los leads aparecen en
el CRM, se deduplican y se califican igual que el resto.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 64 * 1024


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def handle_form_payload(payload: dict) -> tuple[int, dict]:
    """Procesa un lead externo ya autenticado. Exige consentimiento explícito."""
    from database.session import session_scope
    from services.capture import ingest, map_product, map_source

    raw = {
        "name": payload.get("name"), "phone": payload.get("phone"), "email": payload.get("email"),
        "email_required": False, "city": payload.get("city") or "Sin dato",
        "product": map_product(payload.get("product")) or map_product(os.environ.get("DEFAULT_PRODUCT")), "source": map_source(payload.get("source")) or "Sitio web",
        "consent_contact": bool(payload.get("consent_contact")), "consent_privacy": bool(payload.get("consent_privacy")),
        "quote_requested": bool(payload.get("quote_requested")), "contact_requested": bool(payload.get("contact_requested")),
    }
    for k in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ad_id", "external_id"):
        if payload.get(k):
            raw[k] = str(payload[k])
    with session_scope() as s:
        lead_id, errors, dup = ingest(s, raw, channel="webhook_externo", author="webhook")
    if errors:
        return 422, {"ok": False, "errors": errors}
    return 201, {"ok": True, "lead_uid_created": True, "possible_duplicate": dup}


class Handler(BaseHTTPRequestHandler):
    server_version = "InsuranceLeadsWebhook/1.0"

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._send(413, {"ok": False, "error": "tamaño inválido"})
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._send(400, {"ok": False, "error": "JSON inválido"})

        if self.path == "/webhooks/form":
            if not verify_signature(body, self.headers.get("X-Signature", ""), os.environ.get("WEBHOOK_SECRET", "")):
                return self._send(401, {"ok": False, "error": "firma inválida"})
            code, resp = handle_form_payload(payload)
            return self._send(code, resp)

        if self.path == "/webhooks/google-ads":
            from integrations.google_ads import parse_lead_form_webhook
            try:
                data = parse_lead_form_webhook(payload, os.environ.get("GOOGLE_LEAD_FORM_KEY"))
            except PermissionError:
                return self._send(401, {"ok": False, "error": "clave inválida"})
            # Los formularios de Google Ads incluyen el aviso de privacidad del anunciante (obligatorio)
            data.update({"consent_contact": True, "consent_privacy": True, "contact_requested": True})
            code, resp = handle_form_payload(data)
            return self._send(200 if code == 201 else code, resp)

        return self._send(404, {"ok": False, "error": "ruta no encontrada"})

    def log_message(self, fmt, *args):  # sin datos personales en logs
        print(f"[webhook] {self.address_string()} {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def main() -> None:  # pragma: no cover
    if not os.environ.get("WEBHOOK_SECRET"):
        raise SystemExit("Define WEBHOOK_SECRET antes de iniciar el receptor.")
    port = int(os.environ.get("PORT", "8080"))
    print(f"Receptor de leads escuchando en :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
