"""Adaptador opcional de Meta Lead Ads (Graph API).

Configuración en st.secrets:

    [meta]
    access_token = "..."        # token de página/sistema con permiso leads_retrieval
    graph_version = "v21.0"
    form_ids = ["1234567890"]   # formularios instantáneos autorizados

Solo descarga leads de formularios propios, que ya incluyen el aviso de
privacidad configurado en Meta. No realiza extracción de perfiles ni de redes.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from utils.config import get_secret

META_FIELDS = {"full_name": "name", "first_name": "name", "phone_number": "phone", "email": "email", "city": "city"}


def _cfg() -> dict:
    return {"access_token": get_secret("access_token", section="meta"),
            "graph_version": get_secret("graph_version", section="meta") or "v21.0",
            "form_ids": get_secret("form_ids", section="meta") or []}


def is_configured() -> bool:
    c = _cfg()
    return bool(c["access_token"] and c["form_ids"])


def status() -> str:
    return "Configurado" if is_configured() else "No configurado (faltan access_token o form_ids en st.secrets[meta])"


def map_lead(item: dict, form_id: str) -> dict:
    out = {"external_id": item.get("id"), "source": "Facebook Ads", "utm_source": "facebook",
           "utm_medium": "lead_ads", "ad_id": item.get("ad_id"), "utm_campaign": item.get("campaign_name") or None,
           "_form_id": form_id}
    for f in item.get("field_data", []):
        key = META_FIELDS.get(f.get("name"))
        values = f.get("values") or []
        if key and values:
            out[key] = values[0]
    return out


def fetch_leads(form_id: str, since_unix: Optional[int] = None, limit: int = 100) -> list[dict]:
    c = _cfg()
    params = {"access_token": c["access_token"], "limit": limit,
              "fields": "id,created_time,ad_id,campaign_name,field_data"}
    if since_unix:
        params["filtering"] = json.dumps([{"field": "time_created", "operator": "GREATER_THAN", "value": since_unix}])
    url = f"https://graph.facebook.com/{c['graph_version']}/{urllib.parse.quote(str(form_id))}/leads?" + \
        urllib.parse.urlencode(params)
    leads = []
    while url and len(leads) < 1000:
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310 (URL fija de Graph API)
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Meta Graph API respondió {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("No fue posible conectar con Meta Graph API.") from exc
        leads.extend(map_lead(item, form_id) for item in data.get("data", []))
        url = data.get("paging", {}).get("next")
    return leads
