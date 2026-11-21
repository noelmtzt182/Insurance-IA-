import hashlib
import hmac

import pandas as pd

from database import repository as repo
from integrations.google_ads import parse_lead_form_webhook
from integrations.webhook_server import verify_signature
from services import auth, capture
from services.whatsapp import render_message, wa_link
from tests.conftest import make_lead
from utils.validation import normalize_phone, validate_lead


def test_phone_normalization():
    assert normalize_phone("+52 1 55 1234 5678") == "5512345678"
    assert normalize_phone("52 (55) 1234-5678") == "5512345678"
    assert normalize_phone("12345") is None


def test_validation_requires_consent_and_valid_fields():
    _, errors = validate_lead(make_lead(consent_contact=False, consent_privacy=False, email="malo", phone="1"))
    joined = " ".join(errors)
    assert "teléfono" in joined and "correo" in joined and "autorizar" in joined and "aviso" in joined


def test_dedup_marks_without_deleting(session):
    a, _, dup_a = capture.ingest(session, make_lead(), channel="landing_publica")
    b, _, dup_b = capture.ingest(session, make_lead(email="otro@example.com", phone="+52 55 1234 5678"),
                                 channel="landing_publica")
    assert not dup_a and dup_b
    assert repo.get_lead(session, b).duplicate_of == a
    dups = repo.duplicates_df(session)
    assert list(dups["ID nuevo"]) == [b]
    repo.resolve_duplicate(session, b, "confirmar", "admin")
    assert repo.get_lead(session, b) is not None  # se conserva
    assert b not in set(repo.leads_df(session)["id"])  # pero se excluye de métricas


def test_csv_import_requires_consent(session):
    df = pd.DataFrame([
        {"Nombre": "Pedro Ruiz", "Teléfono": "5511112222", "Correo": "p@example.com", "Producto": "GMM", "consentimiento": "sí"},
        {"Nombre": "Sin Permiso", "Teléfono": "5533334444", "Correo": "s@example.com", "Producto": "vida", "consentimiento": "no"},
    ])
    mapping = capture.auto_mapping(df.columns.tolist())
    assert mapping["phone"] == "Teléfono" and mapping["consent"] == "consentimiento"
    rep = capture.import_dataframe(session, df, mapping, default_product=None, default_source="Otro",
                                   campaign_id=None, consent_attested=False, author="admin")
    assert rep["creados"] == 1 and len(rep["errores"]) == 1
    lead = repo.leads_df(session).iloc[0]
    assert lead["product"] == "Gastos médicos mayores" and lead["capture_channel"] == "importacion_csv"


def test_password_hashing():
    h = auth.hash_password("Segura12345")
    assert h.startswith("pbkdf2_sha256$") and "Segura12345" not in h
    assert auth.verify_password("Segura12345", h)
    assert not auth.verify_password("otra", h)
    assert auth.hash_password("Segura12345") != h  # sal aleatoria


def test_user_creation_and_login(session):
    import pytest
    with pytest.raises(ValueError):
        auth.create_user(session, "admin", "corta")
    auth.create_user(session, "Admin", "Segura12345", "admin")
    assert auth.authenticate(session, "admin", "Segura12345") is not None
    assert auth.authenticate(session, "admin", "mala") is None
    assert auth.authenticate(session, "nadie", "Segura12345") is None


def test_sql_injection_is_inert(session):
    payload = "Robert'); DROP TABLE leads;--"
    lid, errors, _ = capture.ingest(session, make_lead(city=payload), channel="landing_publica")
    assert not errors
    assert repo.get_lead(session, lid).city == payload
    assert len(repo.leads_df(session)) == 1


def test_whatsapp_links_and_templates():
    msg = render_message("Primer contacto", nombre="Laura Gómez", asesor="Ana", empresa="Agencia", producto="seguro de vida")
    assert msg.startswith("Hola Laura,") and "{" not in msg
    assert wa_link("55 1234 5678", "hola mundo") == "https://wa.me/525512345678?text=hola%20mundo"
    assert wa_link("123", "x") is None


def test_webhook_signature_and_google_key():
    body = b'{"name":"x"}'
    sig = hmac.new(b"secreto", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, "secreto")
    assert not verify_signature(body, sig, "otro")
    assert not verify_signature(body, "", "secreto")
    payload = {"google_key": "k1", "lead_id": "L1", "user_column_data": [
        {"column_id": "FULL_NAME", "string_value": "Ana Pérez"}, {"column_id": "PHONE_NUMBER", "string_value": "+525512345678"}]}
    out = parse_lead_form_webhook(payload, expected_key="k1")
    assert out["name"] == "Ana Pérez" and out["external_id"] == "L1"
    import pytest
    with pytest.raises(PermissionError):
        parse_lead_form_webhook(payload, expected_key="otra")
