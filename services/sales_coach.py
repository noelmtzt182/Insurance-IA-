"""AI Sales Coach — venta consultiva y ética.

Principios aplicados en todo el módulo:
  * Explicar el valor de la protección sin presionar ni generar miedo excesivo.
  * Nunca afirmar precios, coberturas o condiciones que no provengan de una cotización oficial.
  * Nunca recomendar cancelar una póliza vigente sin un análisis comparativo completo.
  * Respetar la decisión del prospecto y su derecho a no continuar.
"""
from __future__ import annotations

import re
import unicodedata

from utils.config import PRODUCT_GMM, PRODUCT_VIDA


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


OBJECTIONS: dict[str, dict] = {
    "Precio": {
        "triggers": ["caro", "costoso", "no me alcanza", "muy alto", "mucho dinero", "precio", "barato", "presupuesto"],
        "example": "Está muy caro.",
        "intent": "Entender qué parte del costo preocupa y si la protección propuesta corresponde a su necesidad real.",
        "response": ("Entiendo, es una decisión importante para tu presupuesto. Para asegurarme de que la propuesta "
                     "tenga sentido para ti, ¿te parece si revisamos qué es lo más importante proteger? A veces se "
                     "puede ajustar la suma asegurada, el deducible o la forma de pago para que se adapte mejor, "
                     "siempre revisando con claridad qué cubre y qué no cada opción."),
        "questions": ["¿Con qué lo estás comparando: con otra cotización o con tu presupuesto mensual?",
                      "¿Qué monto mensual te sentirías cómodo destinando a tu protección?",
                      "Si tuviéramos que priorizar, ¿qué te preocupa más proteger?"],
        "avoid": ["Minimizar su preocupación", "Afirmar que es «la opción más barata del mercado»",
                  "Usar escenarios de miedo para justificar el precio"],
        "follow_up": "Prepara una alternativa ajustada (otra suma asegurada o deducible) con cotización oficial y agenda revisión en 2–3 días.",
    },
    "Lo voy a pensar": {
        "triggers": ["lo voy a pensar", "pensarlo", "lo pienso", "dejame pensarlo", "luego te digo", "despues te aviso",
                     "no estoy seguro", "dame tiempo"],
        "example": "Lo voy a pensar.",
        "intent": "Identificar la duda concreta que impide decidir, respetando su tiempo.",
        "response": ("Claro, es una decisión que vale la pena pensar con calma. Para que tengas toda la información, "
                     "¿hay algo de la propuesta que no haya quedado claro o que te gustaría comparar? Así puedo "
                     "enviarte justo lo que te ayude a decidir."),
        "questions": ["¿Qué parte de la propuesta te gustaría revisar con más detalle?",
                      "¿Hay alguien más con quien te gustaría revisarlo? Puedo explicarle también.",
                      "¿Qué tendría que pasar para que te sientas seguro con la decisión?"],
        "avoid": ["Inventar urgencias («la oferta vence hoy») si no es cierto", "Insistir repetidamente el mismo día"],
        "follow_up": "Envía un resumen breve de la propuesta y programa seguimiento en 3–5 días con una pregunta concreta.",
    },
    "Ya tengo seguro": {
        "triggers": ["ya tengo seguro", "ya tengo uno", "ya estoy asegurado", "tengo poliza", "ya cuento con",
                     "ya tengo gastos medicos", "ya tengo seguro de vida"],
        "example": "Ya tengo seguro.",
        "intent": "Revisar si la cobertura actual cubre sus necesidades, sin desacreditar su póliza.",
        "response": ("¡Qué bueno que ya cuentas con protección! Si te parece, puedo ayudarte a revisar tu póliza "
                     "actual para confirmar que la suma asegurada y las condiciones siguen alineadas con tus "
                     "necesidades. No se trata de cancelar nada: si tu póliza actual te funciona, lo mejor es "
                     "conservarla. Cualquier cambio solo tendría sentido después de comparar con detalle."),
        "questions": ["¿Tu seguro es individual o es una prestación de tu trabajo?",
                      "¿Recuerdas la suma asegurada y el deducible?",
                      "¿Ha cambiado algo en tu vida desde que lo contrataste (hijos, créditos, ingresos)?"],
        "avoid": ["Recomendar cancelar una póliza sin análisis comparativo completo",
                  "Hablar mal de otra aseguradora o agente", "Omitir periodos de espera o preexistencias al comparar"],
        "follow_up": "Solicita (con su permiso) una copia de la carátula de su póliza y agenda una revisión comparativa.",
    },
    "Ya tengo el de la empresa": {
        "triggers": ["prestacion", "de la empresa", "del trabajo", "me lo da mi trabajo", "seguro de grupo", "colectivo"],
        "example": "Ya tengo el seguro de la empresa.",
        "intent": "Explicar la diferencia entre una prestación laboral y una protección personal, sin alarmar.",
        "response": ("Es una gran prestación. Vale la pena revisar dos cosas: cuánto cubre y qué pasaría si cambias "
                     "de empleo, porque normalmente esa protección termina al dejar la empresa. Si quieres, revisamos "
                     "juntos si te conviene complementarla o si con ella es suficiente."),
        "questions": ["¿Sabes cuál es la suma asegurada de tu prestación?",
                      "¿Tu familia también está cubierta?", "¿Planeas cambiar de trabajo o emprender en el corto plazo?"],
        "avoid": ["Afirmar que la prestación «no sirve»"],
        "follow_up": "Pide los datos de la prestación y prepara un comparativo de necesidades.",
    },
    "No lo necesito": {
        "triggers": ["no lo necesito", "no necesito", "estoy joven", "estoy sano", "no me va a pasar nada", "no hace falta"],
        "example": "No lo necesito, estoy joven y sano.",
        "intent": "Explorar sus responsabilidades y planes sin usar el miedo como argumento.",
        "response": ("Entiendo, y qué bueno que estés bien. El seguro no se trata de esperar algo malo, sino de "
                     "proteger tus planes y a quienes dependen de ti. ¿Te puedo hacer un par de preguntas para "
                     "ver si en tu caso tiene sentido o no?"),
        "questions": ["¿Alguien depende económicamente de ti?", "¿Tienes créditos o compromisos a largo plazo?",
                      "¿Cómo cubrirías hoy un gasto médico mayor imprevisto?"],
        "avoid": ["Relatar casos trágicos para generar miedo", "Insistir si confirma que no tiene la necesidad"],
        "follow_up": "Si no hay necesidad clara, agradece y deja la puerta abierta; seguimiento en 3–6 meses.",
    },
    "Desconfianza": {
        "triggers": ["no confio", "no pagan", "fraude", "letras chiquitas", "me van a enganar", "rechazan"],
        "example": "Las aseguradoras nunca pagan.",
        "intent": "Generar confianza con transparencia sobre condiciones y exclusiones.",
        "response": ("Es una preocupación muy válida. Por eso me gusta revisar contigo, antes de contratar, las "
                     "condiciones generales: qué cubre, qué no cubre, periodos de espera y cómo es el proceso de "
                     "reclamación. Además, te acompaño en caso de un trámite."),
        "questions": ["¿Has tenido una mala experiencia con algún seguro?", "¿Qué te daría más confianza para decidir?"],
        "avoid": ["Afirmar que «todo está cubierto»", "Prometer que un siniestro será pagado"],
        "follow_up": "Envía las condiciones generales oficiales y ofrece una llamada para resolver dudas.",
    },
    "Consultarlo con mi pareja": {
        "triggers": ["mi esposa", "mi esposo", "mi pareja", "consultarlo", "mi familia decide", "platicarlo"],
        "example": "Lo tengo que consultar con mi pareja.",
        "intent": "Facilitar una decisión compartida.",
        "response": ("Me parece muy bien que lo decidan juntos. Si les resulta útil, puedo explicarles la propuesta "
                     "a ambos en una llamada breve para resolver dudas al mismo tiempo."),
        "questions": ["¿Qué crees que le gustaría saber a tu pareja?", "¿Qué horario les funcionaría a ambos?"],
        "avoid": ["Sugerir decidir sin consultar a la pareja"],
        "follow_up": "Agenda una cita conjunta.",
    },
    "No tengo tiempo": {
        "triggers": ["no tengo tiempo", "estoy ocupado", "ahorita no puedo", "otro dia", "llamame despues"],
        "example": "Ahorita no tengo tiempo.",
        "intent": "Respetar su agenda y proponer un formato breve.",
        "response": ("Claro, entiendo. ¿Te funciona que te envíe un resumen por WhatsApp y agendamos 15 minutos "
                     "cuando te acomode mejor?"),
        "questions": ["¿Qué día y horario te funciona mejor?", "¿Prefieres llamada o videollamada?"],
        "avoid": ["Insistir en el momento"],
        "follow_up": "Agenda la fecha que indique; si no responde, un solo recordatorio amable.",
    },
}

