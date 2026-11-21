"""Adaptador opcional de Google Ads API (Keyword Planner y Lead Form webhooks).

Requiere credenciales autorizadas en st.secrets:

    [google_ads]
    developer_token = "..."
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."
    login_customer_id = "1234567890"   # cuenta administradora (MCC), sin guiones
    customer_id = "1234567890"         # cuenta donde se consulta Keyword Planner
    lead_form_key = "..."              # clave configurada en el webhook del formulario de clientes potenciales

y el paquete ``google-ads`` instalado. Sin credenciales, la app opera en modo
heurístico y NO muestra volúmenes, CPC ni competencia.
"""
from __future__ import annotations

import hmac
from typing import Optional

from utils.config import get_secret

GEO_MEXICO = "geoTargetConstants/2484"
LANG_SPANISH = "languageConstants/1003"
REQUIRED = ["developer_token", "client_id", "client_secret", "refresh_token", "customer_id"]


def _cfg() -> dict:
    return {k: get_secret(k, section="google_ads") for k in REQUIRED + ["login_customer_id", "lead_form_key"]}


def is_configured() -> bool:
    cfg = _cfg()
    if not all(cfg.get(k) for k in REQUIRED):
        return False
    try:
        import google.ads.googleads.client  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> str:
    cfg = _cfg()
    if not all(cfg.get(k) for k in REQUIRED):
        return "No configurado (faltan credenciales en st.secrets[google_ads])"
    try:
        import google.ads.googleads.client  # noqa: F401
    except ImportError:
        return "Credenciales presentes, falta instalar el paquete google-ads"
    return "Configurado"


def keyword_ideas(seed_keywords: list[str], geo_constant: str = GEO_MEXICO, limit: int = 50) -> list[dict]:
    """Consulta KeywordPlanIdeaService. Devuelve métricas reales reportadas por Google."""
    from google.ads.googleads.client import GoogleAdsClient

    cfg = _cfg()
    config = {
        "developer_token": cfg["developer_token"], "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"], "refresh_token": cfg["refresh_token"], "use_proto_plus": True,
    }
    if cfg.get("login_customer_id"):
        config["login_customer_id"] = str(cfg["login_customer_id"]).replace("-", "")
    client = GoogleAdsClient.load_from_dict(config)
    service = client.get_service("KeywordPlanIdeaService")
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = str(cfg["customer_id"]).replace("-", "")
    request.language = LANG_SPANISH
    request.geo_target_constants.append(geo_constant)
    request.include_adult_keywords = False
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seed_keywords[:20])
    results = []
    for idea in service.generate_keyword_ideas(request=request):
        m = idea.keyword_idea_metrics
        results.append({
            "keyword": idea.text,
            "avg_monthly_searches": int(m.avg_monthly_searches) if m.avg_monthly_searches else None,
            "competition": m.competition.name if m.competition else None,
            "low_bid": m.low_top_of_page_bid_micros / 1_000_000 if m.low_top_of_page_bid_micros else None,
            "high_bid": m.high_top_of_page_bid_micros / 1_000_000 if m.high_top_of_page_bid_micros else None,
        })
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------------------
# Google Ads Lead Form (webhook): Google envía un JSON con "google_key" y
# "user_column_data" [{column_id, string_value}].
# ---------------------------------------------------------------------------
GOOGLE_COLUMNS = {"FULL_NAME": "name", "PHONE_NUMBER": "phone", "EMAIL": "email", "CITY": "city"}


def parse_lead_form_webhook(payload: dict, expected_key: Optional[str] = None) -> dict:
    expected_key = expected_key or _cfg().get("lead_form_key")
    if not expected_key or not hmac.compare_digest(str(payload.get("google_key", "")), str(expected_key)):
        raise PermissionError("google_key inválida")
    out = {"external_id": payload.get("lead_id"), "source": "Google Ads",
           "utm_source": "google", "utm_medium": "lead_form",
           "utm_campaign": str(payload.get("campaign_id") or ""), "ad_id": str(payload.get("creative_id") or "") or None,
           "click_id": payload.get("gcl_id")}
    for col in payload.get("user_column_data", []):
        field = GOOGLE_COLUMNS.get(col.get("column_id"))
        if field:
            out[field] = col.get("string_value")
    return out
