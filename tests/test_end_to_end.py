"""Flujo completo: campaña → anuncios → captación → score → CRM → cotización → póliza → métricas."""
from datetime import date

import pandas as pd
import pytest

from database import repository as repo
from services import campaign_generator as cg
from services import capture, insights, metrics, optimization
from tests.conftest import make_lead


def test_full_acquisition_to_policy_flow(session):
    s = session
    # 1-3. Crear campaña con plantillas, aprobar variantes y guardar
    inputs = {"product": "Seguro de vida", "audience": "Padres de familia", "location": "Monterrey",
              "platform": "Google Ads", "budget": 15000, "objective": "Solicitudes de cotización"}
    content, variants, by = cg.generate(inputs, use_ai=False)
    assert by == "Plantillas" and len(variants) >= 3
    plan = repo.save_plan(s, inputs, content, variants, by)
    with pytest.raises(ValueError):
        repo.approve_plan(s, plan.id, "admin")  # sin variantes aprobadas
    v = plan.variants[0]
    repo.update_variant(s, v.id, v.headline, v.description, v.cta, "Aprobada")
    camp = repo.approve_plan(s, plan.id, "admin")
    assert camp.status.startswith("Aprobada") and "publicar" in camp.status
    repo.update_campaign(s, camp.id, {"investment": 3000.0, "impressions": 20000, "clicks": 400})

    # 4-7. Captar lead desde la landing con UTM → atribución y score
    raw = make_lead() | capture.attribution_from_params(
        {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": camp.slug, "utm_content": v.code,
         "gclid": "abc"})
    raw["source"] = None
    lead_id, errors, dup = capture.ingest(s, raw, channel="landing_publica")
    assert errors == [] and not dup
    lead = repo.get_lead(s, lead_id)
    assert lead.campaign_id == camp.id and lead.ad_id == v.code and lead.source == "Google Ads"
    assert lead.privacy_version == "v1" and lead.score > 0 and len(lead.consents) == 2

    # 8. Cambiar etapa
    repo.change_stage(s, lead_id, "Contactado", author="admin")
    repo.add_note(s, lead_id, "Llamada inicial", kind="Llamada", author="admin")
    # 10. Cotización (avanza a "Cotización enviada")
    repo.register_quote(s, lead_id, 18000, "Aseguradora X", date.today(), author="admin")
    assert repo.get_lead(s, lead_id).stage == "Cotización enviada"
    # 11. Póliza
    repo.register_policy(s, lead_id, "POL-1", 18000, 4500, date.today(), author="admin")
    lead = repo.get_lead(s, lead_id)
    assert lead.stage == "Póliza emitida" and lead.max_stage_index == 6

    # 12-14. Indicadores
    leads = repo.leads_df(s, "reales")
    camps = repo.campaigns_df(s, "reales")
    ct = metrics.campaign_table(camps, leads)
    row = ct.iloc[0]
    assert row["Leads"] == 1 and row["Pólizas"] == 1 and row["Comisiones"] == 4500
    assert row["CPL"] == 3000 and row["CAC"] == 3000 and row["CTR %"] == 2 and row["CPC"] == 7.5
    assert row["ROAS comisiones"] == 1.5
    k = metrics.lead_kpis(leads)
    assert k["policies"] == 1 and k["conversion"] == 100.0

    # 15. Recomendaciones e inteligencia comercial
    assert isinstance(optimization.recommendations(ct, leads), pd.DataFrame)
    for key in insights.QUESTIONS:
        res = insights.run(key, leads, camps)
        assert res.answer


def test_notes_and_history_persist(session):
    lid, _, _ = capture.ingest(session, make_lead(), channel="captura_interna", author="u")
    repo.set_next_action(session, lid, "Llamar", date.today(), author="u")
    notes = repo.notes_df(session, lid)
    assert any("Seguimiento agendado" in t for t in notes["Detalle"])
