# Gmail OAuth Token — Guía de Renovación

## Situación actual (Mayo 13, 2026)

El sistema dejó de funcionar porque el **refresh token de Gmail expiró**.

**Causa raíz:** La app OAuth estaba en modo **"Testing"** en Google Cloud Console.
En ese modo, Google expira los refresh tokens automáticamente cada **7 días**.

**Solución aplicada:**
1. ✅ App publicada a **"In production"** en Google Cloud Console → Audience
2. ✅ Nuevo refresh token generado corriendo `scripts/setup_oauth.py` desde la Mac local
3. ⏳ **PENDIENTE:** Actualizar `GMAIL_REFRESH_TOKEN` en Cloud Run con el nuevo token

---

## ¿Se volverá a expirar el token?

**NO.** Ahora que la app está en Production, el token dura indefinidamente.

Según la documentación oficial de Google, un refresh token solo deja de funcionar si:
- El usuario revoca el acceso manualmente
- No se usa por **6 meses consecutivos** (el sistema lo usa diariamente)
- Se cambia la contraseña de `bettercrafter1@gmail.com`
- Se genera demasiados tokens del mismo cliente (límite: 100)

---

## Cómo renovar el token (cuando sea necesario en el futuro)

Correr **desde la Mac local** (NO desde Cloud Shell):

```bash
cd /Users/1di/order_system_automatition
python3 scripts/setup_oauth.py
```

El script automáticamente:
1. Abre el browser para autorizar con `bettercrafter1@gmail.com`
2. Guarda el nuevo token en Secret Manager
3. Actualiza Cloud Run
4. Renueva el Gmail push-watch

### ¿Por qué desde la Mac y no desde Cloud Shell?
Google deprecó el flujo OOB (copy-paste de código) en 2022.
El método actual requiere un servidor local en `127.0.0.1` al que el browser
pueda conectarse — esto solo funciona en la Mac, no en Cloud Shell.

---

## PENDIENTE ahora mismo

El token nuevo fue generado pero el script falló al guardarlo en Secret Manager
(pidió contraseña del keychain del sistema varias veces).

Refresh token value removed from tracked documentation. Store replacement only in Secret Manager or local `.env`.

### Opción A — Volver a correr el script completo (recomendado)
```bash
cd /Users/1di/order_system_automatition
python3 scripts/setup_oauth.py
```
Cuando pida la contraseña del Mac, ingresarla. Si la pide varias veces, es normal.

### Opción B — Actualizar Cloud Run manualmente
Si tienes el token completo copiado:
```bash
gcloud run services update order-app \
  --region=us-central1 \
  --project=ordersbc-494213 \
  --update-env-vars=GMAIL_REFRESH_TOKEN="TOKEN_COMPLETO_AQUI"
```

Luego renovar el Gmail watch:
```bash
curl -X POST https://order-app-363114180511.us-central1.run.app/api/renew-gmail-watch
```

---

## Verificar que funciona
```bash
gcloud run services logs read order-app \
  --project=ordersbc-494213 \
  --region=us-central1 \
  --limit=20
```
Debe aparecer `✅ Token refreshed` en lugar de `invalid_grant`.

---

## Credenciales relevantes

| Variable | Descripción |
|----------|-------------|
| `GMAIL_CLIENT_ID` | Client ID del cliente **"gmail-desktop"** (Desktop) en Google Cloud Console → APIs & Services → Credentials |
| `GMAIL_CLIENT_SECRET` | Client Secret del mismo cliente Desktop |
| `GMAIL_ACCOUNT` | `bettercrafter1@gmail.com` |
| `GMAIL_REFRESH_TOKEN` | Guardar en Cloud Run env vars + Secret Manager |

> ⚠️ Hay dos OAuth clients en el proyecto. El correcto para el flujo de autorización
> es el de tipo **Desktop** llamado **"gmail-desktop"** (`363114180511-r3ct...`),
> NO el de tipo Web application (`706034452884`).
> Los valores exactos están en el archivo `.env` local (no subir a git).
