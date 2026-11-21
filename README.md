# INSURANCE LEADS AI

Plataforma en **Python + Streamlit** para generar, captar, calificar y convertir prospectos de **seguro de vida** y **gastos médicos mayores** en México. El diferenciador es la **adquisición**: detectar demanda, generar campañas, atribuir cada lead a su campaña y anuncio, y optimizar la inversión con datos reales.

## Inicio rápido

```bash
cd insurance_leads_ai
python3.11 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml # edita SETUP_TOKEN
streamlit run app.py
```

1. Abre `http://localhost:8501` → crea el administrador (pide el `SETUP_TOKEN`).
2. **Configuración → Datos demo → Cargar / reiniciar datos demo** para explorar con 1,000 prospectos sintéticos.
3. La landing pública está en `http://localhost:8501/registro`.

Pruebas automatizadas:

```bash
pytest -q
```

## Rutas y acceso

| Ruta | Quién | Contenido |
|---|---|---|
| `/registro` | Público | Landing: beneficios, diagnóstico gratuito, formulario, FAQ, WhatsApp, aviso de privacidad y consentimiento. No lee datos comerciales. |
| `/acceso` | Público | Inicio de sesión del panel. |
| `/dashboard`, `/crm`, … | Usuarios autenticados | Panel privado (12 módulos). Las rutas privadas no existen para visitantes sin sesión. |

## Módulos

| # | Módulo | Qué hace |
|---|---|---|
| 1 | Executive Dashboard | KPIs de adquisición (inversión, impresiones, clics, CTR, CPC, leads, CPL) y comerciales (calificados, citas, cotizaciones, pólizas, conversión, CAC, comisiones); funnel, fuente, campaña, producto, ciudad, evolución semanal, conversión por campaña, distribución de score y rentabilidad por canal. |
| 2 | AI Lead Acquisition | **A** Demand Intelligence · **B** acceso al generador · **C** captura automática (estado de canales, constructor de URL con UTM, sincronización Meta) · **D** optimización con recomendaciones por reglas. |
| 3 | Market Intelligence | Segmentos (independientes, padres, empresarios, emprendedores, directivos, pymes) separando **información verificada (CRM)**, **hipótesis** y **recomendaciones de IA**. |
| 4 | AI Campaign Generator | Genera nombre, segmentación, keywords, titulares, descripciones, propuestas de valor, CTAs, estructura de landing, pruebas A/B, KPIs y ≥3 variantes. Editar, aprobar, guardar y exportar CSV. Nunca publica. |
| 5 | Captación de Leads | Formulario interno, importación CSV con mapeo de columnas, revisión de duplicados y enlace público. |
| 6 | Diagnóstico Inteligente | Cuestionarios de vida y GMM sin datos médicos; resultado orientativo sin precios. |
| 7 | Lead Scoring | Puntuación 0–100 explicada, acción recomendada y fecha de seguimiento. |
| 8 | CRM Comercial | Buscar, filtrar, editar, cambiar etapa, actividades, seguimiento, cotización, póliza, WhatsApp y exportar. |
| 9 | AI Sales Intelligence | 8+ preguntas comerciales respondidas con cálculos; explicación opcional con IA. |
| 10 | Campañas y ROI | Registro/edición, importación de métricas CSV, CPL, CPC, CTR, CAC, conversión y ROAS. |
| 11 | Automatizaciones | Reglas → recordatorios internos con mensaje sugerido y enlace wa.me. |
| 12 | Configuración | Datos demo, negocio, aviso de privacidad versionado, usuarios, integraciones, bitácora. |

## AI Sales & Conversion Engine

Sección **Ventas** del menú. Usa los mismos registros del CRM y reutiliza sus operaciones (cambio de etapa, cotización, póliza, notas, recordatorios).

| Módulo | Qué hace |
|---|---|
| Sales Pipeline | Alertas internas (lead nuevo sin contactar, alta intención, cotización sin respuesta, cita pendiente, sin seguimiento, cotización por vencer, próxima al cierre) y **lista diaria de prioridades** con motivo, prioridad, acción recomendada, fecha y acciones rápidas. Contador en el menú lateral. No envía notificaciones externas. |
| AI Sales Agent | Por prospecto: necesidades, señales de intención, siguientes acciones, mensajes preparados (wa.me), cita y cambio de etapa. Conversación asistida: clasifica el mensaje (pregunta, objeción, intención, cita, baja), sugiere respuesta con fuente, registra todo en el CRM y **transfiere al agente humano**. Base de conocimiento validada (con fuente obligatoria) + glosario general. |
| Cotizaciones | Registro de cotizaciones **oficiales** (aseguradora, producto, prima mensual/anual, suma asegurada, deducible, coaseguro y tope, red hospitalaria, vigencia, observaciones, PDF ≤ 5 MB). Estados, descarga del PDF, comparación de 2–3 alternativas (precio, cobertura, condiciones) y emisión de póliza desde la cotización aceptada. |
| AI Sales Coach | Manejo de 8 objeciones (respuesta consultiva, preguntas, qué evitar, seguimiento), preguntas de descubrimiento, argumentos de valor, seguimiento por etapa, **simulación** evaluada (penaliza presión, promesas, montos sin cotización y sugerir cancelar pólizas) y registro de objeciones. |
| Revenue Intelligence | Prospectos, cotizaciones, pólizas, **prima vendida (no es ingreso)**, comisiones esperadas, cobradas y por cobrar, conversión por producto y campaña, CAC, ROAS sobre comisión esperada y cobrada; quién contrata, oportunidades perdidas, efectividad de acciones comerciales y registro de cobro de comisiones. |

