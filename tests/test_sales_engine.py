"""Pruebas del AI Sales & Conversion Engine (y de que no afecta lo existente)."""
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from database import repository as repo
from database import sales_repository as srepo
from services import capture, pipeline, quotations as qsvc, revenue, sales_agent as agent, sales_coach as coach
from tests.conftest import make_lead

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _lead(s, **over):
    lid, errors, _ = capture.ingest(s, make_lead(**over), channel="captura_interna", author="tester")
    assert not errors
    return lid


def _quote(**over):
    q = {"insurer": "Aseguradora Uno", "product": "Seguro de vida", "plan_name": "Plan A", "premium_amount": 1000.0,
         "premium_period": "Mensual", "sum_insured": 2_000_000.0, "issue_date": date.today(),
         "valid_until": date.today() + timedelta(days=30), "official_confirmed": True}
    q.update(over)
    return q


# ---------------------------------------------------------------------------
# Migraciones
# ---------------------------------------------------------------------------
def test_migration_adds_columns_and_preserves_existing_data(tmp_path):
    from database import session as dbs
    from database.migrations import current_version
    url = f"sqlite:///{tmp_path}/old.db"
    # 1) Base "antigua": se crea y se le quitan las columnas nuevas, como estaba antes de esta versión
    with dbs.session_scope(url) as s:
        lid = _lead(s)
        repo.register_quote(s, lid, 12000, "X", date.today())
    eng = create_engine(url)
    with eng.begin() as c:
        for col in ("commission_paid", "commission_paid_date", "accepted_quotation_id"):
            c.execute(text(f"ALTER TABLE leads DROP COLUMN {col}"))
        c.execute(text("DROP TABLE quotations"))
        c.execute(text("DELETE FROM schema_version"))
    eng.dispose()
    dbs._ENGINES.pop(url).dispose()
    dbs._MAKERS.pop(url)
    # 2) Al iniciar la app se aplica la migración
    engine = dbs.get_engine(url)
    assert current_version(engine) == 1
    with dbs.session_scope(url) as s:
        df = repo.leads_df(s)
        assert len(df) == 1 and df.iloc[0]["quote_amount"] == 12000
        assert "commission_paid" in df.columns and pd.isna(df.iloc[0]["commission_paid"])
        assert srepo.quotations_df(s).empty  # tabla recreada
    # 3) Idempotente
    from database.migrations import run_migrations
    assert run_migrations(engine) == []


# ---------------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------------
def test_quotation_requires_official_confirmation_and_valid_pdf(session):
    lid = _lead(session)
    with pytest.raises(ValueError, match="oficial"):
        srepo.add_quotation(session, lid, _quote(official_confirmed=False))
    with pytest.raises(ValueError, match="PDF"):
        srepo.add_quotation(session, lid, _quote(pdf_filename="x.pdf", pdf_data=b"no es pdf"))
    with pytest.raises(ValueError, match="coaseguro"):
        srepo.add_quotation(session, lid, _quote(coinsurance_pct=150))
    q = srepo.add_quotation(session, lid, _quote(pdf_filename="oficial.pdf", pdf_data=PDF))
    lead = repo.get_lead(session, lid)
    assert lead.stage == "Cotización enviada" and lead.quote_amount == 12000  # 1,000 mensual → 12,000 anual
    assert srepo.get_quotation_pdf(session, q.id) == ("oficial.pdf", PDF)


def test_compare_up_to_three_without_inventing_values(session):
    lid = _lead(session, product="Gastos médicos mayores")
    for ins, prem, ded in (("A", 20000.0, 30000.0), ("B", 24000.0, 15000.0), ("C", 22000.0, None)):
        srepo.add_quotation(session, lid, _quote(insurer=ins, product="Gastos médicos mayores", premium_amount=prem,
                                                 premium_period="Anual", deductible=ded, coinsurance_pct=10.0))
    qs = srepo.quotations_df(session, lead_id=lid)
    res = qsvc.compare(qs)
    assert res["table"].shape[1] == 3
    assert "No indicado" in res["table"].loc["Deducible"].tolist()
    text_ = " ".join(res["findings"])
    assert "#" in text_ and "más al año" in text_ and "deducible más bajo" in text_
    with pytest.raises(ValueError):
        qsvc.compare(qs.head(1))
    srepo.add_quotation(session, lid, _quote(insurer="D", product="Gastos médicos mayores"))
    with pytest.raises(ValueError):
        qsvc.compare(srepo.quotations_df(session, lead_id=lid))


