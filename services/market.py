"""Market Intelligence — motor de recomendaciones basado en reglas.

Separa explícitamente tres tipos de información:
  * VERIFICADA: cifras calculadas con los registros de tu propio CRM.
  * HIPÓTESIS: supuestos comerciales razonables, por validar con datos.
  * IA: análisis adicional opcional, generado a partir de las dos anteriores.

No extrae datos personales de redes sociales ni genera listas de contacto.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from services.metrics import conversion_by, fmt_money, fmt_pct
from utils.config import PRODUCT_GMM, PRODUCT_VIDA

SEGMENT_PROFILES = {
    "Profesionistas independientes": {
        "need": "Suelen no contar con prestaciones de un empleador; su ingreso depende de su capacidad de trabajar.",
        "products": [PRODUCT_GMM, PRODUCT_VIDA],
        "channels": ["Google Ads (búsqueda)", "Instagram", "LinkedIn"],
        "message": "Tu independencia merece protección: asesoría para cubrir lo que antes daba una empresa.",
        "objections": ["Ingresos variables", "Percepción de costo alto"],
    },
    "Padres de familia": {
        "need": "Buscan proteger a sus dependientes y la educación de sus hijos ante un imprevisto.",
        "products": [PRODUCT_VIDA, PRODUCT_GMM],
        "channels": ["Facebook", "Instagram", "Google Ads (búsqueda)"],
        "message": "Protege lo que más importa: un plan pensado para el futuro de tu familia.",
        "objections": ["Lo pospongo", "Ya tengo la prestación del trabajo"],
    },
    "Empresarios": {
        "need": "Protección patrimonial, continuidad del negocio y beneficios para sí mismos y socios.",
        "products": [PRODUCT_VIDA, PRODUCT_GMM],
        "channels": ["LinkedIn", "Google Ads (búsqueda)", "Referidos"],
        "message": "Protege tu patrimonio y la continuidad de tu negocio con asesoría especializada.",
        "objections": ["Falta de tiempo", "Ya tengo un asesor"],
    },
    "Emprendedores": {
        "need": "Etapa de crecimiento con poca protección formal y presupuesto ajustado.",
        "products": [PRODUCT_GMM, PRODUCT_VIDA],
        "channels": ["Instagram", "TikTok", "Facebook"],
        "message": "Mientras construyes tu proyecto, cuida tu salud y a quienes dependen de ti.",
        "objections": ["Presupuesto limitado", "No es prioridad hoy"],
    },
    "Directivos": {
        "need": "Cuentan con prestaciones, pero pueden tener sumas aseguradas insuficientes o ligadas al empleo.",
        "products": [PRODUCT_VIDA, PRODUCT_GMM],
        "channels": ["LinkedIn", "Google Ads (búsqueda)"],
        "message": "Complementa tus prestaciones con una protección que no depende de tu empleo.",
        "objections": ["Ya tengo seguro de empresa"],
    },
    "Pequeñas y medianas empresas": {
        "need": "Atraer y retener talento con beneficios; proteger a socios y personal clave.",
        "products": [PRODUCT_GMM, PRODUCT_VIDA],
        "channels": ["LinkedIn", "Google Ads (búsqueda)", "Eventos empresariales"],
        "message": "Beneficios para tu equipo: seguros colectivos con asesoría para tu pyme.",
        "objections": ["Costo por empleado", "Trámites administrativos"],
    },
}


def verified_metrics(leads: pd.DataFrame, product: Optional[str], segment: Optional[str],
                     location: Optional[str]) -> dict:
    """Cifras del CRM para el filtro elegido (información verificada)."""
    df = leads
    if product:
        df = df[df["product"] == product]
    if segment:
        df = df[df["segment"] == segment]
    if location:
        df = df[df["city"].fillna("").str.lower() == location.lower()]
    out = {"leads": len(df)}
    if df.empty:
        return out
    from services.metrics import lead_kpis
    k = lead_kpis(df)
    out.update({"calificados": k["qualified"], "cotizaciones": k["quotes"], "polizas": k["policies"],
                "conversion": k["conversion"], "comisiones": k["commissions"],
                "score_promedio": float(df["score"].mean())})
    src = conversion_by(df, "source")
    src = src[src["Leads"] >= 3]
    if not src.empty:
        best = src.sort_values(["Conversión %", "Leads"], ascending=False).iloc[0]
        out["mejor_fuente"] = {"fuente": best["source"], "leads": int(best["Leads"]),
                               "conversion": best["Conversión %"]}
    return out


def analyze(leads: pd.DataFrame, product: Optional[str], segment: str, location: Optional[str]) -> dict:
    profile = SEGMENT_PROFILES.get(segment, {})
    verified = verified_metrics(leads, product, segment, location)
    seg_all = verified_metrics(leads, product, None, location)

    verified_lines = []
    if verified["leads"] == 0:
        verified_lines.append("No hay leads registrados para esta combinación; las recomendaciones se basan en hipótesis.")
    else:
        verified_lines.append(f"{verified['leads']:,} leads registrados; {verified['calificados']:,} calificados, "
                              f"{verified['polizas']:,} pólizas (conversión {fmt_pct(verified['conversion'])}).")
        verified_lines.append(f"Score promedio: {verified['score_promedio']:.0f}/100. "
                              f"Comisiones registradas: {fmt_money(verified['comisiones'])}.")
        if seg_all.get("conversion") is not None and verified.get("conversion") is not None:
            diff = verified["conversion"] - seg_all["conversion"]
            verified_lines.append(f"Frente al total del filtro sin segmento ({fmt_pct(seg_all['conversion'])}), "
                                  f"este segmento está {'+' if diff >= 0 else ''}{diff:.1f} puntos.")
        if verified.get("mejor_fuente"):
            mf = verified["mejor_fuente"]
            verified_lines.append(f"Fuente con mejor conversión en este segmento: {mf['fuente']} "
                                  f"({fmt_pct(mf['conversion'])}, {mf['leads']} leads).")

    hypotheses = [f"Necesidad: {profile.get('need', 'Sin perfil definido.')}",
                  "Objeciones frecuentes esperadas: " + ", ".join(profile.get("objections", [])) + "."]

    recs = []
    channels = list(profile.get("channels", []))
    if verified.get("mejor_fuente") and verified["leads"] >= 10:
        recs.append(f"Prioriza {verified['mejor_fuente']['fuente']}: es el canal con mejor conversión observada.")
    if channels:
        recs.append("Canales sugeridos (hipótesis): " + ", ".join(channels) + ".")
    prod_fit = profile.get("products", [])
    if product and prod_fit and product != prod_fit[0]:
        recs.append(f"Para este segmento suele resonar primero {prod_fit[0].lower()}; considera una oferta combinada.")
    recs.append(f"Mensaje recomendado: «{profile.get('message', 'Protege lo que más importa.')}»")
    if verified["leads"] and verified.get("conversion") is not None and verified["conversion"] < 3:
        recs.append("La conversión observada es baja: revisa la velocidad del primer contacto y la calidad del lead.")
    return {"verified": verified_lines, "hypotheses": hypotheses, "recommendations": recs,
            "facts": {"segmento": segment, "producto": product, "ubicacion": location, "crm": verified,
                      "hipotesis": profile}}


def segment_overview(leads: pd.DataFrame) -> pd.DataFrame:
    if leads.empty or not leads["segment"].notna().any():
        return pd.DataFrame(columns=["Segmento", "Leads", "Calificados", "Cotizaciones", "Pólizas", "Conversión %",
                                     "Comisiones"])
    return conversion_by(leads[leads["segment"].notna()], "segment").rename(columns={"segment": "Segmento"})
