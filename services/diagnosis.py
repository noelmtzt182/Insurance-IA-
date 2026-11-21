"""Diagnóstico inteligente orientativo.

Reglas:
  * No se solicitan datos médicos sensibles.
  * No se inventan precios ni se prometen coberturas.
  * El resultado es orientativo y siempre remite a un asesor certificado.
"""
from __future__ import annotations

from utils.config import BUDGET_RANGES, PRODUCT_GMM, PRODUCT_VIDA

AGE_RANGES = ["18 a 29", "30 a 39", "40 a 49", "50 a 59", "60 o más"]
DEPENDENTS = ["Ninguno", "1", "2", "3 o más"]
INCOME_RANGES = [
    "Menos de $15,000",
    "$15,000 a $30,000",
    "$30,000 a $60,000",
    "$60,000 a $120,000",
    "Más de $120,000",
    "Prefiero no decir",
]
OBLIGATIONS = ["Crédito hipotecario", "Crédito automotriz", "Tarjetas o créditos personales", "Colegiaturas", "Ninguna"]
LIFE_COVERAGE = ["Ninguna", "Solo la de mi empleo (prestación)", "Póliza individual", "Prestación y póliza individual", "No estoy seguro"]
GMM_COVERAGE = ["Ninguna", "Solo IMSS / ISSSTE", "GMM de mi empleo (prestación)", "Póliza individual o familiar", "No estoy seguro"]
GMM_TYPE = ["Individual", "Familiar"]
INTENT_OPTIONS = [
    "Quiero contratar en los próximos 30 días",
    "En 1 a 3 meses",
    "En más de 3 meses",
    "Solo estoy explorando",
]
INTENT_MAP = {
    INTENT_OPTIONS[0]: "Alta",
    INTENT_OPTIONS[1]: "Media",
    INTENT_OPTIONS[2]: "Baja",
    INTENT_OPTIONS[3]: "Baja",
}

DISCLAIMER = (
    "Este diagnóstico es orientativo y no constituye una cotización, oferta ni garantía de cobertura. "
    "Las condiciones, sumas aseguradas, primas, deducibles y exclusiones dependen de cada aseguradora y "
    "de la evaluación de un agente de seguros autorizado."
)


def _level(points: int) -> str:
    if points >= 5:
        return "Alta"
    if points >= 3:
        return "Media"
    return "Baja"


def diagnose_life(a: dict) -> dict:
    points = 0
    findings, considerations = [], []

    deps = a.get("dependientes", "Ninguno")
    if deps != "Ninguno":
        points += 3 if deps in ("2", "3 o más") else 2
        findings.append(f"Tienes {deps} dependiente(s) económico(s): su estabilidad financiera depende en parte de tus ingresos.")
    else:
        findings.append("No reportas dependientes económicos; la necesidad de protección suele centrarse en deudas y gastos finales.")

    obligations = [o for o in a.get("obligaciones", []) if o != "Ninguna"]
    if obligations:
        points += min(len(obligations), 2)
        findings.append("Obligaciones financieras declaradas: " + ", ".join(obligations).lower() + ".")
        considerations.append("Revisa con tu asesor si conviene que la suma asegurada contemple el saldo de tus créditos vigentes.")

    cov = a.get("cobertura_actual", "No estoy seguro")
    if cov == "Ninguna":
        points += 2
        findings.append("Actualmente no cuentas con seguro de vida: existe una brecha de protección.")
    elif cov == "Solo la de mi empleo (prestación)":
        points += 1
        findings.append("Tu protección depende de una prestación laboral, que normalmente termina si cambias de empleo.")
        considerations.append("Pide a Recursos Humanos el monto de suma asegurada de tu prestación para compararlo con tus necesidades.")
    elif cov == "No estoy seguro":
        considerations.append("Localiza tus pólizas actuales; un asesor puede ayudarte a revisarlas.")

    age = a.get("edad")
    if age in ("18 a 29", "30 a 39"):
        considerations.append("Contratar a edades tempranas suele facilitar la aceptación; el costo final lo determina cada aseguradora.")
    if age == "60 o más":
        considerations.append("A partir de cierta edad algunas aseguradoras aplican requisitos adicionales; tu asesor te indicará opciones.")

    if a.get("ingresos") == "Prefiero no decir":
        considerations.append("Conocer tu rango de ingresos ayuda a estimar una suma asegurada adecuada; puedes comentarlo con tu asesor.")

    if deps != "Ninguno":
        considerations.append(
            "Un enfoque común para definir la suma asegurada es estimar cuántos años de ingresos necesitarían tus "
            "dependientes y sumar las deudas pendientes; tu asesor lo calculará contigo.")
    else:
        considerations.append(
            "Sin dependientes, la suma asegurada suele enfocarse en cubrir deudas y gastos finales; tu asesor "
            "lo revisará contigo.")
    return _result(PRODUCT_VIDA, points, a, findings, considerations)


