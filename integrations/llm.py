"""Explicaciones en lenguaje natural con Claude (opcional).

Se activa solo si existe ``ANTHROPIC_API_KEY`` en st.secrets o en el entorno.
Al modelo se le envían ÚNICAMENTE métricas agregadas y anonimizadas (sin
nombres, teléfonos ni correos) y se le instruye a no inventar cifras.
"""
from __future__ import annotations

import json
import math
from typing import Optional

from utils.config import get_secret

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """Eres un analista comercial senior de una agencia de seguros de vida y gastos médicos mayores en México.
Recibirás métricas agregadas calculadas por el CRM en formato JSON y una pregunta del asesor.

Reglas estrictas:
- Usa exclusivamente las cifras del JSON. No inventes datos, porcentajes, precios ni nombres.
- Si los datos no alcanzan para responder, dilo claramente y sugiere qué registrar.
- No prometas coberturas ni menciones precios de pólizas.
- Responde en español de México, en 4 a 8 viñetas concretas, terminando con 2 o 3 acciones recomendadas.
- Los valores null significan "no calculable" (por ejemplo, división entre cero)."""


def api_key() -> Optional[str]:
    return get_secret("ANTHROPIC_API_KEY")


def is_configured() -> bool:
    if not api_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def model_name() -> str:
    return get_secret("ANTHROPIC_MODEL") or DEFAULT_MODEL


def _clean(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=api_key())


def _call(system: str, user: str, output_format: Optional[dict] = None) -> str:
    """Llamada única a Claude con manejo de errores; devuelve el texto de la respuesta."""
    import anthropic

    output_config: dict = {"effort": "low"}
    if output_format:
        output_config["format"] = output_format
    try:
        response = _client().beta.messages.create(
            model=model_name(),
            max_tokens=16000,
            system=system,
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("La API key de Anthropic no es válida.") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError("Se alcanzó el límite de uso de la API. Intenta en unos minutos.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Error de la API ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("No fue posible conectar con la API de Anthropic.") from exc
    if response.stop_reason == "refusal":
        raise RuntimeError("El modelo no generó una respuesta para esta solicitud.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("La respuesta del modelo se truncó; intenta de nuevo.")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("La respuesta del modelo llegó vacía.")
    return text


def explain(question: str, facts: dict) -> str:
    """Explica métricas agregadas (sin datos personales) en lenguaje natural."""
    payload = json.dumps(_clean(facts), ensure_ascii=False, default=str)
    if len(payload) > 60_000:
        raise RuntimeError("El resumen de datos es demasiado grande; filtra el periodo o el conjunto de datos.")
    return _call(SYSTEM_PROMPT, f"Pregunta: {question}\n\nMétricas del CRM (JSON):\n{payload}")


CAMPAIGN_SYSTEM = """Eres especialista en performance marketing para agentes de seguros en México (Google Ads, Meta y LinkedIn).
Genera propuestas de campaña en español de México que cumplan:
- Sin precios, primas, porcentajes de descuento ni promesas de aprobación o cobertura.
- Sin frases como "garantizado", "sin requisitos", "el más barato", "cubre todo".
- No segmentes por condiciones de salud ni por datos sensibles.
- Respeta los límites de caracteres indicados para la plataforma.
- Entrega al menos 3 variantes creativas con ángulos distintos.
- Tono profesional, cercano y claro. El objetivo es dirigir tráfico a una landing con diagnóstico gratuito y formulario."""


def generate_campaign(inputs: dict, schema: dict) -> dict:
    from services.campaign_generator import PLATFORM_LIMITS
    lim = PLATFORM_LIMITS.get(inputs["platform"], {"headline": 40, "description": 125})
    brief = (f"Producto: {inputs['product']}\nPúblico objetivo: {inputs['audience']}\n"
             f"Ubicación: {inputs['location']}\nPlataforma: {inputs['platform']}\n"
             f"Presupuesto mensual (MXN): {inputs.get('budget') or 'no definido'}\n"
             f"Objetivo comercial: {inputs['objective']}\n"
             f"Límites: titular ≤ {lim['headline']} caracteres; descripción ≤ {lim['description']} caracteres.")
    text = _call(CAMPAIGN_SYSTEM, brief, {"type": "json_schema", "schema": schema})
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("La respuesta de IA no tuvo un formato válido.") from exc


def market_analysis(facts: dict) -> str:
    system = ("Eres analista de mercado de seguros en México. Recibirás cifras verificadas del CRM y "
              "hipótesis comerciales. Distingue explícitamente entre lo verificado (cifras) y tus "
              "inferencias. No inventes estadísticas externas ni cifras de mercado. Responde en 5 a 8 viñetas "
              "en español de México, con 3 acciones concretas al final.")
    payload = json.dumps(_clean(facts), ensure_ascii=False, default=str)
    return _call(system, f"Datos (JSON):\n{payload}")


AGENT_SYSTEM = """Eres el asistente comercial de un agente de seguros en México (seguro de vida y gastos médicos mayores).
Reglas estrictas:
- Responde SOLO con la información de las FUENTES proporcionadas. Si no alcanzan, di que lo consultarás con el asesor.
- Nunca inventes ni estimes primas, precios, coberturas, exclusiones, periodos de espera ni condiciones.
- No presiones ni generes miedo. Tono cálido, claro y breve (máximo 80 palabras), español de México.
- No pidas información médica."""


def agent_draft(question: str, sources: list[dict]) -> str:
    """Redacta una respuesta natural usando exclusivamente las fuentes recuperadas."""
    if not sources:
        raise RuntimeError("Sin fuentes validadas: no se genera respuesta con IA.")
    ctx = "\n".join(f"- [{s.get('source', 'Fuente')}] {s['answer']}" for s in sources)
    return _call(AGENT_SYSTEM, f"FUENTES:\n{ctx}\n\nMensaje del prospecto: {question}")


def coach_feedback(objection: str, reply: str) -> str:
    system = ("Eres coach de venta consultiva de seguros en México. Evalúa la respuesta del agente a una objeción. "
              "Señala fortalezas, riesgos (presión, promesas, afirmaciones sin sustento, recomendar cancelar pólizas sin "
              "análisis) y propone una versión mejorada breve. No inventes cifras ni coberturas. Máximo 150 palabras.")
    return _call(system, f"Objeción del prospecto: {objection}\nRespuesta del agente: {reply}")
