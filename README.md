# Order System Automation (Firebase + Gmail + DOCX)

Sistema de automatización con Firebase Cloud Functions (Python gen 2) para leer correos salientes de Gmail hacia un proveedor (Stephen), extraer órdenes y generar un reporte `.docx` diario.

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