def diagnose_gmm(a: dict) -> dict:
    points = 0
    findings, considerations = [], []

    cov = a.get("cobertura_actual", "No estoy seguro")
    if cov == "Ninguna":
        points += 3
        findings.append("No cuentas con ninguna cobertura médica: un evento hospitalario podría afectar significativamente tu patrimonio.")
    elif cov == "Solo IMSS / ISSSTE":
        points += 2
        findings.append("Cuentas con seguridad social; un seguro de GMM te daría acceso a la red de hospitales privados según la póliza.")
    elif cov == "GMM de mi empleo (prestación)":
        points += 1
        findings.append("Tu GMM depende de tu empleo; conviene revisar la suma asegurada, el deducible y qué pasa si cambias de trabajo.")
        considerations.append("Pregunta si tu póliza de empresa permite conversión a póliza individual al dejar el empleo.")
    elif cov == "No estoy seguro":
        considerations.append("Ubica tus pólizas actuales para que tu asesor identifique posibles huecos de cobertura.")

    tipo = a.get("tipo", "Individual")
    n = int(a.get("asegurados", 1) or 1)
    if tipo == "Familiar" or n > 1:
        points += 2
        findings.append(f"Buscas proteger a {n} persona(s); una póliza familiar puede simplificar la administración.")
    age = a.get("edad")
    if age in ("40 a 49", "50 a 59", "60 o más"):
        points += 1
        considerations.append("En GMM la edad influye en el costo y en los requisitos de contratación; conviene no posponer la evaluación.")

    city = a.get("ciudad")
    if city:
        considerations.append(f"Verifica que la red hospitalaria de la aseguradora tenga cobertura en {city} y en los hospitales que prefieras.")
    considerations.append("Compara suma asegurada, deducible, coaseguro y tope de coaseguro entre opciones; tu asesor te las explicará.")
    considerations.append("Los periodos de espera y las exclusiones varían por aseguradora; revísalos antes de contratar.")
    return _result(PRODUCT_GMM, points, a, findings, considerations)


def _result(product: str, points: int, a: dict, findings: list, considerations: list) -> dict:
    intent = INTENT_MAP.get(a.get("intencion"), "Baja")
    need = _level(points)
    budget = a.get("presupuesto")
    if budget == "No lo sé aún" or not budget:
        considerations.append("Aún no defines presupuesto: tu asesor puede mostrarte alternativas en distintos rangos.")
    if intent == "Alta":
        steps = ["Agenda una llamada con tu asesor esta semana.", "Ten a la mano tus pólizas actuales (si las tienes).",
                 "Solicita una cotización formal con al menos dos alternativas."]
    elif intent == "Media":
        steps = ["Solicita una cotización informativa sin compromiso.", "Define con tu familia el presupuesto mensual que estás dispuesto a destinar."]
    else:
        steps = ["Revisa este diagnóstico con calma.", "Cuando estés listo, solicita una asesoría sin compromiso."]
    return {
        "product": product,
        "need_level": need,
        "intent": intent,
        "points": points,
        "findings": findings,
        "considerations": considerations,
        "next_steps": steps,
        "disclaimer": DISCLAIMER,
        "budget": budget if budget in BUDGET_RANGES else None,
    }


def diagnose(product: str, answers: dict) -> dict:
    if product == PRODUCT_VIDA:
        return diagnose_life(answers)
    if product == PRODUCT_GMM:
        return diagnose_gmm(answers)
    raise ValueError(f"Producto no soportado: {product}")