OBJECTION_CATEGORIES = list(OBJECTIONS)


def detect_objection(text: str) -> str | None:
    t = _norm(text)
    best, hits = None, 0
    for cat, data in OBJECTIONS.items():
        n = sum(1 for trig in data["triggers"] if _norm(trig) in t)
        if n > hits:
            best, hits = cat, n
    return best


DISCOVERY_QUESTIONS = {
    PRODUCT_VIDA: [
        "¿Quiénes dependen económicamente de ti hoy?",
        "Si mañana faltaras, ¿qué gastos o metas quisieras que quedaran cubiertos (educación, hipoteca, deudas)?",
        "¿Cuentas con algún seguro de vida, propio o de tu trabajo? ¿Conoces la suma asegurada?",
        "¿Por cuántos años necesitaría tu familia apoyo económico?",
        "¿Te interesa solo protección o también un componente de ahorro?",
        "¿Qué presupuesto mensual te parece razonable para tu protección?",
    ],
    PRODUCT_GMM: [
        "¿Hoy cómo cubrirías una hospitalización o cirugía importante?",
        "¿A quiénes te gustaría proteger: solo a ti o a tu familia?",
        "¿Tienes hospitales o médicos de preferencia en tu ciudad?",
        "¿Cuentas con IMSS/ISSSTE o un GMM de tu trabajo? ¿Sabes su suma asegurada y deducible?",
        "¿Prefieres un deducible más bajo o una prima más baja?",
        "¿Qué presupuesto mensual te parece razonable?",
    ],
}

