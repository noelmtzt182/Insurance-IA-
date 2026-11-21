"""Utilidades de fechas para Series de pandas (compatibles con pandas 2 y 3)."""
from __future__ import annotations

import pandas as pd


def day(series: pd.Series) -> pd.Series:
    """Convierte fechas/fechas-hora a Timestamp a medianoche (NaT si falta)."""
    return pd.to_datetime(series, errors="coerce").dt.normalize()
