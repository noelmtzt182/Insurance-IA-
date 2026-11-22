"""Motor B — AI Campaign Generator.

Dos motores intercambiables con la misma salida:
  * Plantillas (siempre disponible, determinístico).
  * IA (Claude, opcional) — ver integrations/llm.py.

La app solo GENERA el contenido; nunca publica campañas.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from services.demand import generate_opportunities
from utils.config import PRODUCT_GMM, PRODUCT_VIDA

# Límites de caracteres por plataforma (titular, descripción/texto principal)
PLATFORM_LIMITS = {
    "Google Ads": {"headline": 30, "description": 90},
    "Facebook": {"headline": 40, "description": 125},
    "Instagram": {"headline": 40, "description": 125},
    "LinkedIn": {"headline": 70, "description": 150},
}

# Frases que no deben usarse en anuncios de seguros (promesas, precios, garantías)
RISKY_PHRASES = [
    "garantizado", "garantizamos", "garantía de aprobación", "100%", "sin exámenes", "sin requisitos",
    "aprobación inmediata", "el más barato", "más barato", "desde $", "precio fijo", "cubre todo",
    "sin letras chiquitas", "sin deducible", "cobertura total", "aceptamos a todos",
]

PRODUCT_COPY = {
    PRODUCT_VIDA: {
        "short": "seguro de vida",
        "title": "Seguro de vida",
        "quote": "Cotiza tu seguro de vida",
        "benefit": "protege a quienes dependen de ti",
        "props": ["Asesoría personalizada sin costo para definir la suma asegurada adecuada",
                  "Comparación de alternativas de distintas aseguradoras",
                  "Acompañamiento en la contratación y en un eventual reclamo"],
    },
    PRODUCT_GMM: {
        "short": "seguro de gastos médicos mayores",
        "title": "Gastos médicos mayores",
        "quote": "Cotiza gastos médicos mayores",
        "benefit": "cuida tu salud y tu patrimonio ante un evento médico",
        "props": ["Te explicamos deducible, coaseguro y red hospitalaria con claridad",
                  "Comparamos opciones según tu ciudad y hospitales de preferencia",
                  "Acompañamiento en la contratación y en trámites de reembolso"],
    },
}

AUDIENCE_COPY = {
    "Profesionistas independientes": ("profesionistas independientes", "sin prestaciones de una empresa"),
    "Padres de familia": ("padres de familia", "pensando en tus hijos"),
    "Empresarios": ("empresarios", "para ti y tu negocio"),
    "Emprendedores": ("emprendedores", "mientras haces crecer tu proyecto"),
    "Directivos": ("directivos", "complementa tus prestaciones"),
    "Pequeñas y medianas empresas": ("pymes", "para tu equipo de trabajo"),
}

# Ganchos para el objetivo «Agendar citas»: la oferta es la asesoría, no el seguro
# (ángulo, gancho corto ≤ 30 caracteres, gancho largo, descripción con {short}, {aud_name}, {location})
APPOINTMENT_ANGLES = [
    ("Asesoría gratuita", "Agenda tu asesoría gratis", "Agenda tu asesoría gratuita",
     "Elige día y horario. Un asesor te orienta sobre tu {short}, sin compromiso."),
    ("Revisión de tu protección", "Revisión gratuita de 20 min", "Revisa gratis tu protección familiar",
     "En 20 minutos revisamos qué necesitas proteger y tus opciones. Agenda hoy."),
    ("Experto a tu lado", "Habla con un asesor", "Resuelve tus dudas con un asesor",
     "Para {aud_name} en {location}: agenda una llamada y resuelve tus dudas."),
]

# (ángulo, gancho corto ≤ 30 caracteres, gancho largo para redes sociales)
ANGLES = [
    ("Protección familiar", "Protege lo que más importa", "Protege lo que más importa"),
    ("Asesoría y diagnóstico gratuito", "Diagnóstico gratuito", "Diagnóstico gratuito en 3 minutos"),
    ("Claridad y comparación", "Compara con un experto", "Compara opciones con un asesor experto"),
    ("Planeación oportuna", "Planea hoy tu tranquilidad", "Planea hoy la tranquilidad de mañana"),
]


def compliance_issues(text: str) -> list[str]:
    t = (text or "").lower()
    return [p for p in RISKY_PHRASES if p in t]


def length_issues(platform: str, headline: str, description: str) -> list[str]:
    lim = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["Facebook"])
    issues = []
    if len(headline) > lim["headline"]:
        issues.append(f"Titular de {len(headline)} caracteres (máx. {lim['headline']}).")
    if len(description) > lim["description"]:
        issues.append(f"Descripción de {len(description)} caracteres (recomendado ≤ {lim['description']}).")
    return issues


def _fit(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:")


PLATFORM_UTM = {"Google Ads": ("google", "cpc"), "Facebook": ("facebook", "paid_social"),
                "Instagram": ("instagram", "paid_social"), "LinkedIn": ("linkedin", "paid_social"),
                "TikTok": ("tiktok", "paid_social")}


def build_utm_url(base_url: str, platform: str, campaign_slug: str, content: str = "", term: Optional[str] = None) -> str:
    """URL de la landing pública (/registro) con parámetros UTM para atribución."""
    from urllib.parse import urlencode
    src, medium = PLATFORM_UTM.get(platform, ("otro", "referral"))
    params = {"utm_source": src, "utm_medium": medium, "utm_campaign": campaign_slug}
    if content:
        params["utm_content"] = content
    if term:
        params["utm_term"] = term
    base = (base_url or "http://localhost:8501").rstrip("/")
    return f"{base}/registro?{urlencode(params)}"


def generate_with_templates(inputs: dict) -> tuple[dict, list[dict]]:
    product = inputs["product"]
    audience = inputs["audience"]
    location = inputs["location"]
    platform = inputs["platform"]
    objective = inputs["objective"]
    budget = inputs.get("budget")
    pc = PRODUCT_COPY[product]
    aud_name, aud_hook = AUDIENCE_COPY.get(audience, ("personas", "para ti"))
    lim = PLATFORM_LIMITS[platform]
    month = date.today().strftime("%Y-%m")

    name = f"{'Vida' if product == PRODUCT_VIDA else 'GMM'} · {aud_name.capitalize()} · {location} · {platform} · {month}"

    if platform == "Google Ads":
        segmentation = [
            f"Red de Búsqueda, ubicación: {location} (personas en o interesadas regularmente en la ubicación).",
            "Idioma: español. Horario: priorizar horario laboral y primeras horas de la noche.",
            "Grupos de anuncios por intención: (1) cotizar/contratar, (2) segmento, (3) local.",
            "Estrategia de puja inicial: maximizar conversiones con conversión = envío de formulario.",
        ]
    elif platform == "LinkedIn":
        segmentation = [
            f"Ubicación: {location}.",
            f"Públicos: {aud_name}; cargos y funciones afines; tamaño de empresa según segmento.",
            "Formato sugerido: anuncio de imagen única con formulario o tráfico a landing.",
        ]
    else:
        segmentation = [
            f"Ubicación: {location}. Edad: 25 a 60 años (ajustar tras primeras semanas).",
            f"Intereses relacionados con {aud_name}, finanzas personales, familia o negocio.",
            "Optimización: clientes potenciales; excluir personas que ya enviaron el formulario.",
            "Evita segmentar por condiciones de salud u otros datos sensibles.",
        ]

    kw_df = generate_opportunities(
        "Seguros de vida" if product == PRODUCT_VIDA else "Gastos médicos mayores",
        audience, location if location != "México" else None, None, objective, budget, max_items=15)
    keywords = kw_df["keyword"].tolist() if not kw_df.empty else []
    negatives = ["gratis", "empleo", "vacantes", "imss trámite", "pdf", "definición", "tesis"]

    headlines = [
        _fit(pc["title"], lim["headline"]),
        _fit(pc["quote"], lim["headline"]),
        _fit(f"{pc['title']} {aud_hook}", lim["headline"]),
        _fit(f"Asesoría en {location}", lim["headline"]),
        _fit("Diagnóstico gratuito", lim["headline"]),
        _fit("Habla con un asesor hoy", lim["headline"]),
    ]
    descriptions = [
        _fit(f"Un asesor certificado te ayuda a elegir un {pc['short']} que {pc['benefit']}.", lim["description"]),
        _fit("Responde un diagnóstico breve y recibe orientación personalizada sin compromiso.", lim["description"]),
        _fit("Comparamos alternativas y te explicamos coberturas, condiciones y exclusiones.", lim["description"]),
    ]
    ctas = {"Solicitudes de cotización": ["Solicitar cotización", "Cotizar ahora"],
            "Agendar citas": ["Agendar asesoría", "Reservar llamada"],
            "Generar leads": ["Hacer diagnóstico", "Más información"],
            "Reconocimiento local": ["Conocer más", "Hacer diagnóstico"]}.get(objective, ["Más información"])

    variants = []
    if objective == "Agendar citas":
        for i, (angle, short_hook, long_hook, desc_tpl) in enumerate(APPOINTMENT_ANGLES):
            head = short_hook if lim["headline"] <= 30 else long_hook
            desc = desc_tpl.format(short=pc["short"], aud_name=aud_name, location=location)
            variants.append({"angle": angle, "headline": _fit(head, lim["headline"]),
                             "description": _fit(desc, lim["description"]), "cta": ctas[i % len(ctas)]})
    for i, (angle, short_hook, long_hook) in enumerate(ANGLES[:4] if objective != "Agendar citas" else []):
        hook = short_hook if lim["headline"] <= 30 else long_hook
        if angle == "Protección familiar":
            head = hook
            desc = f"{pc['benefit'].capitalize()} {aud_hook}. Asesoría personalizada en {location}."
        elif angle.startswith("Asesoría"):
            head = hook
            desc = f"Descubre qué {pc['short']} se adapta a tus necesidades. Sin compromiso."
        elif angle.startswith("Claridad"):
            head = hook
            desc = "Te explicamos coberturas y condiciones de varias aseguradoras con claridad."
        else:
            head = hook
            desc = f"Para {aud_name}: revisa hoy tus opciones de {pc['short']} con un asesor."
        variants.append({"angle": angle, "headline": _fit(head, lim["headline"]),
                         "description": _fit(desc, lim["description"]), "cta": ctas[i % len(ctas)]})

    content = {
        "campaign_name": name,
        "segmentation": segmentation,
        "keywords": keywords,
        "negative_keywords": negatives,
        "headlines": headlines,
        "descriptions": descriptions,
        "value_props": pc["props"],
        "ctas": ctas,
        "landing_structure": [
            "Encabezado: «Protege lo que más importa» + subtítulo específico del segmento.",
            "Botón principal «Agenda tu asesoría gratuita» con selección de día y horario.",
            "Beneficios (3 bloques) sin precios ni promesas de cobertura.",
            "Diagnóstico gratuito (cuestionario de 7 preguntas, sin datos médicos).",
            "Formulario breve: nombre, teléfono, correo, ciudad, producto, presupuesto, fecha estimada.",
            "Consentimiento de contacto + aviso de privacidad visible.",
            "Preguntas frecuentes y botón de WhatsApp.",
        ],
        "ab_tests": [
            "Variante A vs B: ángulo emocional (protección familiar) vs racional (asesoría y diagnóstico).",
            "CTA: «Solicitar cotización» vs «Hacer diagnóstico» en la landing.",
            "Formulario corto vs formulario + diagnóstico: comparar CPL y tasa de leads calificados.",
        ],
        "kpis": ["CTR", "CPC", "CPL", "% de leads calificados (score ≥ 50)", "Tasa de cita",
                 "Tasa de cotización", "CAC por póliza", "ROAS de comisiones"],
        "compliance_notes": [
            "No incluir precios, primas ni promesas de aprobación o cobertura.",
            "Mencionar que la contratación está sujeta a las condiciones de cada aseguradora.",
            "Respetar políticas de anuncios de servicios financieros de cada plataforma.",
        ],
        "status_note": "Contenido generado. No ha sido publicado en ninguna plataforma.",
    }
    return content, variants


# Esquema para generación con IA (salida estructurada)
CAMPAIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "campaign_name": {"type": "string"},
        "segmentation": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "negative_keywords": {"type": "array", "items": {"type": "string"}},
        "headlines": {"type": "array", "items": {"type": "string"}},
        "descriptions": {"type": "array", "items": {"type": "string"}},
        "value_props": {"type": "array", "items": {"type": "string"}},
        "ctas": {"type": "array", "items": {"type": "string"}},
        "landing_structure": {"type": "array", "items": {"type": "string"}},
        "ab_tests": {"type": "array", "items": {"type": "string"}},
        "kpis": {"type": "array", "items": {"type": "string"}},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"angle": {"type": "string"}, "headline": {"type": "string"},
                               "description": {"type": "string"}, "cta": {"type": "string"}},
                "required": ["angle", "headline", "description", "cta"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["campaign_name", "segmentation", "keywords", "negative_keywords", "headlines", "descriptions",
                 "value_props", "ctas", "landing_structure", "ab_tests", "kpis", "variants"],
    "additionalProperties": False,
}


def normalize_ai_output(data: dict, inputs: dict) -> tuple[dict, list[dict]]:
    """Valida la salida de IA; si falta algo, completa con plantillas."""
    tpl_content, tpl_variants = generate_with_templates(inputs)
    variants = [v for v in data.get("variants", []) if v.get("headline") and v.get("description")]
    if len(variants) < 3:
        variants = (variants + tpl_variants)[:max(3, len(variants))]
    content = {k: data.get(k) or tpl_content[k] for k in tpl_content if k not in ("compliance_notes", "status_note")}
    content["compliance_notes"] = tpl_content["compliance_notes"]
    content["status_note"] = tpl_content["status_note"]
    return content, variants


def generate(inputs: dict, use_ai: bool = False) -> tuple[dict, list[dict], str]:
    """Devuelve (contenido, variantes, generado_por)."""
    if use_ai:
        from integrations import llm
        if llm.is_configured():
            data = llm.generate_campaign(inputs, CAMPAIGN_SCHEMA)
            content, variants = normalize_ai_output(data, inputs)
            return content, variants, f"IA ({llm.model_name()})"
    content, variants = generate_with_templates(inputs)
    return content, variants, "Plantillas"