VALUE_ARGUMENTS = {
    PRODUCT_VIDA: [
        "Protege el nivel de vida y las metas de quienes dependen de ti (educación, vivienda).",
        "Puede ayudar a que las deudas pendientes no se conviertan en una carga para la familia.",
        "Contratar cuando se está sano y joven suele facilitar la aceptación; el costo lo define cada aseguradora.",
        "Una póliza individual no depende de tu empleo actual.",
    ],
    PRODUCT_GMM: [
        "Ayuda a proteger tu patrimonio ante gastos hospitalarios mayores.",
        "Da acceso a la red hospitalaria privada definida en la póliza.",
        "Permite elegir el equilibrio entre deducible, coaseguro y prima según tu situación.",
        "Una póliza individual o familiar no depende de tu empleo actual.",
    ],
}

STAGE_FOLLOW_UP = {
    "Nuevo": "Primer contacto en las primeras horas; preséntate y pregunta el mejor medio y horario.",
    "Contactado": "Haz preguntas de descubrimiento y propone el diagnóstico gratuito.",
    "Calificado": "Propón una cita breve para revisar necesidades y opciones.",
    "Cita agendada": "Confirma la cita un día antes y prepara preguntas específicas.",
    "Cotización enviada": "A los 2–3 días pregunta si pudo revisarla y qué dudas tiene; ofrece una explicación guiada.",
    "Negociación": "Resuelve objeciones pendientes y explica claramente los pasos de emisión y documentos.",
    "Póliza emitida": "Envía bienvenida, explica cómo usar la póliza y, si está satisfecho, pide referidos.",
    "Perdido": "Respeta la decisión; registra el motivo y no insistas salvo que el prospecto lo solicite.",
}

