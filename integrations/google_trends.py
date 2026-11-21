"""Adaptador para Google Trends mediante una fuente AUTORIZADA.

Google Trends no ofrece una API pública general; el acceso oficial (Google
Trends API) es limitado. No se usa scraping. Mientras no exista una fuente
autorizada configurada, el adaptador reporta "no disponible" y la app no
muestra datos de tendencia.

    [google_trends]
    endpoint = "https://..."   # servicio autorizado que devuelve JSON
    api_key = "..."
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from utils.config import get_secret


def is_configured() -> bool:
    return bool(get_secret("endpoint", section="google_trends") and get_secret("api_key", section="google_trends"))


def status() -> str:
    return "Configurado" if is_configured() else "No disponible (sin fuente autorizada configurada)"


def interest_over_time(keyword: str, geo: str = "MX") -> list[dict]:
    """Consulta el endpoint autorizado. Formato esperado: [{"date": "YYYY-MM-DD", "value": int}]."""
    if not is_configured():
        raise RuntimeError("Google Trends no está configurado con una fuente autorizada.")
    endpoint = get_secret("endpoint", section="google_trends")
    url = f"{endpoint}?{urllib.parse.urlencode({'q': keyword, 'geo': geo})}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {get_secret('api_key', section='google_trends')}"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))
