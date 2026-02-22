# SH-APK-API

**Health Data Ingestion API**

A FastAPI service that receives health metrics from Android devices, stores them in PostgreSQL, and sends Telegram notifications on sync. Built for Samsung Health / Health Connect integration.

---

## Tech Stack

- **Framework**: FastAPI (Python 3.12)
- **Database**: PostgreSQL 16 + asyncpg
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Notifications**: Telegram Bot API
- **Deployment**: Railway (Docker)

---

## API Endpoints

### Health & Status

```http
GET /health                    → Database connectivity check
GET /debug/status              → Sync statistics
```

### Data Ingestion (requires API key)

```http
POST /v1/ingest/shealth/daily
Content-Type: application/json
X-API-Key: <secret>

{
  "date": "2026-02-21",
  "device_id": "uuid",
  "steps_total": 8543,
  "body_metrics": {
    "weight_kg": 78.5,
    "body_fat_percentage": 15.2
  },
  "exercise_sessions": [...],
  "nutrition_summary": {...}
}
```

```http
POST /v1/ingest/shealth/intraday
```

### Data Retrieval (requires API key)

```http
GET /health/connect/latest                 → Most recent daily record
GET /health/connect/range                  → Date range query
GET /health/connect/by-date/{YYYY-MM-DD}   → Specific date
GET /health/connect/{record_id}            → By UUID
```

---

## Architecture

```
Android (Health Connect)
    ↓
POST /v1/ingest/shealth/*
    ↓
FastAPI → Validation → PostgreSQL
    ↓
Telegram Notification
```

### Database Schema

**health_connect_daily** — Upsert table, one row per device per day  
**health_connect_intraday_logs** — Append-only sync history

See [`DATABASE_README.md`](./DATABASE_README.md) for full schema.

---

## Local Development

```bash
git clone https://github.com/Skragus/SH-APK-API.git
cd SH-APK-API

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: DATABASE_URL, API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

alembic upgrade head
uvicorn app.main:app --reload
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `API_KEY` | Secret for X-API-Key header auth |
| `TELEGRAM_BOT_TOKEN` | Bot token for sync notifications |
| `TELEGRAM_CHAT_ID` | Chat ID to notify |

---

## Deployment

Railway auto-deploy from `master` branch:

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## License

MIT