# Frases que el coach marca como presión indebida o afirmaciones riesgosas
PRESSURE_PHRASES = [
    "ultima oportunidad", "solo hoy", "hoy o nunca", "te vas a arrepentir", "si no lo haces", "garantizado",
    "garantizo", "cubre todo", "sin letras chiquitas", "cancela tu poliza", "cancela tu seguro", "el mas barato",
    "nadie te va a dar", "firma ya", "no seas irresponsable", "tu familia sufrira", "vas a morir",
]
EMPATHY_WORDS = ["entiendo", "comprendo", "tiene sentido", "es valido", "claro", "me parece bien", "gracias"]
VALUE_WORDS = ["proteger", "proteccion", "necesidad", "familia", "patrimonio", "tranquilidad", "revisar", "comparar",
               "opciones", "suma asegurada", "deducible", "condiciones"]


def evaluate_reply(reply: str, objection: str | None = None) -> dict:
    """Evalúa una respuesta del agente con criterios de venta consultiva (0–100)."""
    t = _norm(reply)
    feedback, score = [], 40
    pressure = [p for p in PRESSURE_PHRASES if p in t]
    if pressure:
        score -= 30
        feedback.append("⚠ Evita frases de presión o promesas: " + ", ".join(pressure) + ".")
    if any(w in t for w in EMPATHY_WORDS):
        score += 15
        feedback.append("✓ Reconoces la preocupación del prospecto.")
    else:
        feedback.append("→ Empieza validando su preocupación (p. ej. «Entiendo…»).")
    if "?" in reply or "¿" in reply:
        score += 20
        feedback.append("✓ Haces una pregunta para entender su situación.")
    else:
        feedback.append("→ Incluye al menos una pregunta abierta de descubrimiento.")
    if any(w in t for w in VALUE_WORDS):
        score += 15
        feedback.append("✓ Conectas con el valor de la protección o la necesidad.")
    else:
        feedback.append("→ Relaciona tu respuesta con su necesidad concreta.")
    if re.search(r"\$\s?\d|\d+\s?(pesos|mxn)", t):
        score -= 15
        feedback.append("⚠ No menciones montos que no provengan de una cotización oficial.")
    words = len(reply.split())
    if words > 120:
        score -= 10
        feedback.append("→ Tu respuesta es larga; en mensajería conviene ser breve.")
    elif words < 6:
        score -= 10
        feedback.append("→ La respuesta es demasiado corta para generar confianza.")
    safe_cancel = ("no cancel", "sin cancelar", "no se trata de cancelar", "no te recomiendo cancelar",
                   "antes de cancelar", "no tienes que cancelar")
    if "cancel" in t and not any(p in t for p in safe_cancel):
        score -= 20
        feedback.append("⚠ No sugieras cancelar una póliza sin un análisis comparativo completo.")
    score = max(0, min(100, score))
    level = "Excelente" if score >= 85 else "Buena" if score >= 65 else "Mejorable"
    return {"score": score, "level": level, "feedback": feedback, "pressure": pressure}


# Escenarios de simulación (rol del prospecto, determinísticos)
SCENARIOS = {
    "Padre de familia · Seguro de vida": {
        "product": PRODUCT_VIDA,
        "turns": [("Hola, vi su anuncio. ¿Para qué me serviría un seguro de vida?", None),
                  ("Mmm, suena bien, pero está muy caro, ¿no?", "Precio"),
                  ("Además ya tengo el seguro de la empresa.", "Ya tengo el de la empresa"),
                  ("Ok… lo voy a pensar.", "Lo voy a pensar")],
    },
    "Profesionista independiente · GMM": {
        "product": PRODUCT_GMM,
        "turns": [("Soy freelance y no tengo seguro médico. ¿Qué me recomiendas revisar?", None),
                  ("La verdad estoy joven y sano, no sé si lo necesito.", "No lo necesito"),
                  ("He oído que las aseguradoras nunca pagan.", "Desconfianza"),
                  ("Déjame consultarlo con mi pareja.", "Consultarlo con mi pareja")],
    },
    "Empresario · Ya tiene póliza": {
        "product": PRODUCT_GMM,
        "turns": [("Ya tengo seguro de gastos médicos, ¿para qué hablaría contigo?", "Ya tengo seguro"),
                  ("¿Me conviene cancelarlo y cambiarme?", "Ya tengo seguro"),
                  ("No tengo mucho tiempo esta semana.", "No tengo tiempo")],
    },
}
