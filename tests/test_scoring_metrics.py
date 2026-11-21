from datetime import date, timedelta

import pandas as pd

from services.metrics import campaign_metrics, campaign_table, funnel_counts, safe_div
from services.scoring import WEIGHTS, classify, recommended_action, score_lead, suggested_followup


def test_weights_sum_100():
    assert sum(WEIGHTS.values()) == 100


def test_classification_thresholds():
    assert classify(100) == classify(80) == "Alta prioridad"
    assert classify(79) == classify(50) == "Media"
    assert classify(49) == classify(0) == "Exploratorio"


def test_full_lead_scores_100():
    ref = date(2026, 1, 1)
    lead = {"name": "Ana López", "phone": "5512345678", "email": "a@example.com", "city": "CDMX",
            "product": "Seguro de vida", "budget_range": "Más de $4,000", "est_purchase_date": ref + timedelta(days=10),
            "source": "Referido", "purchase_intent": "Alta", "quote_requested": True, "contact_requested": True,
            "interactions_count": 3, "stage": "Contactado"}
    r = score_lead(lead, ref_date=ref)
    assert r.score == 100 and r.priority == "Alta prioridad"
    assert len(r.reasons) == 6 and all("detalle" in x for x in r.reasons)


def test_empty_lead_is_exploratory():
    r = score_lead({"name": "X"}, ref_date=date(2026, 1, 1))
    assert r.score < 50 and r.priority == "Exploratorio"


def test_intent_from_date_when_not_declared():
    ref = date(2026, 1, 1)
    near = score_lead({"est_purchase_date": ref + timedelta(days=5)}, ref_date=ref).reasons[0]["puntos"]
    far = score_lead({"est_purchase_date": ref + timedelta(days=200)}, ref_date=ref).reasons[0]["puntos"]
    assert near == 30 and far == 8


def test_stage_implies_quote_and_contact():
    r = score_lead({"stage": "Cotización enviada", "max_stage_index": 4}, ref_date=date(2026, 1, 1))
    pts = {x["factor"]: x["puntos"] for x in r.reasons}
    assert pts["Solicitud de cotización"] == 25 and pts["Solicitud de contacto"] == 10


def test_recommended_action_and_followup():
    lead = {"stage": "Nuevo", "priority": "Alta prioridad", "next_action_date": None}
    assert "hoy" in recommended_action(lead)
    assert suggested_followup(lead, date(2026, 1, 1)) == date(2026, 1, 2)
    assert suggested_followup({"stage": "Perdido"}) is None


def test_safe_div_handles_zero_and_missing():
    assert safe_div(10, 0) is None
    assert safe_div(None, 5) is None
    assert safe_div(10, None) is None
    assert safe_div(float("nan"), 2) is None
    assert safe_div(1, 4, 100) == 25.0


def test_campaign_formulas():
    mtr = campaign_metrics(investment=10000, leads=50, policies=2, commissions=15000, quotes=10,
                           impressions=100000, clicks=2000)
    assert mtr["CPL"] == 200
    assert mtr["CPC"] == 5
    assert mtr["CTR %"] == 2
    assert mtr["CAC"] == 5000
    assert mtr["Conversión %"] == 4
    assert mtr["ROAS comisiones"] == 1.5
    zero = campaign_metrics(investment=5000, leads=0, policies=0, commissions=0, impressions=0, clicks=0)
    assert zero["CPL"] is None and zero["CAC"] is None and zero["CTR %"] is None and zero["Conversión %"] is None


def _leads(rows):
    cols = ["id", "campaign_id", "stage", "max_stage_index", "quote_amount", "commission", "score"]
    return pd.DataFrame(rows, columns=cols)


def test_campaign_table_prefers_manual_values():
    camps = pd.DataFrame([{"id": 1, "name": "C1", "platform": "Google Ads", "investment": 1000.0, "impressions": None,
                           "clicks": None, "leads_manual": None, "quotes_manual": None, "policies_manual": 3,
                           "commissions_manual": None, "data_origin": "Observado"}])
    leads = _leads([[1, 1, "Póliza emitida", 6, 100, 500.0, 90], [2, 1, "Nuevo", 0, None, None, 20]])
    t = campaign_table(camps, leads).iloc[0]
    assert t["Leads"] == 2 and t["Pólizas"] == 3 and t["Origen resultados"] == "Mixto"
    assert t["CPL"] == 500 and t["CTR %"] is None


def test_funnel_is_cumulative():
    leads = _leads([[1, None, "Póliza emitida", 6, 1, 1, 1], [2, None, "Perdido", 3, None, None, 1],
                    [3, None, "Nuevo", 0, None, None, 1]])
    f = funnel_counts(leads).set_index("Etapa")["Leads"]
    assert f["Nuevo"] == 3 and f["Cita agendada"] == 2 and f["Póliza emitida"] == 1
