# Better Crafter Orders 2.0

FastAPI/React order automation app for Better Crafter, with Gmail parsing and
OneDrive sandbox document workflows. The older Firebase/Stephen report code is
kept as legacy/reference material while 2.0 stabilizes.

## Current Stabilization Status

The active source of truth is the Better Crafter Orders 2.0 codebase in this
repository. The older Firebase/static HTML repo is reference/quarantine only and
must not be used as the active application during stabilization.

No deploy has happened as part of this stabilization work. No production
OneDrive writes have been intentionally performed during stabilization. Real
secrets belong only in local `.env` files or a secret manager, never in source
code, commits, chat, screenshots, or logs.

Edit `.env` through VS Code Explorer or another normal editor. If using VS Code
from WSL, run `code .env`. Do not print `.env`; do not use terminal editors like
`nano`, `vim`, `vi`, or `emacs` unless you explicitly choose to.

### Completed stabilization PRs

PR #1 - remove hardcoded Microsoft OneDrive credentials

- Moved Microsoft / OneDrive config out of tracked source and into env-driven configuration.
- Added `.env.example` placeholders.
- Guarded unsafe deploy script behavior.
- Commit: `715638e`

PR #2 - protect write endpoints with admin API key

- Protected dangerous write/delete/external-state routes with `ADMIN_API_KEY` / `X-Admin-API-Key`.
- Kept `/api/health` public.
- Protected:
  - `POST /api/append-to-onedrive`
  - `POST /api/gmail-webhook`
  - `POST /api/clear-onedrive-rows`
  - `POST /api/daily-update`
  - `POST /api/renew-gmail-watch`
- Commit: `c64c339`

PR #3 - normalize parser results in API order paths

- Normalized parser outputs from `None`, legacy `dict`, empty list, and `list[dict]`.
- Preserved multi-item parser results.
- Validates rows individually.
- Skips invalid sibling rows without discarding valid rows.
- Commit: `80247a1`

PR #4 - frontend endpoint alignment

- Preview/fetch uses implemented read endpoint `/api/orders-stream`.
- Removed active frontend calls to missing `/api/generate-report` and `/api/download-report/...`.
- OneDrive write action is disabled/protected in the UI during stabilization.
- No frontend admin-key handling.
- Branch: `stabilize/frontend-endpoint-alignment`

## Local Sanity Check

Open `.env` using VS Code Explorer or:

```bash
code .env
```

Do not print `.env`. Do not paste secrets into chat. Do not call protected
write/delete/scheduler endpoints during sanity checks. `/api/health` is the safe
backend check. Preview/fetch may read Gmail if credentials are configured, so use
it only when you intentionally want a local Gmail read.

Backend:

```bash
cd /mnt/c/dev/better-crafter-orders-2.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

Safe backend health check from another terminal:

```bash
curl http://127.0.0.1:8000/api/health
```

Frontend:

```bash
cd /mnt/c/dev/better-crafter-orders-2.0/frontend
npm install
npm run build
npm run dev -- --host 127.0.0.1
```

Safe config diagnostics:

```bash
cd /mnt/c/dev/better-crafter-orders-2.0
.venv/bin/python scripts/check_config.py
```

The diagnostic reports only whether each expected key is present or missing. It
must never include raw values, masked values, lengths, prefixes, suffixes, or
hashes. Do not paste diagnostic output anywhere if it contains anything
unexpected.

Admin-protected local API diagnostic:

```bash
curl -H "X-Admin-API-Key: <local-admin-key>" http://127.0.0.1:8000/api/config-diagnostics
```

## 2.0 Environment Variables

`/api/config-status` and `/api/config-diagnostics` report presence/status only.
They never return raw values, masked values, lengths, prefixes, suffixes, or
hashes. Placeholder-looking values such as `placeholder_*` are reported as
missing or `status: "placeholder"`; they are not treated as configured.

| Group | Variables | Required for local 2.0? | Notes |
| --- | --- | --- | --- |
| Required for local admin app | `GCP_PROJECT`, `ALLOWED_ORIGINS`, `ADMIN_API_KEY` | Yes | `ADMIN_API_KEY` gates protected admin routes. Keep it local/testing only unless a production auth layer replaces it. |
| Required for Gmail fetch | `GMAIL_ACCOUNT`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | Yes, when fetching Gmail | Used by `/api/orders-stream`, `/api/batch-orders`, Gmail webhook handling, and Gmail watch renewal. |
| Required for OneDrive sandbox | `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_REFRESH_TOKEN`, `ONEDRIVE_TEST_DRIVE_ID`, `ONEDRIVE_TEST_FILE_ID`, `ONEDRIVE_SANDBOX_WRITE_ENABLED` | Yes, when creating/testing sandbox docs | Sandbox flows use `ONEDRIVE_TEST_*` IDs and refuse to run if they match production IDs. |
| Optional Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` | No | Gemini billing/API access has been confirmed. `GEMINI_MODEL` defaults to `gemini-2.5-flash` when unset. |
| Production-later | `ONEDRIVE_DRIVE_ID`, `ONEDRIVE_FILE_ID`, `MS_CLIENT_SECRET`, `GOOGLE_CREDENTIALS_JSON` | No | Do not require these for local admin, Gmail fetch, supplier CRUD, or sandbox document creation. |
| Legacy/reference only | `STORAGE_BUCKET`, `FIRESTORE_COLLECTION`, `SEARCH_HOURS_BACK`, `REPORT_PREFIX`, `TEMPLATE_PATH` | No | Used by the old Firebase/Stephen report path (`functions/main.py`, `WordReportGenerator`, and legacy scripts). They are not required by `api.py`, the React app, supplier CRUD, or sandbox supplier doc creation. |