La landing pública incluye la pestaña **«Pregunta a nuestro asistente»**: responde solo con información validada, no da precios ni confirma coberturas, y permite pedir cita o atención personal (si el visitante ya dejó sus datos).

**Reglas de seguridad comercial:** sin una fuente validada el asistente no improvisa y ofrece transferir al agente; la IA (opcional) solo reformula fuentes validadas; las cotizaciones requieren confirmar que son oficiales; nada se envía automáticamente.

### Migraciones

`database/migrations.py` se ejecuta al iniciar la app: crea las tablas nuevas (`quotations`, `objections`, `agent_messages`, `knowledge_items`, `schema_version`) y agrega a `leads` las columnas `commission_paid`, `commission_paid_date` y `accepted_quotation_id` con `ALTER TABLE … ADD COLUMN` (no destructivo, compatible con SQLite y PostgreSQL). Es idempotente y conserva todos los registros existentes (probado en `tests/test_sales_engine.py`).

## Flujo de punta a punta (criterios de aceptación)

1. **AI Campaign Generator** → generar campaña (IA o plantillas) → editar variantes → marcar ≥1 como *Aprobada* → **Aprobar propuesta** (crea la campaña con estado *Aprobada, pendiente de publicar*) → **Exportar CSV** con las URL finales con UTM.
2. Publicar manualmente en Google/Meta/LinkedIn usando esas URL (la app no publica).
3. El prospecto llega a `/registro?utm_source=…&utm_campaign=…&utm_content=…` → se guarda con fuente, campaña, anuncio, UTM, consentimiento y versión del aviso → se califica automáticamente.
4. **CRM** → cambiar etapa → WhatsApp con mensaje precargado → registrar cotización → registrar póliza (prima y comisión).
5. **Campañas y ROI** → capturar inversión/impresiones/clics → CPL, CAC, conversión y ROAS se recalculan; **Acquisition Optimization** y **AI Sales Intelligence** identifican mejores campañas y recomendaciones.

`tests/test_end_to_end.py` automatiza exactamente este flujo.

## Lead Scoring

| Variable | Puntos | Regla |
|---|---|---|
| Intención de contratación | 30 | Declarada (diagnóstico/CRM) o derivada de la fecha estimada: ≤30 días = 30, ≤90 = 18, >90 = 8 |
| Solicitud de cotización | 25 | Solicitó o recibió cotización |
| Presupuesto declarado | 15 | Por rango declarado (2 a 15) |
| Información completa | 10 | Proporcional a 8 campos de contacto/interés |
| Interacción comercial | 10 | 0/4/7/10 por 0/1/2/3+ actividades (incluye diagnóstico) |
| Solicitud de contacto | 10 | Pidió contacto o agendó cita |

80–100 Alta prioridad · 50–79 Media · 0–49 Exploratorio. **No usa datos médicos ni características sensibles.** Se recalcula en cada cambio comercial.

## Integraciones (adaptadores configurables)

Todas se activan solo con credenciales en `st.secrets` (ver `.streamlit/secrets.toml.example`). Sin ellas la app funciona en modo heurístico/manual claramente identificado.

| Integración | Archivo | Sin credenciales |
|---|---|---|
| Anthropic Claude (IA) | `integrations/llm.py` | Plantillas y cálculos determinísticos. A la IA solo se envían métricas agregadas, sin datos personales. |
| Google Ads Keyword Planner | `integrations/google_ads.py` | Palabras clave heurísticas **sin** volúmenes, CPC ni competencia. Requiere `pip install google-ads`. |
| Google Ads Lead Forms | `integrations/google_ads.py` + `webhook_server.py` | Receptor listo; requiere `GOOGLE_LEAD_FORM_KEY`. |
| Meta Lead Ads | `integrations/meta_ads.py` | Sin sincronización. Con credenciales: botón de sincronizar en AI Lead Acquisition → C. |
| Formularios externos | `integrations/webhook_server.py` | Receptor HTTP aparte, firma HMAC-SHA256 (`X-Signature`). |
| Google Trends | `integrations/google_trends.py` | "No disponible": no hay scraping; solo fuente autorizada. |
| WhatsApp Business Platform | `integrations/whatsapp_cloud.py` | Enlaces wa.me con envío manual. El adaptador exige habilitación explícita y consentimiento. |

