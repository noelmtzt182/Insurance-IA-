"""Migraciones de esquema que CONSERVAN los datos existentes.

Estrategia (compatible con SQLite y PostgreSQL):
  * Las tablas nuevas las crea ``Base.metadata.create_all`` (no toca tablas existentes).
  * Las columnas nuevas en tablas existentes se agregan con ``ALTER TABLE … ADD COLUMN``
    (operación no destructiva: los registros conservan todos sus valores; la columna nueva queda NULL).
  * La tabla ``schema_version`` registra qué migraciones ya se aplicaron; cada migración es
    idempotente (solo agrega columnas que falten).

Para agregar una migración: añade una entrada al final de MIGRATIONS con un número mayor.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine

from database.models import Base, SchemaVersion

# (versión, descripción, [(tabla, columna)])  — el tipo se toma del modelo ORM
MIGRATIONS: list[tuple[int, str, list[tuple[str, str]]]] = [
    (1, "Sales & Conversion Engine: comisiones cobradas y cotización aceptada",
     [("leads", "commission_paid"), ("leads", "commission_paid_date"), ("leads", "accepted_quotation_id")]),
]


def current_version(engine: Engine) -> int:
    with engine.connect() as conn:
        versions = conn.execute(select(SchemaVersion.version)).scalars().all()
    return max(versions) if versions else 0


def run_migrations(engine: Engine) -> list[int]:
    """Aplica las migraciones pendientes. Devuelve las versiones aplicadas en esta ejecución."""
    applied: list[int] = []
    done = set()
    with engine.connect() as conn:
        done = set(conn.execute(select(SchemaVersion.version)).scalars().all())
    for version, description, columns in MIGRATIONS:
        if version in done:
            continue
        insp = inspect(engine)
        with engine.begin() as conn:
            for table, column in columns:
                existing = {c["name"] for c in insp.get_columns(table)}
                if column in existing:
                    continue
                col = Base.metadata.tables[table].c[column]
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
            conn.execute(SchemaVersion.__table__.insert().values(version=version, description=description))
        applied.append(version)
    return applied