The current supplier document creation path builds a Word table dynamically from
the supplier config: the standard base columns plus each
`supplier.custom_fields[].field_name`. It does not read
`templates/stephen_template.docx`, `functions/templates/stephen_template.docx`,
`TEMPLATE_PATH`, or `WordReportGenerator`.

## Dry-run batch order preview

`POST /api/batch-orders` provides an admin-protected dry-run preview for
supplier order candidates. It reads matching Gmail messages and parses candidate
orders, but it does not write to OneDrive, delete OneDrive rows, write to
Firestore, mark emails as processed, or mutate external state. This endpoint is
dry-run only during stabilization; requests with `dry_run: false` are rejected.

The endpoint requires `X-Admin-API-Key`. Do not put admin keys in the request
body, frontend code, browser storage, logs, or documentation.

Supported supplier IDs in this branch are `stephen` and `steven`; both map to
the current Stephen supplier parser/email path. Use narrow date ranges for local
checks because this endpoint can perform a read-only Gmail fetch.

Example local request:

```bash
curl -X POST http://127.0.0.1:8000/api/batch-orders \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: <local-admin-key>" \
  -d '{"supplier_ids":["stephen"],"start_date":"2026-05-01","end_date":"2026-05-02","dry_run":true,"include_orders":false}'
```

Request body:

```json
{
  "supplier_ids": ["stephen"],
  "start_date": "2026-05-01",
  "end_date": "2026-05-02",
  "dry_run": true,
  "include_orders": false,
  "max_preview_rows": 100
}
```

`dry_run` defaults to `true`. `supplier_ids`, `start_date`, and `end_date` are
required. Dates must use `YYYY-MM-DD`. If `include_orders` is true, preview rows
are sanitized and capped at 100 rows. Email bodies, raw PDF text, headers,
tokens, credentials, and admin keys are never included in the response.

### Local frontend dry-run preview

The Vite frontend includes a local-only Batch Dry-Run Preview flow for
`POST /api/batch-orders`. It is intended for narrow, deliberate local checks
after the backend is running on `127.0.0.1:8000`.

Local usage:

