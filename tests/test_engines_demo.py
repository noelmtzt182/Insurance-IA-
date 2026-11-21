from datetime import timedelta

from database import repository as repo
from services import automations, campaign_generator as cg, demand, diagnosis, market, optimization
from services.demo import generate_demo
from services.metrics import campaign_table
from tests.conftest import make_lead
from utils.config import today_mx


def test_demand_has_no_invented_metrics():
    df = demand.generate_opportunities("Gastos médicos mayores", "Padres de familia", "Monterrey", "Nuevo León",
                                       "Solicitudes de cotización", 10000)
    assert len(df) > 10
    assert df["avg_monthly_searches"].isna().all() and df["low_bid"].isna().all() and df["competition"].isna().all()
    assert set(df["source"]) == {demand.SOURCE_HEURISTIC}
    assert demand.classify_intent("cotizar seguro de vida") == "Alta"
    assert demand.classify_intent("qué es un seguro de vida") == "Baja"


def test_generator_respects_limits_and_compliance():
    for platform, lim in cg.PLATFORM_LIMITS.items():
        content, variants, _ = cg.generate({"product": "Seguro de vida", "audience": "Empresarios", "location": "Guadalajara",
                                            "platform": platform, "budget": 0, "objective": "Generar leads"})
        assert len(variants) >= 3
        for v in variants:
            assert len(v["headline"]) <= lim["headline"]
            assert not cg.compliance_issues(v["headline"] + v["description"])
        for key in ("segmentation", "keywords", "headlines", "descriptions", "value_props", "ctas",
                    "landing_structure", "ab_tests", "kpis"):
            assert content[key]
        assert "No ha sido publicado" in content["status_note"]
    assert cg.compliance_issues("Aprobación garantizado 100% sin exámenes")


def test_diagnosis_never_includes_prices():
    for product, answers in [
        ("Seguro de vida", {"edad": "30 a 39", "dependientes": "2", "ingresos": "$30,000 a $60,000",
                            "obligaciones": ["Crédito hipotecario"], "cobertura_actual": "Ninguna",
                            "presupuesto": "$1,000 a $2,000", "intencion": "Quiero contratar en los próximos 30 días"}),
        ("Gastos médicos mayores", {"edad": "50 a 59", "tipo": "Familiar", "asegurados": 4, "ciudad": "Puebla",
                                    "cobertura_actual": "Solo IMSS / ISSSTE", "presupuesto": "No lo sé aún",
                                    "intencion": "Solo estoy explorando"}),
    ]:
        r = diagnosis.diagnose(product, answers)
        text = " ".join(r["findings"] + r["considerations"] + r["next_steps"])
        assert "$" not in text
        assert r["disclaimer"] and r["need_level"] in ("Alta", "Media", "Baja")


def test_demo_data_is_separated(session):
    from services import capture
    capture.ingest(session, make_lead(), channel="landing_publica")
    res = generate_demo(session, n=1000, seed=1)
    assert res["leads"] == 1000
    counts = repo.count_records(session)
    assert counts["leads_reales"] == 1 and counts["leads_demo"] == 1000
    demo = repo.leads_df(session, "demo")
    assert demo["is_demo"].all() and demo["email"].dropna().str.endswith("@example.com").all()
    assert demo["phone"].str.startswith("00").all()
    assert demo["stage"].nunique() == 8 and demo["priority"].nunique() == 3 and demo["city"].nunique() > 10
    assert len(repo.leads_df(session, "reales")) == 1
    repo.delete_demo_data(session)
    counts = repo.count_records(session)
    assert counts["leads_demo"] == 0 and counts["leads_reales"] == 1


def test_optimization_and_market_on_demo(session):
    generate_demo(session, n=600, seed=3)
    leads = repo.leads_df(session, "demo")
    ct = campaign_table(repo.campaigns_df(session, "demo"), leads)
    recs = optimization.recommendations(ct, leads)
    assert not recs.empty and (recs["Requiere aprobación"] == "Sí").all()
    res = market.analyze(leads, "Seguro de vida", "Padres de familia", None)
    assert res["verified"] and res["hypotheses"] and res["recommendations"]


def test_automations_create_reminders_only_with_consent(session):
    from services import capture
    from database.models import Lead
    a, _, _ = capture.ingest(session, make_lead(), channel="captura_interna", author="u")
    b, _, _ = capture.ingest(session, make_lead(phone="5599998888", email="b@example.com"), channel="captura_interna", author="u")
    for lid in (a, b):
        session.get(Lead, lid).created_at = session.get(Lead, lid).created_at - timedelta(days=2)
    session.get(Lead, b).consent_contact = False
    session.flush()
    leads = repo.leads_df(session)
    rep = automations.run_rules(session, leads, repo.get_settings(session), "u", today=today_mx())
    assert rep["creados"] == 1 and rep["sin_consentimiento"] == 1
    rep2 = automations.run_rules(session, leads, repo.get_settings(session), "u", today=today_mx())
    assert rep2["creados"] == 0 and rep2["ya_pendientes"] == 1
    rem = repo.reminders_df(session)
    assert rem.iloc[0]["Regla"] == "Nuevo sin contacto (24 h)" and "Laura" in rem.iloc[0]["Mensaje"]