def test_accepting_quote_and_issuing_policy(session):
    lid = _lead(session)
    q = srepo.add_quotation(session, lid, _quote())
    srepo.set_quotation_status(session, q.id, "Enviada")
    srepo.set_quotation_status(session, q.id, "Aceptada")
    assert repo.get_lead(session, lid).stage == "Negociación"
    srepo.issue_policy_from_quotation(session, q.id, "POL-1", 3000, date.today())
    lead = repo.get_lead(session, lid)
    assert lead.stage == "Póliza emitida" and lead.policy_premium == 12000 and lead.accepted_quotation_id == q.id
    with pytest.raises(ValueError):
        srepo.register_commission_payment(session, _lead(session, phone="5500001111", email="z@example.com"), 10, date.today())
    srepo.register_commission_payment(session, lid, 2500, date.today())
    assert repo.get_lead(session, lid).commission_paid == 2500


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def test_pipeline_alerts_cover_required_cases(session):
    from database.models import Lead
    today = date.today()
    new = _lead(session, phone="5510000001", email="a1@example.com")
    session.get(Lead, new).created_at -= timedelta(days=2)
    hot = _lead(session, phone="5510000002", email="a2@example.com", purchase_intent="Alta")
    repo.add_note(session, hot, "Llamada", kind="Llamada")
    repo.change_stage(session, hot, "Contactado")
    quoted = _lead(session, phone="5510000003", email="a3@example.com")
    q = srepo.add_quotation(session, quoted, _quote(valid_until=today + timedelta(days=2)))
    srepo.set_quotation_status(session, q.id, "Enviada")
    session.get(type(q), q.id).sent_at -= timedelta(days=5)
    appt = _lead(session, phone="5510000004", email="a4@example.com")
    srepo.request_appointment(session, appt, today + timedelta(days=1), "Tarde", confirm=True)
    neg = _lead(session, phone="5510000005", email="a5@example.com")
    repo.change_stage(session, neg, "Negociación")
    stale = _lead(session, phone="5510000006", email="a6@example.com")
    repo.change_stage(session, stale, "Calificado")
    session.get(Lead, stale).updated_at -= timedelta(days=10)
    session.flush()

    alerts = pipeline.build_alerts(repo.leads_df(session), srepo.quotations_df(session), srepo.objections_df(session),
                                   today=today)
    kinds = set(alerts["Alerta"])
    assert {"Lead nuevo sin contactar", "Alta intención de compra", "Cotización sin respuesta", "Cita pendiente",
            "Sin seguimiento", "Cotización por vencer", "Oportunidad próxima al cierre"} <= kinds
    for col in ("Prospecto", "Motivo", "Prioridad", "Acción recomendada", "Fecha de seguimiento"):
        assert alerts[col].notna().all()
    daily = pipeline.daily_priorities(alerts)
    assert daily["lead_id"].is_unique and daily.iloc[0]["Prioridad"] == "Alta"


# ---------------------------------------------------------------------------
# Agente y coach
# ---------------------------------------------------------------------------
def test_agent_never_invents_prices_or_coverage():
    for msg in ("¿Cuánto cuesta el seguro?", "¿Cubre maternidad?", "¿Cubre cirugía estética?", "¿Me aceptan con diabetes?"):
        r = agent.respond(msg, "Gastos médicos mayores", [])
        assert "$" not in r.reply and not any(ch.isdigit() for ch in r.reply)
        assert r.handoff_suggested
    r = agent.respond("¿Qué es el deducible?", "Gastos médicos mayores", [])
    assert r.intent == "concepto" and r.sources


def test_agent_uses_validated_knowledge_with_source(session):
    srepo.add_knowledge(session, {"product": "Gastos médicos mayores", "insurer": "Aseg X", "topic": "Maternidad",
                                  "question": "¿El plan cubre maternidad?", "keywords": "maternidad parto embarazo",
                                  "answer": "Respuesta validada.", "source": "Condiciones generales 2026"}, author="u")
    with pytest.raises(ValueError):
        srepo.add_knowledge(session, {"topic": "x", "question": "y", "answer": "z", "source": ""})
    kb = srepo.knowledge_items(session, "Gastos médicos mayores")
    r = agent.respond("¿Cubre maternidad?", "Gastos médicos mayores", kb)
    assert r.reply == "Respuesta validada." and "Condiciones generales 2026" in r.sources[0]
    assert agent.respond("¿Cubre maternidad?", "Seguro de vida", kb).handoff_suggested


def test_agent_detects_intents_and_objections():
    assert agent.classify("Está muy caro")[1] == "Precio"
    assert agent.classify("Ya tengo seguro de gastos médicos")[1] == "Ya tengo seguro"
    assert agent.classify("Quiero hablar con una persona")[0] == "transferencia"
    assert agent.classify("¿Podemos agendar una cita?")[0] == "cita"
    assert agent.classify("Quiero contratar")[0] == "intencion_compra"
    assert agent.respond("Ya no me escriban, por favor", None, []).opt_out


def test_handoff_and_appointment_register_in_crm(session):
    lid = _lead(session)
    srepo.request_handoff(session, lid, "Duda sobre exclusiones")
    rem = repo.reminders_df(session)
    assert (rem["Regla"] == "Transferencia a agente").any()
    srepo.request_appointment(session, lid, date.today() + timedelta(days=3), "Mañana", confirm=False)
    assert (repo.reminders_df(session)["Regla"] == "Solicitud de cita").any()
    assert repo.get_lead(session, lid).stage == "Nuevo"  # no se confirma sin el agente
    srepo.request_appointment(session, lid, date.today() + timedelta(days=3), "Mañana", confirm=True)
    lead = repo.get_lead(session, lid)
    assert lead.stage == "Cita agendada" and lead.next_action_date == date.today() + timedelta(days=3)
    msgs = srepo.agent_messages_df(session, lid)
    assert (msgs["intent"] == "transferencia").any()