```bash
cd /mnt/c/dev/better-crafter-orders-2.0
source .venv/bin/activate
uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd /mnt/c/dev/better-crafter-orders-2.0/frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open the local Vite URL, choose `Stephen` or `Steven`, select a narrow start and
end date, and enter the local admin key manually in the field labeled
`Local admin key for dry-run preview`. Do not print `.env` to retrieve the key;
open it in a normal editor such as VS Code if you need to read it.

The key is kept only in React component state for the current page session. It
is not saved to `localStorage`, `sessionStorage`, source code, query params, or
logs. The frontend uses it only as the `X-Admin-API-Key` request header.

The frontend always sends `dry_run: true`. It can optionally request sanitized
preview rows with a local cap from 1 to 100. This UI flow does not call OneDrive
write/delete endpoints, does not mark emails as processed, and does not write to
Firestore. Avoid broad date ranges because the dry-run can still perform a
read-only Gmail fetch when local credentials are configured.

## OneDrive Sandbox Testing

The local OneDrive sandbox harness is the first allowed path for OneDrive
testing during stabilization. It must use a cloned/test Word document only. Do
not use the production `ONEDRIVE_FILE_ID` or `ONEDRIVE_DRIVE_ID` as sandbox test
IDs.

Required test-only variables:

- `ONEDRIVE_TEST_DRIVE_ID`
- `ONEDRIVE_TEST_FILE_ID`
- `ONEDRIVE_SANDBOX_WRITE_ENABLED`

The harness also needs the existing Microsoft auth variables used by the
OneDrive client, such as `MS_CLIENT_ID`, `MS_TENANT_ID`, and
`MS_REFRESH_TOKEN`. Keep real values only in local `.env` or a secret manager.
Do not paste `.env`, token values, client secrets, drive IDs, or file IDs into
chat, screenshots, commits, or logs.

Config readiness check, no Microsoft Graph call:

```bash
.venv/bin/python scripts/test_onedrive_sandbox.py --check-config
```

Read-only sandbox metadata check, Microsoft Graph metadata read only:

```bash
.venv/bin/python scripts/test_onedrive_sandbox.py --check-metadata
```

Sandbox write test, cloned/test file only:

```bash
ONEDRIVE_SANDBOX_WRITE_ENABLED=true .venv/bin/python scripts/test_onedrive_sandbox.py --write-test-row
```

The write test refuses to run unless the explicit write flag is true, the test
IDs are present, the test IDs differ from production IDs, and the file name
contains `TEST`, `SANDBOX`, `COPY`, or `CLONE`. The current app format is a
`.docx` Word document, so the write test appends one row to the first table of
the cloned/test document. The row is marked:

`SANDBOX TEST - SAFE TO DELETE`

The sandbox harness does not read Gmail, does not call app production endpoints,
does not delete OneDrive content, and must not be used against production
OneDrive files.

## Estructura

- `api.py`: FastAPI backend for the active 2.0 app
- `frontend/`: React admin app for local 2.0 workflows
- `functions/main.py`: legacy Firebase scheduled function/reference path
- `functions/gmail_client.py`: cliente Gmail API con OAuth2 + retries
- `functions/email_parser.py`: parser extensible con registry por proveedor
- `functions/word_generator.py`: active OneDrive table helpers plus legacy report generator
- `functions/firestore_client.py`: legacy Firestore dedupe helper
- `functions/config.py`: shared Gmail config plus optional legacy/reference config
- `templates/stephen_template.docx`: legacy/reference Stephen Word template
- `scripts/create_template.py`: script para crear la plantilla legacy/reference
- `setup_oauth.py`: script local para obtener refresh token

## Requisitos

- Python 3.11
- Firebase CLI
- Proyecto Firebase con Firestore y Storage habilitados
- API de Gmail habilitada en Google Cloud

## Instalación local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración local segura

Los valores reales de Microsoft / OneDrive pertenecen solo en un `.env` local
sin commitear o en un secret manager. `.env` nunca debe commitearse.
`.env.example` debe contener placeholders solamente.

Para pruebas locales, copia `.env.example` a `.env` y coloca allí los valores
temporales existentes. No pegues secretos, tokens, client secrets, IDs reales de
OneDrive, ni valores de configuración sensible en chat, documentación, commits,
capturas de pantalla o logs.

`functions/config.py` no debe contener credenciales reales. Las credenciales de
Gmail, Microsoft / OneDrive, Gemini y claves admin deben venir de variables de
entorno locales o del secret manager del entorno donde corra la app. Los errores
de configuración deben nombrar la variable faltante sin imprimir su valor.

## Protección temporal de endpoints de escritura

Los endpoints que escriben en OneDrive, borran filas, renuevan el watch de Gmail
o procesan webhooks requieren el header `X-Admin-API-Key`. Para pruebas locales,
define `ADMIN_API_KEY` en `.env`. Nunca commitees claves admin reales; `.env.example`
debe conservar solo placeholders.

`/api/health` permanece público. Esta clave admin es una protección temporal de
toma de control/estabilización, no la autenticación final de producción.

## Comportamiento actual de la UI durante estabilización

La UI de Vite permite previsualizar órdenes usando dos flujos de lectura:
`GET /api/orders-stream` para la previsualización streaming existente y
`POST /api/batch-orders` para la previsualización batch dry-run protegida por
admin. Estas previsualizaciones pueden leer correos mediante el backend local si
las credenciales están configuradas, pero no escriben en OneDrive desde el
navegador.

La escritura en OneDrive permanece protegida durante esta fase. La UI muestra el
estado de escritura como deshabilitado y no expone acciones de escritura con
clave admin. El único campo de clave admin del frontend es temporal y sirve para
la previsualización batch dry-run local; la clave se mantiene en memoria del
componente y no se guarda en almacenamiento del navegador.

Las rutas backend de escritura, borrado, webhook y renovación siguen requiriendo
`X-Admin-API-Key`. Esta es una medida temporal de toma de control/estabilización,
no el flujo final de autenticación de producción.

## Crear plantilla Word

```bash
python create_template.py
```

## Obtener refresh token (una sola vez)

Define variables de entorno y ejecuta:

```bash
export GMAIL_CLIENT_ID="tu_client_id"
export GMAIL_CLIENT_SECRET="tu_client_secret"
python setup_oauth.py
```

Guarda el token en Secret Manager como `GMAIL_REFRESH_TOKEN`.

## Configurar secretos en Firebase

```bash
firebase functions:secrets:set GMAIL_CLIENT_ID
firebase functions:secrets:set GMAIL_CLIENT_SECRET
firebase functions:secrets:set GMAIL_REFRESH_TOKEN
```

## Despliegue

```bash
firebase deploy --only functions
```

## Comportamiento de idempotencia

- Antes de procesar cada correo, consulta `processed_emails/{message_id}` en Firestore.
- Después de generar/subir el reporte, marca cada mensaje como procesado en transacción.
- Si se reejecuta la función, no duplica correos ya registrados.

## Prueba rápida del parser

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Manual Fetch Orders (UI)

The Fetch Orders page in the 2.0 admin UI supports:

- Supplier selector: individual supplier or all active suppliers
- Quick-range buttons: Last 24h, Last 7 days, Last 30 days
- Custom date range via date pickers
- Dry-run only (`dry_run: true` is hardcoded in the UI)
- `write_target` defaults to `"none"` — no OneDrive writes
- Structured JSON result with per-supplier email/order counts and sanitized preview rows

Manual fetch does **not** call `/api/append-to-onedrive`, `/api/daily-update`, or
`/api/clear-onedrive-rows`. It calls only `POST /api/batch-orders` with
`dry_run: true`.

### Supplier routing and workbook targets

Each active supplier must be processed as its own route:

`Supplier -> To Email / Routing Key -> OneDrive Workbook -> Active Worksheet`

Configured suppliers use `routing_key` when present, otherwise `email`. Manual
fetch and all-supplier fetch run a separate Gmail search for each supplier using
`deliveredto:<configured inbox>` plus `to:<supplier routing key>`. Selecting one
supplier must never fetch or process the other suppliers. All-supplier mode
processes active suppliers sequentially and returns separate per-supplier
summaries.

Supplier config now supports future Excel targets with:

- `onedrive_file_name`, `onedrive_file_id`, `onedrive_drive_id`
- `active_sheet` / `active_year`
- `custom_fields[]` as future Excel columns and extraction rules

Changing workbook or sheet config affects future writes only. Existing files,
sheets, rows, and columns must not be deleted, moved, merged, copied, or
overwritten automatically.

The default workbook model is one workbook per supplier and one sheet per year,
for example `Jake Test.xlsx` with sheets `2025`, `2026`, and `2027`. The Excel
helper can create a new yearly sheet by copying headers only from an existing
sheet; it does not copy old order rows and does not overwrite an existing sheet.

Adding a custom field safely adds its column to the supplier active sheet if it
is missing. Existing rows and columns are preserved. Future parsed emails use the
custom field `field_name`, `type`, `source`, and `hint`; missing optional values
stay blank and produce safe warnings.

Current live OneDrive code still contains legacy Word `.docx` helpers for older
paths. The Excel workbook helpers are local-byte safe helpers and do not call
OneDrive by themselves.

### Parser strategy and diagnostics

Stephen parsing remains supported by `stephen_regex`. Other suppliers can use
`generic_regex` for label-style fields or `smart` / `gemini_fallback` when a
format is unknown or messy. Gemini defaults to `gemini-2.5-flash` and can be
overridden with `GEMINI_MODEL`. Gemini is limited to field extraction only: it
must not choose the supplier, routing key, workbook, worksheet, or destination.
API code validates parser output before rows are counted for writing.

For every fetched email, batch preview returns safe diagnostics:

- supplier id and name
- shortened message id and subject
- body extracted yes/no and body length
- HTML converted to text yes/no
- attachment/PDF counts
- PDF text extracted yes/no and PDF text length
- parser used
- required fields found/missing
- final status: `parsed`, `skipped`, `duplicate`, or `error`
- safe skip reason

Diagnostics never include secrets, tokens, raw credentials, full email bodies,
raw PDF text, or full customer-sensitive payloads. If a PDF/image attachment has
no selectable text, diagnostics report that OCR/Gemini vision may be required.

### Date handling and dedupe

Same-day UI selections include the full day. For example, selecting June 2, 2026
builds a Gmail query equivalent to:

```text
after:2026/06/01 before:2026/06/03
```

Re-running a fetch must not duplicate rows. The active dry-run response reports
duplicates skipped within the supplier result. Production writes should mark rows
processed only after a successful Excel write; failed writes must not mark rows
as processed.

### Automatic 2:00 AM run

The intended automatic run uses the same supplier routing rules as manual fetch:
process active suppliers independently, run one Gmail search per supplier, keep
rows separated by supplier, and write only to the configured workbook and active
sheet for that supplier. If Cloud Scheduler is enabled, the scheduler endpoint
must use production auth and must be verified after deployment.

### Production pressure cases

Before demo or production signoff, pressure-test these real-world cases with
fake/demo/test data first:

- Multiple supplier routing keys in one email: all-supplier mode should skip the
  message with `ambiguous_multiple_supplier_routing_keys` unless explicit split
  behavior is later designed.
- Forwarded/replied Gmail thread duplicates: repeated appearances of the same
  supplier/thread/item/customer should be deduped before append.
- Gemini source fidelity: Gemini may extract fields only. Item codes and
  order-number-like values that cannot be traced to the source text should carry
  warnings such as `item_code_not_source_verified`.
- Custom fields after existing rows: matching is normalized by trimming,
  lowercasing, and collapsing whitespace; existing rows/columns must stay in
  place and old rows remain blank until an explicit backfill exists.
- Image-only/scanned PDFs: if no body/PDF text can be read, diagnostics should
  include `attachment_may_require_ocr_or_gemini_vision` and no blank/partial row
  should be written.

## 2:00 AM Scheduled Run — Audit Result

### Legacy Firebase scheduled function (reference path)

`functions/main.py` contains `process_stephen_orders`, a Firebase Cloud Functions v2
scheduled function:

```python
@scheduler_fn.on_schedule(
    schedule="0 2 * * *",
    timezone=scheduler_fn.Timezone("America/New_York"),
    ...
)
def process_stephen_orders(event): ...
```

This is the **original Firebase Functions** path from the prototype era. It is
**not** part of the 2.0 FastAPI backend (`api.py`). It uses the old Firestore
deduplication, old `WordReportGenerator`, and the legacy Stephen-only workflow.
It is kept as reference/legacy material only.

### 2.0 FastAPI backend (active path)

The 2.0 backend exposes `POST /api/daily-update` as the production-ready
scheduled-run endpoint. **This endpoint is not automatically triggered by
anything.** No Cloud Scheduler job, cron, or external timer currently calls it.

### What is currently automatic

Nothing in 2.0 runs automatically at 2:00 AM or on any schedule.

### What is needed for production scheduling

To restore the 2:00 AM run via the 2.0 FastAPI backend:

1. Deploy 2.0 to Cloud Run (or equivalent).
2. Create a **Cloud Scheduler** job:
   - Schedule: `0 2 * * *` (America/New_York)
   - Target: `POST https://<2.0-backend-url>/api/daily-update?days=1`
   - Header: `X-Admin-API-Key: <production-admin-key>` (or replace with a
     scheduler-only OIDC auth token)
3. Confirm `ONEDRIVE_DRIVE_ID`, `ONEDRIVE_FILE_ID`, and all Gmail credentials
   are correctly set in the production Cloud Run service.
4. Verify at least one manual `POST /api/daily-update` succeeds before enabling
   the schedule.
5. Monitor Cloud Scheduler execution history and Cloud Run logs after the first
   automated run.

### Recommended future improvements before production scheduling

- Replace the `X-Admin-API-Key` header with Cloud Scheduler OIDC authentication
  so the production endpoint is not callable publicly.
- Add idempotency: track already-processed Gmail message IDs (Firestore or
  equivalent) so retries do not duplicate orders.
- Add a configurable lookback window (`SEARCH_HOURS_BACK`) so the scheduler can
  safely use `days=1` without missing late-arriving emails.
- The production scheduler is not considered live until deployed, tested, and
  explicitly verified by Leo or an authorized admin.

**Production scheduling must be explicitly enabled and verified. It does not
happen automatically from the 2.0 codebase alone.**
