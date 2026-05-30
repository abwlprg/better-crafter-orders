# Better Crafter Orders — Progreso del Proyecto

## 🏗️ Arquitectura Final

| Componente | Tecnología | Detalles |
|---|---|---|
| Backend | FastAPI (Python 3.12) | Cloud Run `order-app` |
| Frontend | Vite + React | Servido desde el mismo Cloud Run |
| Email | Gmail API OAuth2 | Cuenta `bettercrafter1@gmail.com` |
| Parser | Regex + Gemini fallback | Solo Stephen por ahora |
| Reporte | python-docx | Genera `.docx` descargable |
| Deploy | Cloud Run (GCP) | Proyecto `ordersbc-494213` |

**URL producción:** `https://order-app-363114180511.us-central1.run.app`

---

## ✅ Lo que se hizo

### 1. Migración de proyecto GCP
- El token OAuth original de Stephen (`7173783020@hellofax.com`) expiró/fue revocado
- Se creó cuenta nueva dedicada: `bettercrafter1@gmail.com` (password: `BCorders!`)
- Se creó proyecto GCP nuevo: `ordersbc-494213`
- Se generó nuevo refresh token via OAuth Playground

### 2. Consolidación en un solo Cloud Run
- Antes: backend y frontend separados
- Ahora: Dockerfile multi-stage (Node 20 para build Vite + Python 3.12 para FastAPI)
- El backend sirve el frontend como archivos estáticos
- `VITE_API_URL=/api` — todo en el mismo dominio

### 3. Descubrimiento BCC
- Los correos de Ben (`bettercrafterorders@gmail.com`) llegan a `bettercrafter1@gmail.com` por **BCC**
- Gmail no muestra correos BCC en Inbox, van a "All Mail"
- Solución: usar operador `deliveredto:` en lugar de `to:` en la query

### 4. Filtro por proveedor
- Antes: traía correos de TODOS los proveedores (57 correos)
- Ahora: filtra `to:7173783020@hellofax.com` para solo traer órdenes de Stephen
- Resultado: 18 correos reales de Stephen

### 5. Hardcodeo de constantes
- Eliminado `os.environ.get("STEPHEN_EMAIL", ...)` — ahora es constante en código
- `STEPHEN_EMAIL = "7173783020@hellofax.com"` en `api.py`
- `inbox_account = "bettercrafter1@gmail.com"` en `gmail_client.py`

### 6. Filtro por fechas reales
- Antes: `hours_back` (ventana imprecisa desde "ahora")
- Ahora: `start_date` / `end_date` en formato `YYYY-MM-DD`
- Gmail query usa `after:YYYY/MM/DD before:YYYY/MM/DD` — fecha exacta
- Frontend manda las fechas seleccionadas en el date picker
- Sin fechas → últimos 7 días (default)

### 7. Logs detallados
Por cada correo se loguea:
- 📅 Date, 📝 Subject, 👤 From, 📨 To, 🤫 Bcc, 🆔 Delivered-To
- Body length, PDF files encontrados
- ✅ Parsed (customer, item) o ❌ Skipped (qué campo falta)
- Query Gmail completa (inbox, supplier, fechas)

---

## 🔑 Credenciales

| Variable | Valor |
|---|---|
| `GMAIL_CLIENT_ID` | *(ver Cloud Run env vars)* |
| `GMAIL_CLIENT_SECRET` | *(ver Cloud Run env vars)* |
| `GMAIL_REFRESH_TOKEN` | *(ver Cloud Run env vars)* |
| `GEMINI_API_KEY` | ⚠️ **BLOQUEADA** — necesita nueva key |
| `GMAIL_ACCOUNT` | `bettercrafter1@gmail.com` |

---

## ⚠️ Pendientes

### 🔴 URGENTE — API Key de Gemini bloqueada
Gemini API key value removed from tracked documentation. Store replacement only in a secret manager or local `.env`.

**Cómo arreglar:**
1. Ir a https://aistudio.google.com/app/apikey con `bettercrafter1@gmail.com`
2. Borrar la key vieja y crear nueva
3. Actualizar en Cloud Run:
```bash
gcloud run services update order-app \
  --region us-central1 \
  --project ordersbc-494213 \
  --update-env-vars GEMINI_API_KEY=NUEVA_KEY
```

Sin Gemini: parser usa regex fallback → 14/18 órdenes (78%). Con Gemini: esperado ~18/18 (100%).

### 🟡 Otros proveedores
- Michael, Lee, Amos, Shawn — formatos de email desconocidos, sin parser implementado
- Cuando lleguen, agregar parser en `functions/email_parser.py` y entrada en `SUPPLIERS` del frontend

### 🟡 Deploy después de cada cambio
Siempre hacer redeploy desde Cloud Shell después de cambios:
```bash
cd ~/better-crafter-orders && git pull origin main && gcloud run deploy order-app \
  --source . --region us-central1 --platform managed \
  --allow-unauthenticated --memory 1Gi --timeout 600 --project ordersbc-494213
```

---

## 📋 Flujo del sistema

```
Ben (bettercrafterorders@gmail.com)
  │
  │  Envía email:
  │    To: Steven <7173783020@hellofax.com>   ← proveedor
  │    Bcc: bettercrafter1@gmail.com          ← nos llega a nosotros
  │    Subject: [Nombre del cliente final]
  │    Adjunto: PDF con detalles de la orden
  │
  ▼
bettercrafter1@gmail.com (All Mail — no Inbox)
  │
  │  Gmail API query:
  │    deliveredto:bettercrafter1@gmail.com
  │    to:7173783020@hellofax.com
  │    has:attachment filename:pdf
  │    after:YYYY/MM/DD before:YYYY/MM/DD
  │
  ▼
FastAPI (Cloud Run)
  │
  ├── Extrae body del email (texto plano / HTML → texto)
  ├── Extrae texto del PDF adjunto (pdfplumber)
  ├── Parser (Regex + Gemini) → { customer_name, item_code, quantity, ship_by, color, ... }
  │
  ▼
Word Report (.docx)
  └── Descargable desde la app web
```

---

## 📁 Estructura relevante

```
api.py                          ← FastAPI backend + sirve frontend
Dockerfile                      ← Multi-stage: Node build + Python run
functions/
  gmail_client.py               ← Gmail API, query con after:/before:
  email_parser.py               ← SmartParser (Regex + Gemini)
  gemini_parser.py              ← Parser Gemini
  word_generator.py             ← Genera .docx
frontend/src/
  App.jsx                       ← Date picker, SSE progress, tabla de órdenes
```

---

## 🗓️ Historial de commits importantes

| Commit | Descripción |
|---|---|
| `9bc6ce4` | Filtrar query por supplier email (`to:7173783020@hellofax.com`) |
| `c034aa5` | Hardcodear emails + logs detallados por paso |
| `f7dbfb2` | Loguear headers por correo (Date, From, To, Bcc, Subject) |
| `d5a7a82` | Usar fechas reales `after:/before:` en lugar de `hours_back` |
