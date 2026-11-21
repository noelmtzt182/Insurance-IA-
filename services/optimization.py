"""Motor D — Acquisition Optimization.

Recomendaciones basadas en reglas sobre los datos registrados. Cada
recomendación indica la evidencia y el origen de los datos. La app no modifica
presupuestos ni publica nada: toda acción requiere aprobación del usuario.
"""
from __future__ import annotations

import pandas as pd

from services.metrics import conversion_by, fmt_money, fmt_pct, safe_div

MIN_LEADS = 5


def _rec(tipo, elemento, evidencia, accion, prioridad, origen):
    return {"Tipo": tipo, "Elemento": elemento, "Evidencia": evidencia, "Acción sugerida": accion,
            "Prioridad": prioridad, "Origen de datos": origen, "Requiere aprobación": "Sí"}


def recommendations(ct: pd.DataFrame, leads: pd.DataFrame) -> pd.DataFrame:
    recs: list[dict] = []
    cols = ["Tipo", "Elemento", "Evidencia", "Acción sugerida", "Prioridad", "Origen de datos", "Requiere aprobación"]
    if not ct.empty:
        elig = ct[ct["Leads"] >= MIN_LEADS]

        # 1. CPL elevado
        cpl = elig.dropna(subset=["CPL"])
        if len(cpl) >= 3:
            med = cpl["CPL"].median()
            for _, r in cpl[cpl["CPL"] > med * 1.3].iterrows():
                recs.append(_rec("CPL elevado", r["Campaña"],
                                 f"CPL {fmt_money(r['CPL'], 2)} vs mediana {fmt_money(med, 2)} ({int(r['Leads'])} leads).",
                                 "Revisar segmentación y palabras clave; mover presupuesto a grupos con menor CPL "
                                 "si la calidad de lead es similar.", "Alta", r["Origen de datos"]))

        # 2. Mayor conversión
        conv = elig.dropna(subset=["Conversión %"]).sort_values("Conversión %", ascending=False)
        if not conv.empty and conv.iloc[0]["Conversión %"] > 0:
            r = conv.iloc[0]
            recs.append(_rec("Mayor conversión", r["Campaña"],
                             f"Conversión a póliza {fmt_pct(r['Conversión %'])} ({int(r['Pólizas'])} de {int(r['Leads'])}).",
                             "Considerar aumentar presupuesto de forma gradual (10–20 %) y replicar su mensaje.",
                             "Media", r["Origen de datos"]))

        # 5. Requieren revisión
        for _, r in ct.iterrows():
            inv = r["Inversión"] or 0
            if inv > 0 and r["Leads"] == 0:
                recs.append(_rec("Requiere revisión", r["Campaña"], f"Inversión {fmt_money(inv)} sin leads registrados.",
                                 "Verificar seguimiento UTM, formulario y aprobación de anuncios en la plataforma.",
                                 "Alta", r["Origen de datos"]))
            elif r["Pólizas"] > 0 and r["ROAS comisiones"] is not None and r["ROAS comisiones"] < 1:
                recs.append(_rec("Requiere revisión", r["Campaña"],
                                 f"ROAS de comisiones {r['ROAS comisiones']:.2f}x: la comisión no cubre la inversión.",
                                 "Revisar CAC y calidad de leads antes de mantener el presupuesto.", "Alta",
                                 r["Origen de datos"]))
        ctr = ct.dropna(subset=["CTR %"])
        ctr = ctr[ctr["Impresiones"].fillna(0) >= 1000]
        if len(ctr) >= 3:
            med = ctr["CTR %"].median()
            for _, r in ctr[ctr["CTR %"] < med * 0.5].iterrows():
                recs.append(_rec("Requiere revisión", r["Campaña"],
                                 f"CTR {fmt_pct(r['CTR %'], 2)} vs mediana {fmt_pct(med, 2)}.",
                                 "Probar nuevos titulares o creatividades; revisar relevancia del público.", "Media",
                                 r["Origen de datos"]))

        # 6. Oportunidades A/B
        if not leads.empty:
            for _, r in elig.iterrows():
                sub = leads[leads["campaign_id"] == r["id"]]
                ads = sub["ad_id"].dropna().unique()
                if len(sub) >= 20 and len(ads) <= 1:
                    recs.append(_rec("Prueba A/B", r["Campaña"], f"{len(sub)} leads atribuidos a {len(ads)} anuncio.",
                                     "Crear una segunda variante creativa (otro ángulo o CTA) y repartir el presupuesto.",
                                     "Media", "CRM"))

    if not leads.empty:
        # 3. Anuncios con leads de baja calidad
        ads = leads.dropna(subset=["ad_id"])
        if not ads.empty:
            g = ads.groupby("ad_id").agg(Leads=("id", "count"), Score=("score", "mean"),
                                         Calif=("max_stage_index", lambda x: (x >= 2).mean() * 100))
            avg = leads["score"].mean()
            for ad, r in g[(g["Leads"] >= MIN_LEADS) & (g["Score"] < min(45, avg - 10))].iterrows():
                recs.append(_rec("Leads de baja calidad", f"Anuncio {ad}",
                                 f"Score promedio {r['Score']:.0f} vs {avg:.0f} general; {r['Calif']:.0f}% calificados.",
                                 "Ajustar el mensaje para atraer prospectos con intención real o pausar el anuncio.",
                                 "Media", "CRM"))
        # 4. Segmentos con mejores resultados
        seg = conversion_by(leads[leads["segment"].notna()], "segment") if leads["segment"].notna().any() else pd.DataFrame()
        if not seg.empty:
            seg = seg[seg["Leads"] >= MIN_LEADS].dropna(subset=["Conversión %"]).sort_values("Conversión %", ascending=False)
            if not seg.empty and seg.iloc[0]["Conversión %"] > 0:
                r = seg.iloc[0]
                recs.append(_rec("Mejor segmento", r["segment"],
                                 f"Conversión {fmt_pct(r['Conversión %'])} con {int(r['Leads'])} leads.",
                                 "Crear o reforzar campañas dirigidas a este segmento.", "Media", "CRM"))
    return pd.DataFrame(recs, columns=cols)
