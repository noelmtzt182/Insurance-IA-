"""Generador de datos sintéticos de demostración.

Todo se marca con ``is_demo=True`` (y las campañas con origen "Demo") y se puede
borrar o reiniciar desde Configuración sin tocar los datos reales. Nombres,
teléfonos (prefijo 00, inválido para marcar) y correos (dominio reservado
example.com) son ficticios. Las cifras NO representan resultados reales.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Campaign, Diagnostic, Lead, Note
from database.repository import delete_demo_data, rescore, slugify
from utils.config import BUDGET_RANGES, IDX_POLICY, IDX_QUOTE, PRODUCT_GMM, PRODUCT_VIDA, SEGMENTS, STAGE_LOST, STAGES, now_mx

FIRST_NAMES = ["María", "José", "Guadalupe", "Juan", "Fernanda", "Luis", "Ana", "Carlos", "Sofía", "Miguel",
               "Valeria", "Jorge", "Daniela", "Ricardo", "Ximena", "Alejandro", "Paola", "Eduardo", "Mariana",
               "Fernando", "Gabriela", "Roberto", "Andrea", "Héctor", "Lucía", "Diego", "Camila", "Arturo",
               "Regina", "Óscar", "Natalia", "Sergio", "Renata", "Raúl", "Elena", "Iván"]
LAST_NAMES = ["Hernández", "García", "Martínez", "López", "González", "Pérez", "Rodríguez", "Sánchez", "Ramírez",
              "Cruz", "Flores", "Gómez", "Morales", "Vázquez", "Reyes", "Jiménez", "Torres", "Díaz", "Gutiérrez",
              "Ruiz", "Mendoza", "Aguilar", "Ortiz", "Moreno", "Castillo", "Romero", "Álvarez", "Chávez"]
CITIES = [("Ciudad de México", 22), ("Guadalajara", 11), ("Monterrey", 11), ("Puebla", 6), ("Querétaro", 6),
          ("Mérida", 5), ("León", 4), ("Tijuana", 4), ("Toluca", 4), ("Cancún", 3), ("San Luis Potosí", 3),
          ("Aguascalientes", 3), ("Chihuahua", 3), ("Hermosillo", 3), ("Morelia", 3), ("Veracruz", 3),
          ("Culiacán", 2), ("Saltillo", 2), ("Oaxaca", 2)]

# nombre, plataforma, fuente, producto, segmento, inversión, CTR base, peso, calidad, nº anuncios
DEMO_CAMPAIGNS = [
    ("DEMO · Protege a tu familia (Vida)", "Facebook", "Facebook Ads", PRODUCT_VIDA, "Padres de familia", 38000, 0.011, 18, 1.0, 3),
    ("DEMO · GMM Familias CDMX", "Facebook", "Facebook Ads", PRODUCT_GMM, "Padres de familia", 42000, 0.009, 15, 0.9, 2),
    ("DEMO · Reels Independientes", "Instagram", "Instagram", PRODUCT_GMM, "Profesionistas independientes", 21000, 0.008, 11, 0.8, 2),
    ("DEMO · Búsqueda GMM", "Google Ads", "Google Ads", PRODUCT_GMM, None, 55000, 0.052, 14, 1.35, 3),
    ("DEMO · Búsqueda Seguro de Vida", "Google Ads", "Google Ads", PRODUCT_VIDA, None, 36000, 0.047, 9, 1.25, 1),
    ("DEMO · TikTok Emprendedores", "TikTok", "TikTok", PRODUCT_GMM, "Emprendedores", 18000, 0.006, 10, 0.55, 2),
    ("DEMO · LinkedIn Directivos", "LinkedIn", "LinkedIn", PRODUCT_VIDA, "Directivos", 30000, 0.005, 6, 1.4, 2),
    ("DEMO · Webinar Pymes", "Evento", "Evento", PRODUCT_GMM, "Pequeñas y medianas empresas", 12000, None, 5, 1.2, 1),
]
ORGANIC_SOURCES = [("Referido", 8, 1.8), ("Sitio web", 6, 1.0), ("WhatsApp", 4, 1.1), ("Otro", 2, 0.7)]
UTM = {"Facebook": ("facebook", "paid_social"), "Instagram": ("instagram", "paid_social"),
       "Google Ads": ("google", "cpc"), "TikTok": ("tiktok", "paid_social"), "LinkedIn": ("linkedin", "paid_social"),
       "Evento": ("evento", "offline")}

STAGE_WEIGHTS = [("Nuevo", 26), ("Contactado", 19), ("Calificado", 14), ("Cita agendada", 10),
                 ("Cotización enviada", 9), ("Negociación", 5), ("Póliza emitida", 7), (STAGE_LOST, 10)]
INSURERS = ["Aseguradora A (demo)", "Aseguradora B (demo)", "Aseguradora C (demo)"]
LOST_REASONS = ["Precio fuera de presupuesto", "No respondió", "Contrató con otra opción", "Pospuso la decisión",
                "No calificó"]
NOTE_SAMPLES = ["Llamada inicial, interesado en conocer opciones.", "Envié información general por WhatsApp.",
                "Pidió que le marque la próxima semana.", "Revisamos necesidades familiares.",
                "Solicitó comparar dos alternativas."]
NEXT_ACTIONS = ["Llamar para seguimiento", "Enviar cotización", "Confirmar cita", "Resolver dudas de cobertura",
                "Enviar documentos para emisión"]


def _weighted(rng: random.Random, items):
    return rng.choices([i[0] for i in items], weights=[i[1] for i in items], k=1)[0]


def generate_demo(s: Session, n: int = 1000, seed: int = 42, replace: bool = True,
                  ref: Optional[datetime] = None) -> dict:
    rng = random.Random(seed)
    ref = ref or now_mx()
    if replace:
        delete_demo_data(s)

    camps = []
    for name, platform, _src, product, segment, inv, ctr, _w, _q, _ads in DEMO_CAMPAIGNS:
        cpm = rng.uniform(35, 90)
        impressions = int(inv / cpm * 1000) if ctr else None
        clicks = int(impressions * ctr) if ctr else None
        c = Campaign(name=name, slug=slugify(name), platform=platform, product=product, segment=segment,
                     location="México", objective="Generar leads", status="Activa (registrada por el usuario)",
                     budget=float(inv), investment=float(inv), impressions=impressions, clicks=clicks,
                     start_date=(ref - timedelta(days=180)).date(), data_origin="Demo", is_demo=True,
                     notes="Campaña sintética para demostración. No representa resultados reales.")
        s.add(c)
        camps.append(c)
    s.flush()

    channels = [(("camp", i), DEMO_CAMPAIGNS[i][7]) for i in range(len(DEMO_CAMPAIGNS))]
    channels += [(("org", i), ORGANIC_SOURCES[i][1]) for i in range(len(ORGANIC_SOURCES))]

    leads = []
    for i in range(n):
        kind, idx = _weighted(rng, channels)
        utm = {}
        ad_id = None
        if kind == "camp":
            spec = DEMO_CAMPAIGNS[idx]
            campaign, source, product, segment, quality = camps[idx], spec[2], spec[3], spec[4], spec[8]
            ad_n = rng.randrange(spec[9])
            ad_id = f"demo-{campaign.slug[7:27]}-{chr(97 + ad_n)}"
            if ad_n == 1 and spec[9] > 1:
                quality *= 0.7  # la variante B atrae leads de menor calidad (para el análisis de anuncios)
            src, med = UTM[spec[1]]
            utm = {"utm_source": src, "utm_medium": med, "utm_campaign": campaign.slug, "utm_content": ad_id}
            segment = segment if rng.random() < 0.75 else rng.choice(SEGMENTS)
        else:
            campaign = None
            source, quality = ORGANIC_SOURCES[idx][0], ORGANIC_SOURCES[idx][2]
            product = rng.choice([PRODUCT_VIDA, PRODUCT_GMM])
            segment = rng.choice(SEGMENTS + [None])

        days_ago = int(abs(rng.gauss(0, 70))) % 180
        created = ref - timedelta(days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))

        stage = _weighted(rng, STAGE_WEIGHTS)
        if rng.random() < (quality - 1.0) * 0.35 and stage in ("Nuevo", "Contactado", STAGE_LOST):
            stage = rng.choice(["Calificado", "Cita agendada", "Cotización enviada", "Póliza emitida"])
        if rng.random() < (1.0 - quality) * 0.5 and stage in ("Cotización enviada", "Negociación", "Póliza emitida"):
            stage = rng.choice(["Contactado", STAGE_LOST])
        if days_ago < 3 and stage in ("Negociación", "Póliza emitida"):
            stage = "Contactado"
        max_idx = rng.choice([0, 1, 1, 2, 2, 3, 4, 4, 5]) if stage == STAGE_LOST else STAGES.index(stage)

        fn, ln1, ln2 = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES), rng.choice(LAST_NAMES)
        email = None if rng.random() < 0.08 else \
            f"{fn.lower()}.{ln1.lower()}{i}@example.com".translate(str.maketrans("áéíóúñü", "aeiounu"))
        budget = rng.choices(BUDGET_RANGES, weights=[10, 14, 24, 26, 18, 8])[0] if rng.random() > 0.05 else None
        low_q = quality < 0.8
        lead = Lead(
            name=f"{fn} {ln1} {ln2}", phone=f"00{rng.randint(10_000_000, 99_999_999)}", email=email,
            city=_weighted(rng, CITIES), segment=segment, product=product, budget_range=budget,
            est_purchase_date=(created + timedelta(days=rng.choice([7, 15, 30, 45, 60, 90, 120, 180]))).date(),
            source=source, campaign_id=campaign.id if campaign else None, ad_id=ad_id,
            purchase_intent=rng.choices(["Sin definir", "Baja", "Media", "Alta"],
                                        weights=[45, 30, 15, 10] if low_q else [45, 15, 22, 18])[0],
            quote_requested=rng.random() < (0.2 if low_q else 0.35) or max_idx >= IDX_QUOTE,
            contact_requested=rng.random() < (0.4 if low_q else 0.55),
            diagnostic_completed=rng.random() < 0.3,
            interactions_count=min(max_idx + rng.randint(0, 2), 8),
            stage=stage, max_stage_index=max_idx,
            lost_reason=rng.choice(LOST_REASONS) if stage == STAGE_LOST else None,
            owner=rng.choice(["asesor1", "asesor2", None]),
            created_at=created, updated_at=created + timedelta(days=min(days_ago, rng.randint(0, 10))),
            consent_contact=True, consent_privacy=True, consent_at=created, privacy_version="demo",
            capture_channel="demo", is_demo=True, **utm,
        )
        if stage not in ("Póliza emitida", STAGE_LOST) and rng.random() < 0.6:
            lead.next_action = rng.choice(NEXT_ACTIONS)
            lead.next_action_date = (ref + timedelta(days=rng.randint(-5, 10))).date()

        base = rng.uniform(600, 2500) if product == PRODUCT_VIDA else rng.uniform(1500, 6000)
        if max_idx >= IDX_QUOTE:
            lead.quote_amount = round(base * 12, -1)
            lead.quote_insurer = rng.choice(INSURERS)
            lead.quote_date = (created + timedelta(days=rng.randint(3, 20))).date()
        if max_idx >= IDX_POLICY and stage == "Póliza emitida":
            lead.policy_number = f"DEMO-{i:05d}"
            lead.policy_premium = lead.quote_amount
            rate = 0.25 if product == PRODUCT_VIDA else 0.12  # tasas sintéticas, solo demo
            lead.commission = round(lead.policy_premium * rate, 2)
            lead.policy_date = (created + timedelta(days=rng.randint(10, 40))).date()
        rescore(lead)
        leads.append(lead)

    s.add_all(leads)
    s.flush()

    extra = []
    for lead in leads:
        if lead.interactions_count and rng.random() < 0.5:
            extra.append(Note(lead_id=lead.id, kind=rng.choice(["Llamada", "WhatsApp", "Nota"]), author="demo",
                              text=rng.choice(NOTE_SAMPLES), created_at=lead.updated_at))
        if lead.diagnostic_completed:
            extra.append(Diagnostic(lead_id=lead.id, product=lead.product, answers=json.dumps({"demo": True}),
                                    need_level=rng.choice(["Alta", "Media", "Baja"]),
                                    intent=lead.purchase_intent if lead.purchase_intent != "Sin definir" else "Baja",
                                    result=json.dumps({"demo": True}), created_at=lead.created_at))
    s.add_all(extra)
    s.flush()
    from services.demo_sales import generate_sales_demo
    sales = generate_sales_demo(s, leads, rng, ref)
    return {"leads": len(leads), "campaigns": len(camps), **sales}
