"""Constantes de negocio compartidas por todos los módulos."""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

APP_NAME = "Insurance Leads AI"
TZ = ZoneInfo("America/Mexico_City")

# --- Productos -------------------------------------------------------------
PRODUCT_VIDA = "Seguro de vida"
PRODUCT_GMM = "Gastos médicos mayores"
PRODUCTS = [PRODUCT_VIDA, PRODUCT_GMM]

# --- Embudo comercial ------------------------------------------------------
STAGES = [
    "Nuevo",
    "Contactado",
    "Calificado",
    "Cita agendada",
    "Cotización enviada",
    "Negociación",
    "Póliza emitida",
]
STAGE_LOST = "Perdido"
ALL_STAGES = STAGES + [STAGE_LOST]
STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}
IDX_CONTACTED = STAGE_INDEX["Contactado"]
IDX_QUALIFIED = STAGE_INDEX["Calificado"]
IDX_APPOINTMENT = STAGE_INDEX["Cita agendada"]
IDX_QUOTE = STAGE_INDEX["Cotización enviada"]
IDX_POLICY = STAGE_INDEX["Póliza emitida"]
CLOSED_STAGES = {"Póliza emitida", STAGE_LOST}

# --- Fuentes de adquisición ------------------------------------------------
SOURCES = [
    "Facebook Ads",
    "Instagram",
    "Google Ads",
    "TikTok",
    "LinkedIn",
    "Sitio web",
    "Referido",
    "WhatsApp",
    "Evento",
    "Otro",
]
PLATFORMS = ["Google Ads", "Facebook", "Instagram", "LinkedIn", "TikTok", "Email", "Evento", "Otro"]
AD_PLATFORMS = ["Google Ads", "Facebook", "Instagram", "LinkedIn"]
# Mapeo plataforma -> fuente de adquisición (para atribución)
PLATFORM_SOURCE = {"Google Ads": "Google Ads", "Facebook": "Facebook Ads", "Instagram": "Instagram",
                   "LinkedIn": "LinkedIn", "TikTok": "TikTok", "Email": "Otro", "Evento": "Evento", "Otro": "Otro"}
UTM_SOURCE_MAP = {"google": "Google Ads", "facebook": "Facebook Ads", "fb": "Facebook Ads", "meta": "Facebook Ads",
                  "instagram": "Instagram", "ig": "Instagram", "linkedin": "LinkedIn", "tiktok": "TikTok",
                  "whatsapp": "WhatsApp", "referido": "Referido", "web": "Sitio web"}

SEGMENTS = [
    "Profesionistas independientes",
    "Padres de familia",
    "Empresarios",
    "Emprendedores",
    "Directivos",
    "Pequeñas y medianas empresas",
]
SEGMENT_OTHER = "Otro / prefiero no decir"

OBJECTIVES = ["Generar leads", "Solicitudes de cotización", "Agendar citas", "Reconocimiento local"]
CAMPAIGN_STATUS = ["Borrador", "Aprobada (pendiente de publicar)", "Activa (registrada por el usuario)", "Pausada", "Finalizada"]
DATA_ORIGINS = ["Observado", "Importado", "Estimado", "Demo"]

# Estados y ciudades principales (catálogo para segmentación)
STATES_CITIES = {
    "Ciudad de México": ["Ciudad de México"],
    "Jalisco": ["Guadalajara", "Zapopan", "Puerto Vallarta"],
    "Nuevo León": ["Monterrey", "San Pedro Garza García", "Apodaca"],
    "Estado de México": ["Toluca", "Naucalpan", "Tlalnepantla", "Metepec"],
    "Puebla": ["Puebla"],
    "Querétaro": ["Querétaro"],
    "Yucatán": ["Mérida"],
    "Guanajuato": ["León", "Irapuato", "Celaya"],
    "Baja California": ["Tijuana", "Mexicali", "Ensenada"],
    "Quintana Roo": ["Cancún", "Playa del Carmen"],
    "San Luis Potosí": ["San Luis Potosí"],
    "Aguascalientes": ["Aguascalientes"],
    "Chihuahua": ["Chihuahua", "Ciudad Juárez"],
    "Sonora": ["Hermosillo"],
    "Michoacán": ["Morelia"],
    "Veracruz": ["Veracruz", "Xalapa"],
    "Sinaloa": ["Culiacán", "Mazatlán"],
    "Coahuila": ["Saltillo", "Torreón"],
    "Oaxaca": ["Oaxaca"],
}
STATES = list(STATES_CITIES)
CITIES = sorted({c for cs in STATES_CITIES.values() for c in cs})

# --- Presupuesto mensual (rangos, sin inventar precios) --------------------
BUDGET_RANGES = [
    "No lo sé aún",
    "Menos de $500",
    "$500 a $1,000",
    "$1,000 a $2,000",
    "$2,000 a $4,000",
    "Más de $4,000",
]

INTENT_LEVELS = ["Sin definir", "Baja", "Media", "Alta"]

NOTE_KINDS = ["Nota", "Llamada", "WhatsApp", "Correo", "Reunión", "Cotización", "Sistema"]
ACTIVITY_KINDS = ["Llamada", "WhatsApp", "Correo", "Reunión", "Nota"]
DUP_POSSIBLE = "Posible duplicado"
DUP_CONFIRMED = "Duplicado confirmado"
DUP_CLEARED = "No es duplicado"

PRIORITY_HIGH = "Alta prioridad"
PRIORITY_MEDIUM = "Media"
PRIORITY_LOW = "Exploratorio"
PRIORITIES = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]

DATA_MODES = {"reales": "Datos reales", "demo": "Datos demo", "todos": "Reales + demo"}

DEFAULT_PRIVACY_NOTICE = """**Aviso de privacidad simplificado**

[Nombre del responsable], con domicilio en [domicilio], es responsable del tratamiento de sus datos personales.

**Datos que recabamos:** nombre, teléfono, correo electrónico, ciudad y preferencias sobre productos de seguros. **No recabamos datos sensibles** (por ejemplo, información de salud) mediante este formulario.

**Finalidades:** (1) contactarle para brindarle información y asesoría sobre seguros de vida y gastos médicos mayores; (2) elaborar cotizaciones a solicitud suya; (3) dar seguimiento comercial.

**Derechos ARCO:** puede ejercer sus derechos de acceso, rectificación, cancelación u oposición, así como revocar su consentimiento, escribiendo a [correo de contacto].

Puede consultar el aviso de privacidad integral en [URL del aviso integral].

*Este texto es una plantilla. Revíselo con su asesor legal y actualícelo en Configuración antes de captar datos reales.*"""


def now_mx() -> datetime:
    """Fecha y hora actual en Ciudad de México, sin tzinfo (para almacenar)."""
    return datetime.now(TZ).replace(tzinfo=None)


def today_mx() -> date:
    return now_mx().date()


def get_secret(key: str, default=None, section: str | None = None):
    """Lee un valor de st.secrets (si existe) o de variables de entorno.

    No falla si Streamlit no está disponible (pruebas automatizadas).
    """
    try:
        import streamlit as st

        container = st.secrets
        if section:
            if section in container and key in container[section]:
                return container[section][key]
        elif key in container:
            return container[key]
    except Exception:
        pass
    env_key = f"{section}_{key}".upper() if section else key.upper()
    return os.environ.get(env_key, default)
