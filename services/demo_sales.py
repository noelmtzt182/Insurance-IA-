"""Datos demo del Sales & Conversion Engine (cotizaciones, objeciones, cobros).

Se generan solo para leads demo (is_demo=True). Las aseguradoras y cifras son
sintéticas y se identifican como «(demo)»: no son cotizaciones reales.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database.models import Lead, Objection, Quotation
from services.sales_coach import OBJECTION_CATEGORIES
from utils.config import IDX_CONTACTED, IDX_QUOTE, PRODUCT_GMM, now_mx

INSURERS = ["Aseguradora A (demo)", "Aseguradora B (demo)", "Aseguradora C (demo)"]
NETWORKS = ["Red amplia (demo)", "Red media (demo)", "Red básica (demo)"]


def generate_sales_demo(s: Session, leads: list[Lead], rng: random.Random, ref: datetime | None = None) -> dict:
    ref = ref or now_mx()
    n_q = n_o = 0
    for lead in leads:
        if lead.max_stage_index >= IDX_CONTACTED:
            lead.last_contact_at = lead.created_at + timedelta(days=rng.randint(0, 3))
        if lead.stage == "Póliza emitida" and lead.commission and rng.random() < 0.7:
            lead.commission_paid = lead.commission
            lead.commission_paid_date = (lead.policy_date or ref.date()) + timedelta(days=rng.randint(15, 45))
        if lead.max_stage_index >= IDX_QUOTE and lead.quote_amount:
            k = rng.choice([1, 2, 2, 3])
            for j in range(k):
                annual = lead.quote_amount * (1 + rng.uniform(-0.15, 0.2)) if j else lead.quote_amount
                monthly = rng.random() < 0.5
                gmm = lead.product == PRODUCT_GMM
                q = Quotation(
                    lead_id=lead.id, created_by="demo", insurer=[i for i in INSURERS if i != (lead.quote_insurer or INSURERS[0])][j - 1] if j else (lead.quote_insurer or INSURERS[0]),
                    product=lead.product, plan_name=f"Plan {'Integral' if gmm else 'Protección'} {j + 1} (demo)",
                    premium_amount=round(annual / 12, 2) if monthly else round(annual, 2),
                    premium_period="Mensual" if monthly else "Anual",
                    sum_insured=float(rng.choice([1_000_000, 2_000_000, 3_000_000, 5_000_000])),
                    deductible=float(rng.choice([15_000, 25_000, 35_000, 50_000])) if gmm else None,
                    coinsurance_pct=float(rng.choice([5, 10, 15])) if gmm else None,
                    coinsurance_cap=float(rng.choice([40_000, 60_000, 80_000])) if gmm else None,
                    hospital_network=rng.choice(NETWORKS) if gmm else None,
                    issue_date=lead.quote_date, valid_until=(lead.quote_date or ref.date()) + timedelta(days=30),
                    observations="Cotización sintética para demostración.", official_confirmed=True,
                    created_at=datetime.combine(lead.quote_date or ref.date(), datetime.min.time()),
                )
                if lead.stage == "Póliza emitida" and j == 0:
                    q.status = "Aceptada"
                elif lead.stage == "Perdido":
                    q.status = rng.choice(["Rechazada", "Vencida"])
                else:
                    q.status = rng.choice(["Enviada", "Enviada", "Registrada"])
                    if q.status == "Enviada":
                        q.sent_at = q.created_at + timedelta(days=1)
                s.add(q)
                n_q += 1
        if lead.max_stage_index >= IDX_CONTACTED and rng.random() < 0.25:
            cat = rng.choice(OBJECTION_CATEGORIES)
            status = "Resuelta" if lead.stage == "Póliza emitida" else rng.choice(["Pendiente", "Resuelta", "No resuelta"])
            s.add(Objection(lead_id=lead.id, category=cat, status=status, source="demo", author="demo",
                            created_at=lead.updated_at))
            n_o += 1
    s.flush()
    return {"quotations": n_q, "objections": n_o}