def test_coach_rejects_pressure_and_rewards_consultative_replies():
    good = coach.evaluate_reply("Entiendo tu preocupación. ¿Qué es lo que más te gustaría proteger? Podemos revisar "
                                "opciones con calma.", "Precio")
    bad = coach.evaluate_reply("Es tu última oportunidad, firma ya o te vas a arrepentir.", "Lo voy a pensar")
    cancel = coach.evaluate_reply("Entiendo, cancela tu seguro actual y contrata este, ¿te parece?", "Ya tengo seguro")
    safe = coach.evaluate_reply("Entiendo. No se trata de cancelar nada; ¿revisamos tu suma asegurada actual?",
                                "Ya tengo seguro")
    assert good["score"] >= 80 and bad["score"] < 40 and bad["pressure"]
    assert any("cancelar" in f for f in cancel["feedback"])
    assert not any("cancelar una póliza" in f for f in safe["feedback"])
    for play in coach.OBJECTIONS.values():
        assert not coach.evaluate_reply(play["response"])["pressure"]
        assert "$" not in play["response"]


def test_objections_are_logged_with_note(session):
    lid = _lead(session)
    o = srepo.add_objection(session, lid, "Precio", "Está muy caro", "Respuesta consultiva")
    srepo.set_objection_status(session, o.id, "Resuelta")
    df = srepo.objections_df(session, lead_id=lid)
    assert df.iloc[0]["status"] == "Resuelta"
    assert any("Objeción registrada" in t for t in repo.notes_df(session, lid)["Detalle"])


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------
def test_revenue_separates_premium_from_commissions(session):
    a = _lead(session)
    q = srepo.add_quotation(session, a, _quote(premium_amount=30000, premium_period="Anual"))
    srepo.issue_policy_from_quotation(session, q.id, "P-1", 6000, date.today())
    srepo.register_commission_payment(session, a, 4000, date.today())
    _lead(session, phone="5599990000", email="b@example.com")
    k = revenue.kpis(repo.leads_df(session), repo.campaigns_df(session), srepo.quotations_df(session))
    assert k["premium_sold"] == 30000
    assert k["commission_expected"] == 6000 and k["commission_collected"] == 4000 and k["commission_pending"] == 2000
    assert k["policies"] == 1 and k["conversion"] == 50.0
    assert k["cac"] is None and k["roas_expected"] is None  # sin inversión registrada no se inventa


def test_demo_sales_data_is_separated_and_removable(session):
    from services.demo import generate_demo
    _lead(session)
    res = generate_demo(session, n=300, seed=5)
    assert res["quotations"] > 0 and res["objections"] > 0
    assert srepo.quotations_df(session, "reales").empty
    assert all("(demo)" in i for i in srepo.quotations_df(session, "demo")["insurer"])
    repo.delete_demo_data(session)
    assert srepo.quotations_df(session, "todos").empty and srepo.objections_df(session, "todos").empty
    assert len(repo.leads_df(session, "reales")) == 1


# ---------------------------------------------------------------------------
# Criterios de aceptación 1–10
# ---------------------------------------------------------------------------
def test_acceptance_criteria_sales_flow(session):
    s = session
    lid = _lead(s)                                                     # 1. prospecto existente
    hist = srepo.lead_history(s, lid)                                  # 2. historial comercial
    assert hist["lead"]["id"] == lid and len(hist["notes"]) >= 1
    acts = agent.next_actions(hist["lead"], hist["quotations"], hist["objections"])   # 3. recomendaciones
    assert acts and all("Acción" in a for a in acts)
    q1 = srepo.add_quotation(s, lid, _quote(insurer="A", premium_amount=1000))        # 4. cotización oficial
    srepo.add_quotation(s, lid, _quote(insurer="B", premium_amount=1100))
    cmp_ = qsvc.compare(srepo.quotations_df(s, lead_id=lid))                          # 5. comparar
    assert len(cmp_["labels"]) == 2
    srepo.add_objection(s, lid, "Precio", "Está caro")                               # 6. objeción
    repo.set_next_action(s, lid, "Revisar comparativo", date.today() + timedelta(days=2))   # 7. seguimiento
    before = revenue.kpis(repo.leads_df(s), repo.campaigns_df(s), srepo.quotations_df(s))
    repo.change_stage(s, lid, "Negociación")                                          # 8. estado comercial
    srepo.issue_policy_from_quotation(s, q1.id, "POL-ACC", 2400, date.today())        # 9. póliza
    after = revenue.kpis(repo.leads_df(s), repo.campaigns_df(s), srepo.quotations_df(s))   # 10. indicadores
    assert before["policies"] == 0 and after["policies"] == 1
    assert after["premium_sold"] == 12000 and after["commission_expected"] == 2400
    alerts = pipeline.build_alerts(repo.leads_df(s), srepo.quotations_df(s), srepo.objections_df(s))
    assert lid not in set(alerts["lead_id"])  # cerrado: sale del pipeline
