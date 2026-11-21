"""Pruebas de humo de la interfaz con streamlit.testing (AppTest)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent

PAGES = ["dashboard", "acquisition", "market", "campaign_generator", "capture", "diagnosis", "scoring", "crm",
         "sales_ai", "campaigns", "automations", "settings",
         # AI Sales & Conversion Engine
         "sales_agent", "quotations", "pipeline", "coach", "revenue"]


@pytest.fixture(scope="module", autouse=True)
def demo_data():
    from database.session import session_scope
    from services.demo import generate_demo
    with session_scope() as s:
        generate_demo(s, n=300, seed=7)


def test_unauthenticated_sees_login_only():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Panel privado" in text
    assert "Executive Dashboard" not in text


@pytest.mark.parametrize("page", PAGES)
def test_private_page_renders(page):
    script = f"""
import streamlit as st
from utils.theme import inject_css
from modules import {page}
st.session_state.setdefault("user", {{"username": "tester", "role": "admin"}})
st.session_state.setdefault("data_mode", "demo")
inject_css()
{page}.render()
"""
    at = AppTest.from_string(script, default_timeout=90)
    at.run()
    assert not at.exception, at.exception


def test_landing_renders_without_private_data():
    script = """
from modules import landing
landing.render()
"""
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Protege lo que más importa" in text
    assert "DEMO" not in text and "@example.com" not in text
