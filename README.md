# Order System Automation (Firebase + Gmail + DOCX)

Sistema de automatización con Firebase Cloud Functions (Python gen 2) para leer correos salientes de Gmail hacia un proveedor (Stephen), extraer órdenes y generar un reporte `.docx` diario.

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

- `functions/main.py`: función programada principal (cada 12 horas)
- `functions/gmail_client.py`: cliente Gmail API con OAuth2 + retries
- `functions/email_parser.py`: parser extensible con registry por proveedor
- `functions/word_generator.py`: generación y subida de reporte Word
- `functions/firestore_client.py`: deduplicación idempotente con Firestore
- `functions/config.py`: configuración general
- `templates/stephen_template.docx`: plantilla Word
- `create_template.py`: script para crear la plantilla
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
