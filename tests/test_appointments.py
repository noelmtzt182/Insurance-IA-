"""Pruebas del flujo enfocado en citas: landing → solicitud de cita → alerta → costo por cita."""
from datetime import date, timedelta

import pandas as pd

from database import repository as repo
from database import sales_repository as srepo
from services import campaign_generator as cg
from services import capture, metrics, pipeline, revenue
from tests.conftest import make_lead
from utils.config import APPOINTMENT_SLOTS


def test_landing_appointment_request_creates_alert_first(session):
    lid, errors, _ = capture.ingest(session, make_lead(), channel="landing_publica")
    assert not errors
    wanted = date.today() + timedelta(days=2)
    srepo.request_appointment(session, lid, wanted, APPOINTMENT_SLOTS[2], author="prospecto", channel="landing",
                              confirm=False)
    lead = repo.get_lead(session, lid)
    assert lead.stage == "Nuevo" and lead.next_action_date == wanted and lead.contact_requested
    assert (repo.reminders_df(session)["Regla"] == "Solicitud de cita").any()

    alerts = pipeline.build_alerts(repo.leads_df(session), srepo.quotations_df(session),
                                   srepo.objections_df(session))
    appt = alerts[alerts["Alerta"] == "Solicitud de cita por confirmar"]
    assert len(appt) == 1 and appt.iloc[0]["Prioridad"] == "Alta"
    assert APPOINTMENT_SLOTS[2] in appt.iloc[0]["Cita solicitada"]
    # En la lista diaria, la solicitud de cita aparece antes que «Lead nuevo sin contactar»
    daily = pipeline.daily_priorities(alerts)
    assert daily.iloc[0]["Alerta"] == "Solicitud de cita por confirmar"

    # Al confirmar la cita (etapa «Cita agendada») la alerta de solicitud desaparece
    repo.change_stage(session, lid, "Cita agendada")
    alerts = pipeline.build_alerts(repo.leads_df(session), srepo.quotations_df(session), srepo.objections_df(session))
    assert "Solicitud de cita por confirmar" not in set(alerts["Alerta"])


def test_requested_slot_parsing():
    assert pipeline.requested_slot("Cita con el agente (Tarde (15 a 19 h))") == "Tarde (15 a 19 h)"
    assert pipeline.requested_slot("Llamar para seguimiento") is None
    assert pipeline.requested_slot(None) is None


def test_cost_per_appointment(session):
    camp = repo.create_campaign(session, {"name": "Citas Monterrey", "platform": "Facebook", "investment": 1200.0})
    for i in range(3):
        lid, _, _ = capture.ingest(session, make_lead(phone=f"55100000{i:02d}", email=f"c{i}@example.com",
                                                      campaign_id=camp.id), channel="landing_publica")
        if i < 2:
            repo.change_stage(session, lid, "Cita agendada")
    leads = repo.leads_df(session)
    ct = metrics.campaign_table(repo.campaigns_df(session), leads)
    assert ct.iloc[0]["Citas"] == 2 and ct.iloc[0]["Costo por cita"] == 600
    acq = metrics.overall_acquisition(ct)
    assert acq["appointments"] == 2 and acq["cost_per_appt"] == 600
    k = revenue.kpis(leads, repo.campaigns_df(session), srepo.quotations_df(session))
    assert k["appointments"] == 2 and k["cost_per_appointment"] == 600 and round(k["appointment_rate"], 1) == 66.7


def test_cost_per_appointment_without_appointments_is_none():
    camps = pd.DataFrame([{"id": 1, "name": "C", "platform": "Facebook", "investment": 500.0, "impressions": None,
                           "clicks": None, "leads_manual": None, "quotes_manual": None, "policies_manual": None,
                           "commissions_manual": None, "data_origin": "Observado"}])
    leads = pd.DataFrame(columns=["id", "campaign_id", "stage", "max_stage_index", "quote_amount", "commission",
                                  "score"])
    ct = metrics.campaign_table(camps, leads)
    assert ct.iloc[0]["Costo por cita"] is None or pd.isna(ct.iloc[0]["Costo por cita"])


def test_generator_appointment_objective_uses_appointment_hooks():
    for platform, lim in cg.PLATFORM_LIMITS.items():
        _, variants, _ = cg.generate({"product": "Seguro de vida", "audience": "Padres de familia",
                                      "location": "Monterrey", "platform": platform, "budget": 5000,
                                      "objective": "Agendar citas"})
        assert len(variants) >= 3
        text = " ".join(v["headline"] + " " + v["description"] for v in variants).lower()
        assert "asesor" in text and "agenda" in text
        for v in variants:
            assert len(v["headline"]) <= lim["headline"]
            assert not cg.compliance_issues(v["headline"] + v["description"])
