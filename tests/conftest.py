import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Base de datos temporal para toda la sesión de pruebas (nunca toca data/)
_TMP = tempfile.mkdtemp(prefix="ila_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"


@pytest.fixture()
def db_url(tmp_path):
    """URL de una base SQLite aislada por prueba."""
    return f"sqlite:///{tmp_path}/t.db"


@pytest.fixture()
def session(db_url):
    from database.session import session_scope
    with session_scope(db_url) as s:
        yield s


def make_lead(**over):
    from datetime import date, timedelta
    data = {
        "name": "Laura Prueba Gómez", "phone": "55 1234 5678", "email": "laura@example.com", "city": "Monterrey",
        "product": "Seguro de vida", "budget_range": "$1,000 a $2,000",
        "est_purchase_date": date.today() + timedelta(days=20), "source": "Google Ads",
        "quote_requested": True, "contact_requested": True, "consent_contact": True, "consent_privacy": True,
    }
    data.update(over)
    return data
