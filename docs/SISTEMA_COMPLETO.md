# Better Crafter Orders — Documentación Completa del Sistema

> Última actualización: 04 de mayo de 2026  
> Desarrollado para: **Leo** (Better Crafter)  
> Desarrollado por: Juan

---

## 📋 Índice

1. [¿Qué hace este sistema?](#qué-hace-este-sistema)
2. [Arquitectura](#arquitectura)
3. [Flujo completo](#flujo-completo)
4. [Infraestructura GCP](#infraestructura-gcp)
5. [Credenciales y variables de entorno](#credenciales-y-variables-de-entorno)
6. [Endpoints de la API](#endpoints-de-la-api)
7. [Historial de problemas resueltos](#historial-de-problemas-resueltos)
8. [Deploy y mantenimiento](#deploy-y-mantenimiento)
9. [Estado actual](#estado-actual)

---

## ¿Qué hace este sistema?

El proveedor **Stephen** (`7173783020@hellofax.com`) envía pedidos por email a **Leo** (`bettercrafter1@gmail.com`). Cada email contiene los datos de una orden: cliente, producto, cantidad, fecha de envío, etc.

Este sistema:
1. **Detecta automáticamente** cuando llega un email de Stephen (via Gmail Push Notifications)
2. **Parsea** el contenido del email y extrae los datos del pedido
3. **Escribe** esos datos en un documento Word en OneDrive (`Bird Feeders & Houses - Steven 2026.docx`)
4. **Cada madrugada** (2 AM ET) hace una sincronización del día anterior como respaldo

Leo nunca necesita hacer nada manualmente.

---

## Arquitectura

```
Stephen (proveedor)
  └─ Email → bettercrafter1@gmail.com
                    │
                    │  Gmail Push Notifications (Pub/Sub)
                    ▼
         Google Cloud Pub/Sub
         topic: gmail-orders
                    │
                    │  HTTPS POST
                    ▼
         Cloud Run: order-app (FastAPI)
         https://order-app-363114180511.us-central1.run.app
                    │
              ┌─────┴─────┐
              │           │
         Gmail API    OneDrive (Graph API)
         (leer email) (escribir .docx)
                    │
                    ▼
         Bird Feeders & Houses - Steven 2026.docx
         (en OneDrive de Leo)
```

### Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI (Python 3.12) |
| Frontend | Vite + React |
| Email | Gmail API OAuth2 |
| Parser | Regex (con fallback Gemini) |
| Documento | python-docx → OneDrive |
| Notificaciones | Gmail Push → Google Pub/Sub |
| Hosting | Google Cloud Run |
| Scheduler | Google Cloud Scheduler |

---

## Flujo completo

### Flujo en tiempo real (cuando llega un email)

```
1. Stephen envía email a bettercrafter1@gmail.com
       │
2. Gmail detecta el nuevo email
       │
3. Gmail notifica a Google Pub/Sub (topic: gmail-orders)
       │
4. Pub/Sub hace POST a /api/gmail-webhook
       │
5. Cloud Run recibe la notificación (base64 decodificado)
       │
6. Gmail API busca emails de hoy de Stephen
       │
7. Parser extrae: customer_name, item_code, quantity, ship_by, color, etc.
       │
8. Se descarga el .docx de OneDrive
       │
9. Se agregan las nuevas filas (con detección de duplicados)
       │
10. Se sube el .docx actualizado a OneDrive
```

### Flujo nocturno (Cloud Scheduler — 2 AM ET)

```
Cloud Scheduler dispara /api/daily-update?days=1
       │
       ├─ Busca emails de Stephen del día anterior
       ├─ Parsea y filtra duplicados
       ├─ Descarga .docx de OneDrive
       ├─ Agrega filas nuevas
       └─ Sube .docx actualizado
```

Este flujo nocturno es el **respaldo principal** — a las 2 AM el archivo está cerrado, por lo que nunca hay error 423 Locked.

---

## Infraestructura GCP

| Recurso | Nombre | Detalles |
|---|---|---|
| Proyecto | `ordersbc-494213` | Proyecto principal |
| Cloud Run | `order-app` | Región: `us-central1` |
| Pub/Sub Topic | `gmail-orders` | Recibe notificaciones de Gmail |
| Pub/Sub Subscription | `gmail-orders-sub` | Push → `/api/gmail-webhook` |
| Cloud Scheduler | `renew-gmail-watch` | Diario 9 AM UTC → `/api/renew-gmail-watch` |
| Cloud Scheduler | `daily-onedrive-update` | Diario 7 AM UTC (2 AM ET) → `/api/daily-update?days=1` |
| OAuth Client | `363114180511-r3cttlssveajnu1h4pismlod2v5f1qmj` | Tipo Desktop/Installed |

**URL producción:** `https://order-app-363114180511.us-central1.run.app`

### Revisiones Cloud Run desplegadas

| Revisión | Cambio principal |
|---|---|
| `order-app-00001` | Deploy inicial |
| `order-app-00015-xt7` | Firestore removido del webhook |
| `order-app-00018-kch` | ✅ **Actual** — daily-update, limpieza de endpoints |

---

## Credenciales y variables de entorno

Todas las variables están configuradas en Cloud Run (no en código):

| Variable | Descripción |
|---|---|
| `GMAIL_CLIENT_ID` | ID del cliente OAuth (proyecto ordersbc-494213) |
| `GMAIL_CLIENT_SECRET` | Secret del cliente OAuth |
| `GMAIL_REFRESH_TOKEN` | Token de refresco de bettercrafter1@gmail.com |
| `GMAIL_ACCOUNT` | `bettercrafter1@gmail.com` |

### Constantes hardcodeadas en `api.py`

```python
STEPHEN_EMAIL  = "7173783020@hellofax.com"   # Proveedor — no cambia
INBOX_ACCOUNT  = "bettercrafter1@gmail.com"  # Inbox de Leo — no cambia
```

### OneDrive

La configuración del token de OneDrive (Microsoft Graph API) está en `functions/onedrive_client.py`. Apunta al archivo:
```
Bird Feeders & Houses - Steven 2026.docx
Drive ID: 9f9c6569035a2b06
Item ID:  9F9C6569035A2B06!s8f3f59c58ae4411c9bb2622519f7ee43
```

---

## Endpoints de la API

### `POST /api/daily-update?days=N`
**El endpoint principal.** Busca emails de Stephen de los últimos N días y los agrega a OneDrive.

- `days=1` → solo ayer (lo usa el Cloud Scheduler a las 2 AM)
- `days=7` → última semana
- `days=20` → catch-up de 20 días

```bash
# Ejemplo de uso manual:
curl -X POST "https://order-app-363114180511.us-central1.run.app/api/daily-update?days=2"
```

Respuesta:
```json
{
  "status": "ok",
  "range": "2026-05-03 → 2026-05-04",
  "orders_found": 5,
  "orders_appended": 5,
  "orders_skipped": 0
}
```

---

### `POST /api/append-to-onedrive`
Agrega órdenes enviadas en el body (desde el frontend) al documento OneDrive.

```json
{ "orders": [ {...}, {...} ] }
```

---

### `POST /api/gmail-webhook`
Recibe notificaciones push de Google Pub/Sub. **No llamar manualmente.**

---

### `POST /api/renew-gmail-watch`
Renueva la suscripción de Gmail Push Notifications (expira cada 7 días). Llamado por Cloud Scheduler automáticamente.

---

### `GET /api/orders`
Busca y parsea emails de Stephen.

```
GET /api/orders?start_date=2026-05-01&end_date=2026-05-04
```

---

### `GET /api/orders-stream`
Igual que `/api/orders` pero con SSE (Server-Sent Events) para mostrar progreso en el frontend.

---

### `GET /api/health`
Healthcheck.

```json
{ "status": "ok", "date": "2026-05-04" }
```

---

## Historial de problemas resueltos

### ❌ → ✅ Cuenta de Gmail incorrecta
- **Problema**: El sistema usaba `bettercrafterorders@gmail.com` pero los emails llegaban a `bettercrafter1@gmail.com`
- **Solución**: Migración completa a `bettercrafter1@gmail.com`, nuevo OAuth, nuevo refresh token

### ❌ → ✅ OAuth client del proyecto equivocado
- **Problema**: Se usaba el client ID `706...` que pertenecía al proyecto `automation-system-493415`, no al proyecto actual `ordersbc-494213`
- **Solución**: Usar el client ID `363...` del proyecto correcto

### ❌ → ✅ Error 403 access_denied en OAuth
- **Problema**: `bettercrafter1@gmail.com` no estaba en la lista de usuarios de prueba del OAuth consent screen
- **Solución**: Agregar la cuenta a "Test users" y poner la app en modo Testing

### ❌ → ✅ Webhook devolvía 422 Unprocessable Entity
- **Problema**: FastAPI intentaba parsear el body del webhook como JSON con tipado de Pydantic, pero el body de Pub/Sub no coincidía con el modelo esperado
- **Solución**: Cambiar a `async def gmail_webhook(request: Request)` y leer el body como bytes crudos con `await request.body()`

### ❌ → ✅ Firebase/Firestore no inicializado en Cloud Run
- **Problema**: El webhook intentaba usar Firestore para guardar estado, pero Firebase no estaba configurado en Cloud Run, causando errores en cada notificación
- **Solución**: Eliminar Firestore completamente del webhook. La detección de duplicados se hace comparando filas en el propio documento Word

### ❌ → ✅ OneDrive 423 Locked
- **Problema**: Cuando Leo tenía el archivo `.docx` abierto en Word/OneDrive, la API de Microsoft Graph devolvía error 423 (archivo bloqueado) al intentar subir la nueva versión
- **Causa**: OneDrive bloquea el archivo cuando está abierto para edición
- **Solución implementada**:
  1. Retry automático en `onedrive_client.py` (5 intentos con backoff)
  2. **Solución real**: Cloud Scheduler a las **2 AM ET** — a esa hora el archivo siempre está cerrado
  3. Endpoint `/api/daily-update` diseñado específicamente para este flujo nocturno

---

## Deploy y mantenimiento

### Hacer un nuevo deploy (desde Cloud Shell)

```bash
cd ~/better-crafter-orders
git pull origin main
gcloud run deploy order-app \
  --source . \
  --project ordersbc-494213 \
  --region us-central1 \
  --quiet
```

### Ver logs en tiempo real

```bash
gcloud run services logs read order-app \
  --region us-central1 \
  --project ordersbc-494213 \
  --limit 50
```

### Catch-up manual (si algo falla un día)

```bash
# Procesar los últimos 3 días (duplicados se saltan automáticamente)
curl -X POST "https://order-app-363114180511.us-central1.run.app/api/daily-update?days=3"
```

### Ver jobs del scheduler

```bash
gcloud scheduler jobs list --project ordersbc-494213 --location us-central1
```

### Forzar ejecución del scheduler manualmente

```bash
gcloud scheduler jobs run daily-onedrive-update \
  --project ordersbc-494213 \
  --location us-central1
```

### Renovar Gmail Watch manualmente

```bash
curl -X POST "https://order-app-363114180511.us-central1.run.app/api/renew-gmail-watch"
```

---

## Estado actual

> Al 04 de mayo de 2026

| Componente | Estado | Detalles |
|---|---|---|
| Gmail OAuth | ✅ Activo | bettercrafter1@gmail.com |
| Gmail Push Notifications | ✅ Activo | Pub/Sub → webhook |
| Webhook `/api/gmail-webhook` | ✅ Funcionando | Sin errores 422 |
| Cloud Scheduler (renovar watch) | ✅ Activo | Diario 9 AM UTC |
| Cloud Scheduler (daily update) | ✅ Activo | Diario 7 AM UTC (2 AM ET) |
| OneDrive sync | ✅ **93 pedidos escritos** | 04/14 → 05/04/2026 |
| Deploy activo | ✅ `order-app-00018-kch` | |

### Pedidos en OneDrive
- **Antes de hoy**: solo hasta 04/15
- **Hoy (catch-up)**: se escribieron **93 pedidos** del 04/14 al 05/04
- **A partir de mañana**: el scheduler escribe automáticamente cada madrugada

---

## Estructura del repositorio

```
better-crafter-orders/
├── api.py                          # FastAPI — todos los endpoints
├── Dockerfile                      # Multi-stage: Node (Vite) + Python (FastAPI)
├── requirements.txt                # Dependencias Python del backend
├── functions/
│   ├── email_parser.py             # Parser Regex + Gemini
│   ├── gmail_client.py             # Gmail API — listar y leer emails
│   ├── onedrive_client.py          # Microsoft Graph API — download/upload .docx
│   ├── word_generator.py           # Manipulación de .docx con python-docx
│   └── config.py                   # Configuración general
├── frontend/
│   └── src/
│       └── App.jsx                 # UI: date picker, tabla de órdenes, botones
├── scripts/
│   ├── setup_oauth.py              # Genera refresh token Gmail (uso único)
│   ├── setup_gmail_watch.py        # Activa Gmail Push Notifications
│   └── deploy_cloudshell.sh        # Script de deploy desde Cloud Shell
├── templates/
│   └── stephen_template.docx       # Plantilla Word base
└── docs/
    ├── PROGRESS.md                 # Log de cambios histórico
    ├── DESIGN.md                   # Diseño del sistema
    └── SISTEMA_COMPLETO.md         # ← Este archivo
```
