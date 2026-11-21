"""AI Sales Intelligence — análisis determinístico sobre los datos reales.

Cada análisis devuelve:
  * ``answer``: texto en markdown construido solo con cifras calculadas.
  * ``table``: DataFrame de soporte.
  * ``facts``: resumen agregado y SIN datos personales, apto para enviarse a un
    modelo de lenguaje (opcional) que lo explique en lenguaje natural.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

import pandas as pd

from utils.dates import day
from utils.config import CLOSED_STAGES, IDX_QUALIFIED, STAGE_LOST, STAGES, today_mx
from services.metrics import (
    campaign_table,
    fmt_money,
    fmt_pct,
    fmt_ratio,
    funnel_counts,
    product_conversion,
    safe_div,
)

MIN_LEADS_FOR_RANKING = 5


@dataclass
class Insight:
    key: str
    title: str
    answer: str
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    facts: dict = field(default_factory=dict)


def _active(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["stage"].isin(CLOSED_STAGES)]


def _empty(key: str, title: str) -> Insight:
    return Insight(key, title, "No hay datos suficientes en el conjunto seleccionado para responder esta pregunta.",
                   facts={"sin_datos": True})


# ---------------------------------------------------------------------------
def best_leads(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None, top: int = 15) -> Insight:
    title = "¿Cuáles son mis leads prioritarios?"
    act = _active(leads)
    if act.empty:
        return _empty("best", title)
    top_df = act.sort_values(["score", "created_at"], ascending=[False, False]).head(top)
    high = int((act["score"] >= 80).sum())
    lines = [
        f"- Tienes **{len(act):,} leads activos**; **{high:,}** están en *Alta prioridad* (score ≥ 80).",
        f"- El score promedio de los {len(top_df)} mejores es **{top_df['score'].mean():.0f}/100**.",
    ]
    prod_mix = top_df["product"].value_counts()
    if not prod_mix.empty:
        lines.append(f"- Entre ellos predomina **{prod_mix.index[0]}** ({prod_mix.iloc[0]} de {len(top_df)}).")
    no_next = int(top_df["next_action"].isna().sum())
    if no_next:
        lines.append(f"- **{no_next}** de estos leads no tienen próxima acción registrada: asígnala hoy.")
    table = top_df[["id", "name", "product", "city", "stage", "score", "priority", "next_action", "phone"]].rename(
        columns={"id": "ID", "name": "Nombre", "product": "Producto", "city": "Ciudad", "stage": "Etapa",
                 "score": "Score", "priority": "Prioridad", "next_action": "Próxima acción", "phone": "Teléfono"})
    facts = {
        "leads_activos": len(act), "alta_prioridad": high,
        "top": [{"id": int(r.id), "producto": r.product, "etapa": r.stage, "score": int(r.score)}
                for r in top_df.itertuples()],
        "top_sin_proxima_accion": no_next,
    }
    return Insight("best", title, "\n".join(lines), table, facts)


def best_campaigns(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Qué campañas están funcionando mejor?"
    ct = campaign_table(camps, leads)
    if ct.empty:
        # Sin campañas registradas: analizar por fuente
        if leads.empty:
            return _empty("campaigns", title)
        from services.metrics import conversion_by
        by_src = conversion_by(leads, "source").rename(columns={"source": "Fuente"})
        ranked = by_src[by_src["Leads"] >= MIN_LEADS_FOR_RANKING].sort_values("Conversión %", ascending=False)
        lines = ["- No hay campañas registradas; el análisis se hace por **fuente de adquisición**."]
        if not ranked.empty and pd.notna(ranked.iloc[0]["Conversión %"]):
            r = ranked.iloc[0]
            lines.append(f"- Mejor fuente por conversión: **{r['Fuente']}** con {fmt_pct(r['Conversión %'])} "
                         f"({int(r['Pólizas'])} pólizas de {int(r['Leads'])} leads).")
        return Insight("campaigns", title, "\n".join(lines), by_src,
                       {"por_fuente": by_src.drop(columns=["Comisiones"]).to_dict("records")})

    eligible = ct[ct["Leads"] >= MIN_LEADS_FOR_RANKING]
    lines = [f"- Se analizaron **{len(ct)} campañas** (inversión total {fmt_money(ct['Inversión'].sum())})."]
    if eligible.empty:
        lines.append(f"- Ninguna campaña tiene al menos {MIN_LEADS_FOR_RANKING} leads; aún no hay base para compararlas.")
    else:
        by_roas = eligible.dropna(subset=["ROAS comisiones"]).sort_values("ROAS comisiones", ascending=False)
        if not by_roas.empty:
            b = by_roas.iloc[0]
            lines.append(f"- Mayor retorno en comisiones: **{b['Campaña']}** ({fmt_ratio(b['ROAS comisiones'])}: "
                         f"{fmt_money(b['Comisiones'])} de comisión por {fmt_money(b['Inversión'])} invertidos).")
        by_cpl = eligible.dropna(subset=["CPL"]).sort_values("CPL")
        if not by_cpl.empty:
            c = by_cpl.iloc[0]
            lines.append(f"- Lead más barato: **{c['Campaña']}** con CPL de {fmt_money(c['CPL'], 2)}.")
        by_conv = eligible.dropna(subset=["Conversión %"]).sort_values("Conversión %", ascending=False)
        if not by_conv.empty:
            v = by_conv.iloc[0]
            lines.append(f"- Mejor conversión a póliza: **{v['Campaña']}** ({fmt_pct(v['Conversión %'])}).")
        losers = eligible[(eligible["Pólizas"] == 0) & (eligible["Inversión"].fillna(0) > 0)]
        if not losers.empty:
            lines.append(f"- **{len(losers)}** campaña(s) con inversión y sin pólizas: "
                         + ", ".join(losers["Campaña"].head(5)) + ". Revisa segmentación o mensaje.")
    show = ct.drop(columns=["id"])
    facts = {"campanas": show.to_dict("records")}
    return Insight("campaigns", title, "\n".join(lines), show, facts)


def needs_follow_up(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None,
                    stale_days: int = 3) -> Insight:
    title = "¿Qué prospectos necesitan seguimiento?"
    today = today or today_mx()
    act = _active(leads)
    if act.empty:
        return _empty("follow", title)
    nad = day(act["next_action_date"])
    updated = day(act["updated_at"])
    overdue = act[nad.notna() & (nad <= pd.Timestamp(today))]
    stale_cut = pd.Timestamp(today - timedelta(days=stale_days))
    no_plan = act[nad.isna() & (updated <= stale_cut) & (act["score"] >= 50)]
    new_uncontacted = act[(act["stage"] == "Nuevo") & (updated <= pd.Timestamp(today - timedelta(days=1)))]
    lines = [
        f"- **{len(overdue):,}** leads con próxima acción vencida o para hoy.",
        f"- **{len(no_plan):,}** leads con score ≥ 50 sin próxima acción y sin movimiento en {stale_days}+ días.",
        f"- **{len(new_uncontacted):,}** leads en etapa *Nuevo* con más de 24 h sin contacto.",
    ]
    if len(new_uncontacted):
        lines.append("- Prioriza el primer contacto: la probabilidad de respuesta disminuye con el tiempo.")
    out = pd.concat([
        overdue.assign(Motivo="Acción vencida / hoy"),
        no_plan.assign(Motivo="Sin próxima acción"),
        new_uncontacted.assign(Motivo="Nuevo sin contactar"),
    ]).drop_duplicates("id").sort_values("score", ascending=False)
    table = out[["id", "name", "product", "stage", "score", "next_action", "next_action_date", "Motivo", "phone"]].rename(
        columns={"id": "ID", "name": "Nombre", "product": "Producto", "stage": "Etapa", "score": "Score",
                 "next_action": "Próxima acción", "next_action_date": "Fecha acción", "phone": "Teléfono"})
    facts = {"vencidas": len(overdue), "sin_plan_score_50": len(no_plan), "nuevos_sin_contacto": len(new_uncontacted),
             "total_a_atender": len(out)}
    return Insight("follow", title, "\n".join(lines), table, facts)


def where_we_lose(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Dónde estoy perdiendo clientes?"
    if leads.empty:
        return _empty("loss", title)
    fun = funnel_counts(leads)
    drops = []
    for i in range(1, len(fun)):
        prev, cur = fun.loc[i - 1, "Leads"], fun.loc[i, "Leads"]
        drops.append({"Transición": f"{fun.loc[i - 1, 'Etapa']} → {fun.loc[i, 'Etapa']}",
                      "Entraron": int(prev), "Avanzaron": int(cur), "No avanzaron": int(prev - cur),
                      "Tasa de paso %": safe_div(cur, prev, 100)})
    drops_df = pd.DataFrame(drops)
    valid = drops_df.dropna(subset=["Tasa de paso %"])
    lines = []
    if not valid.empty:
        worst = valid.sort_values("Tasa de paso %").iloc[0]
        biggest = valid.sort_values("No avanzaron", ascending=False).iloc[0]
        lines.append(f"- La transición con **menor tasa de paso** es *{worst['Transición']}*: "
                     f"solo {fmt_pct(worst['Tasa de paso %'])} avanza.")
        lines.append(f"- El **mayor volumen** de oportunidades se queda en *{biggest['Transición']}* "
                     f"({int(biggest['No avanzaron']):,} leads).")
    lost = leads[leads["stage"] == STAGE_LOST]
    if not lost.empty:
        by_stage = lost["max_stage_index"].map(lambda i: STAGES[int(i)] if 0 <= int(i) < len(STAGES) else "—").value_counts()
        lines.append(f"- **{len(lost):,}** leads marcados como *Perdido*; la mayoría se perdió después de "
                     f"*{by_stage.index[0]}* ({int(by_stage.iloc[0])}).")
        reasons = lost["lost_reason"].dropna().value_counts().head(3)
        if not reasons.empty:
            lines.append("- Motivos más frecuentes: " + ", ".join(f"{k} ({v})" for k, v in reasons.items()) + ".")
    else:
        lines.append("- No hay leads marcados como *Perdido*; registra el motivo de pérdida para afinar este análisis.")
    facts = {"embudo": fun.to_dict("records"), "transiciones": drops_df.to_dict("records"), "perdidos": len(lost)}
    return Insight("loss", title, "\n".join(lines), drops_df, facts)


def product_performance(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Qué producto tiene mejor conversión?"
    if leads.empty:
        return _empty("product", title)
    pc = product_conversion(leads)
    lines = []
    for r in pc.to_dict("records"):
        lines.append(f"- **{r['Producto']}**: {int(r['Leads']):,} leads, {int(r['Pólizas']):,} pólizas → conversión "
                     f"{fmt_pct(r['Conversión %'])}; comisiones {fmt_money(r['Comisiones'])}.")
    valid = pc.dropna(subset=["Conversión %"])
    valid = valid[valid["Leads"] >= MIN_LEADS_FOR_RANKING]
    if len(valid) >= 2:
        best = valid.sort_values("Conversión %", ascending=False).iloc[0]
        lines.append(f"- **{best['Producto']}** convierte mejor en este periodo.")
    elif len(valid) < 2:
        lines.append("- Aún no hay suficientes datos en ambos productos para concluir cuál convierte mejor.")
    return Insight("product", title, "\n".join(lines), pc, {"por_producto": pc.to_dict("records")})


def best_segments(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Qué segmento convierte mejor?"
    from services.market import segment_overview
    seg = segment_overview(leads)
    if seg.empty:
        return Insight("segment", title, "- Aún no hay leads con segmento registrado. Agrega el campo «segmento» en la "
                       "captación o en el CRM.", seg, {"sin_datos": True})
    elig = seg[seg["Leads"] >= MIN_LEADS_FOR_RANKING].dropna(subset=["Conversión %"]).sort_values("Conversión %", ascending=False)
    lines = [f"- {int(seg['Leads'].sum()):,} leads tienen segmento registrado en {len(seg)} segmentos."]
    if not elig.empty:
        b, w = elig.iloc[0], elig.iloc[-1]
        lines.append(f"- Mejor conversión: **{b['Segmento']}** ({fmt_pct(b['Conversión %'])}, {int(b['Pólizas'])} pólizas).")
        if len(elig) > 1:
            lines.append(f"- Menor conversión: **{w['Segmento']}** ({fmt_pct(w['Conversión %'])}).")
    return Insight("segment", title, "\n".join(lines), seg, {"por_segmento": seg.to_dict("records")})


def campaigns_to_optimize(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Qué campañas debería optimizar?"
    from services.optimization import recommendations
    ct = campaign_table(camps, leads)
    recs = recommendations(ct, leads)
    if recs.empty:
        return Insight("optimize", title, "- No se detectaron campañas que requieran optimización con las reglas "
                       "actuales (o no hay datos suficientes).", recs, {"recomendaciones": []})
    focus = recs[recs["Tipo"].isin(["CPL elevado", "Requiere revisión", "Leads de baja calidad", "Prueba A/B"])]
    lines = [f"- Se generaron **{len(recs)} recomendaciones**; **{len(focus)}** señalan campañas o anuncios a optimizar."]
    for r in focus.head(6).to_dict("records"):
        lines.append(f"- *{r['Tipo']}* · **{r['Elemento']}**: {r['Evidencia']}")
    lines.append("- Ningún cambio se aplica automáticamente: revisa y aprueba cada acción en la plataforma publicitaria.")
    return Insight("optimize", title, "\n".join(lines), recs, {"recomendaciones": recs.to_dict("records")})


def acquisition_cost(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Cuál es mi costo de adquisición?"
    from services.metrics import overall_acquisition
    ct = campaign_table(camps, leads)
    ov = overall_acquisition(ct)
    if ct.empty or ov["investment"] is None:
        return Insight("cac", title, "- No hay inversión registrada en campañas; registra la inversión en "
                       "«Campañas y ROI» para calcular CPL y CAC.", ct, {"sin_datos": True})
    lines = [f"- Inversión registrada: **{fmt_money(ov['investment'])}** en {len(ct)} campañas.",
             f"- CPL global: **{fmt_money(ov['CPL'], 2)}** ({ov['leads']:,} leads atribuidos).",
             f"- CAC publicitario: **{fmt_money(ov['CAC'], 2)}** ({ov['policies']:,} pólizas).",
             f"- ROAS de comisiones: **{fmt_ratio(ov['ROAS'])}**."]
    by_plat = ct.groupby("Plataforma").agg(Inversión=("Inversión", "sum"), Leads=("Leads", "sum"),
                                           Pólizas=("Pólizas", "sum"), Comisiones=("Comisiones", "sum")).reset_index()
    by_plat["CPL"] = [safe_div(i, l) for i, l in zip(by_plat["Inversión"], by_plat["Leads"])]
    by_plat["CAC"] = [safe_div(i, p) for i, p in zip(by_plat["Inversión"], by_plat["Pólizas"])]
    valid = by_plat.dropna(subset=["CAC"])
    if not valid.empty:
        b = valid.sort_values("CAC").iloc[0]
        lines.append(f"- Plataforma con menor CAC: **{b['Plataforma']}** ({fmt_money(b['CAC'], 2)}).")
    return Insight("cac", title, "\n".join(lines), by_plat, {"global": ov, "por_plataforma": by_plat.to_dict("records")})


def product_commissions(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    title = "¿Qué producto genera mayores comisiones?"
    if leads.empty:
        return _empty("commission", title)
    pc = product_conversion(leads)
    pol = leads[leads["stage"] == "Póliza emitida"]
    lines = []
    if pol.empty or pol["commission"].fillna(0).sum() == 0:
        lines.append("- Aún no hay comisiones registradas. Registra pólizas emitidas con su comisión en el CRM.")
    else:
        g = pol.groupby("product").agg(Comisiones=("commission", "sum"), Pólizas=("id", "count"),
                                       Promedio=("commission", "mean")).reset_index()
        g = g.sort_values("Comisiones", ascending=False)
        for r in g.to_dict("records"):
            lines.append(f"- **{r['product']}**: {fmt_money(r['Comisiones'])} en {int(r['Pólizas'])} pólizas "
                         f"(promedio {fmt_money(r['Promedio'])} por póliza).")
        lines.append(f"- **{g.iloc[0]['product']}** genera más comisiones en el periodo seleccionado.")
    return Insight("commission", title, "\n".join(lines), pc, {"por_producto": pc.to_dict("records")})


QUESTIONS: dict[str, tuple[str, Callable[..., Insight]]] = {
    "campaigns": ("¿Qué campañas están funcionando mejor?", best_campaigns),
    "best": ("¿Cuáles son mis leads prioritarios?", best_leads),
    "segment": ("¿Qué segmento convierte mejor?", best_segments),
    "loss": ("¿Dónde estoy perdiendo clientes?", where_we_lose),
    "optimize": ("¿Qué campañas debería optimizar?", campaigns_to_optimize),
    "follow": ("¿Qué prospectos necesitan seguimiento?", needs_follow_up),
    "cac": ("¿Cuál es mi costo de adquisición?", acquisition_cost),
    "commission": ("¿Qué producto genera mayores comisiones?", product_commissions),
    "product": ("¿Qué producto tiene mejor conversión?", product_performance),
}

KEYWORDS = {
    "best": ["mejor lead", "mejores lead", "prioritario", "prioridad", "top", "calientes", "score alto"],
    "campaigns": ["campana funciona", "campanas funcionan", "mejor campana", "mejores campanas", "funcionando", "roas"],
    "segment": ["segmento", "perfil", "publico"],
    "loss": ["pierdo", "perdiendo", "perd", "fuga", "embudo", "funnel", "abandon"],
    "optimize": ["optimizar", "mejorar campana", "ajustar", "pausar", "cpl alto"],
    "follow": ["seguimiento", "contactar", "pendiente", "vencid", "llamar", "atender"],
    "cac": ["costo de adquisicion", "cac", "cpl", "cuanto me cuesta", "costo por lead", "inversion"],
    "commission": ["comision", "comisiones", "ingreso", "rentab"],
    "product": ["producto convierte", "conversion por producto", "vida o gmm"],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def route_question(text: str) -> Optional[str]:
    t = _norm(text or "")
    scores = {k: sum(1 for w in words if _norm(w) in t) for k, words in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def run(key: str, leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> Insight:
    _, fn = QUESTIONS[key]
    return fn(leads, camps, today=today)


def global_facts(leads: pd.DataFrame, camps: pd.DataFrame, today: Optional[date] = None) -> dict:
    """Resumen agregado (sin datos personales) de todos los análisis."""
    return {k: run(k, leads, camps, today).facts for k in QUESTIONS}