Receptor de webhooks (servicio separado, detrás de HTTPS):

```bash
WEBHOOK_SECRET=... GOOGLE_LEAD_FORM_KEY=... DATABASE_URL=postgresql+psycopg2://... python -m integrations.webhook_server
```

## Seguridad y privacidad

- Autenticación con contraseñas **PBKDF2-HMAC-SHA256** (390,000 iteraciones, sal aleatoria), bloqueo temporal tras 5 intentos fallidos, roles `admin`/`asesor`.
- Primer administrador protegido por `SETUP_TOKEN`, o definido en secretos (`python -m services.auth "Contraseña"` genera el hash).
- Secretos solo en `st.secrets` / variables de entorno; nunca en la base de datos ni en pantalla.
- Consultas vía ORM SQLAlchemy con parámetros enlazados (prueba de inyección incluida).
- Validación de formularios (teléfono MX normalizado, correo, consentimiento obligatorio).
- **Consentimiento verificable**: tabla `consents` con tipo, texto exacto, versión, SHA-256, canal, usuario y fecha.
- Aviso de privacidad configurable y versionado (no se puede modificar el texto sin cambiar la versión).
- Deduplicación por teléfono normalizado o correo: **marca** posibles duplicados para revisión, nunca borra.
- Eliminación manual por solicitud ARCO con confirmación y bitácora de auditoría.
- Sin scraping de redes sociales ni listas de contacto sin base legítima.

## Despliegue

### Streamlit Community Cloud

1. Sube el repositorio a GitHub (el `.gitignore` excluye `secrets.toml` y la base SQLite).
2. Crea la app con `app.py` como archivo principal y Python 3.11+.
3. En **Secrets** pega el contenido de `secrets.toml.example` con valores reales.

> ⚠️ **SQLite en Streamlit Community Cloud no conserva datos**: el almacenamiento es efímero y se borra al reiniciar o redesplegar. Antes de captar clientes reales configura **PostgreSQL administrado** (Neon, Supabase, AWS RDS, Cloud SQL):
>
> ```toml
> [database]
> url = "postgresql+psycopg2://usuario:clave@host:5432/insurance_leads?sslmode=require"
> ```
>
> Las tablas se crean automáticamente al iniciar. Los modelos no usan tipos exclusivos de SQLite.

### Antes de captar clientes reales

- Sustituye la plantilla del aviso de privacidad por el texto revisado por tu asesor legal y cambia su versión.
- Configura nombre comercial, asesor, WhatsApp y URL pública en **Configuración → Negocio**.
- Usa PostgreSQL y define `SETUP_TOKEN`.
- Verifica las políticas de anuncios de servicios financieros/seguros de cada plataforma.

## Arquitectura

```
insurance_leads_ai/
├── app.py                    # navegación, rutas públicas/privadas, sesión
├── database/                 # modelos, sesión (SQLite/PostgreSQL), repositorio
├── services/                 # lógica de negocio pura (testeable sin UI)
│   ├── demand.py             # Motor A — Demand Intelligence
│   ├── campaign_generator.py # Motor B — generador de campañas
│   ├── capture.py            # Motor C — captura, UTM, CSV, deduplicación
│   ├── optimization.py       # Motor D — recomendaciones
│   ├── market.py  scoring.py  diagnosis.py  metrics.py  insights.py
│   ├── automations.py  whatsapp.py  auth.py  demo.py
│   ├── sales_agent.py  sales_coach.py  quotations.py  # Sales & Conversion Engine
│   ├── pipeline.py  revenue.py  demo_sales.py
├── integrations/             # Claude, Google Ads, Meta, Trends, WhatsApp Cloud, webhooks
├── modules/                  # páginas de Streamlit
├── utils/                    # configuración, validación, tema, componentes, caché
├── data/                     # SQLite local (ignorado por git)
└── tests/                    # pytest + streamlit AppTest
```

## Limitaciones conocidas del MVP

- La sesión vive en la conexión de Streamlit: al recargar la página o abrir una URL privada directamente se vuelve a pedir el inicio de sesión (Streamlit no maneja cookies de sesión de forma nativa).
- Las llamadas reales a Claude, Google Ads, Meta y WhatsApp Cloud requieren credenciales; están implementadas como adaptadores pero no se probaron contra las APIs reales sin esas credenciales.
- Los cambios de esquema futuros requerirán migraciones (Alembic); hoy las tablas se crean con `create_all`.

## Roadmap hacia SaaS

- Multi-tenant (columna `account_id` + políticas de acceso por agencia).
- Migraciones con Alembic.
- Sincronización programada de métricas de Google Ads y Meta.
- Envío por WhatsApp Business Platform con plantillas aprobadas y registro de opt-in.
- Pasarela de suscripción y gestión de planes.
