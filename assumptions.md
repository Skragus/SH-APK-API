# Assumptions, Placeholders & Thoughts

Pre-implementation notes for `sh-apk-api` — the Samsung Health "truth layer" ingest API.

---

## Assumptions

### Auth
- A single static `API_KEY` env var is sufficient for now. There is no user/session/token model.
- The Android app (or Tasker) will send this key in the `X-API-Key` header on every request.

### Data Model
- **One row = one device + one calendar date + one schema version.** Re-syncing the same day overwrites everything except `received_at`, which preserves the original ingestion timestamp.
- `sleep_sessions` and `heart_rate_summary` are intentionally schemaless JSONB. The Android side decides the shape; the API stores it as-is. Tighter validation can be added later per `schema_version`.
- `steps_total` is a non-negative integer. Zero is valid (e.g. device worn but idle).
- `schema_version` defaults to `1`. When the payload shape changes in the future, bump this and the unique constraint keeps old and new versions as separate rows for the same date.

### Dates & Time
- "Date cannot be in the future" is evaluated against **UTC**. A user in UTC+13 submitting near midnight could technically be rejected. This is acceptable for now.
- `collected_at` is the phone-local timestamp of when the data was gathered. It is stored as-is (with timezone).

### Database
- PostgreSQL is the only supported backend (asyncpg driver, JSONB columns, PG `INSERT … ON CONFLICT`).
- In development, `Base.metadata.create_all` runs at startup to bootstrap tables. In production, only Alembic migrations should be used.
- `received_at` uses the DB server's `now()` so clock skew between app server and DB is irrelevant.

### Deployment
- Target host is **Railway** with their managed PostgreSQL plugin.
- Railway auto-provides `DATABASE_URL`. The code rewrites `postgresql://` → `postgresql+asyncpg://` at runtime.
- The Dockerfile exposes port `8000`; Railway's proxy handles TLS termination and public routing.

### Android Bridge APK (Client)
- Tech stack: **Kotlin**, **AndroidX**, **WorkManager**, official Samsung Health SDK.
- App structure: single-Activity setup UI only; no ongoing UI after initial configuration.
- Scheduling: a `WorkManager` job runs **once per day at ~02:30 local time**, using a periodic `WorkRequest` with appropriate flex time.
- Reported date: the payload `date` is the **local “yesterday” calendar date**; the job always reports for yesterday so the day is complete.
- `collected_at`: an ISO-8601 timestamp of when the worker actually runs (ideally in UTC, with offset).
- `device_id`: a stable `UUID` generated once on first run and stored in `SharedPreferences`; reused for all future requests from that phone.
- Networking: HTTP `POST` to `/v1/ingest/shealth/daily` with a static `X-API-Key` header value sourced from `BuildConfig` (no runtime editing).
- Heart rate: **only** send `heart_rate_summary` if `resting_hr` is available from Samsung Health; otherwise **omit** `heart_rate_summary` entirely (no best-effort mix of other stats).
- Failure policy: **no backfill**. If a run fails (no network, permission error, server issue), that day’s data is skipped; we try again on the next scheduled run for that new “yesterday”.
- WorkManager constraints: requires `networkType = CONNECTED` and uses **exponential backoff** for transient failures, letting WorkManager handle retries.
- Android targets: `minSdk = 26`, `targetSdk = latest stable` (to be updated as Android releases advance).
- Endpoint config: base URL and API key are defined via **`BuildConfig` and build flavors** (e.g. `staging` vs `prod`); there is **no in-app debug/preferences screen** for overriding them.

---

## Placeholders

| Item | Current value | Replace with |
|---|---|---|
| `API_KEY` | Set via `.env` / Railway variable | A strong random secret before first deploy |
| `DATABASE_URL` | Set via `.env` / Railway variable | Railway auto-injects; local dev needs a real PG connection string |
| Alembic config | Not yet generated | Run `alembic init -t async alembic` and wire up `env.py` |
| `.env` file | Does not exist yet | Create locally with `DATABASE_URL` and `API_KEY` |

---

## Thoughts & Future Considerations

### Short-term (before or during v1 deploy)
- **Health check endpoint**: Add `GET /health` that pings the DB and returns `{"status": "ok"}`. Useful for Railway's health checks and uptime monitoring.
- **CORS**: Not needed yet (no browser client), but if a dashboard is added later, CORS middleware will be required.
- **Rate limiting**: Not in scope for v1. The only client is a single phone. If this opens up, add middleware or rely on Railway's proxy.

### Medium-term
- **Batch ingest**: The current endpoint accepts one day at a time. A `POST /v1/ingest/shealth/daily/batch` accepting a list would reduce round-trips if the phone catches up after being offline for days.
- **Read endpoints**: There are no `GET` routes yet. Eventually you'll want `GET /v1/shealth/daily?from=...&to=...` for dashboards or exports.
- **Tighter JSONB validation**: Once the sleep/heart-rate shapes stabilize on the Android side, add Pydantic sub-models per `schema_version`.

### Long-term
- **Auth upgrade**: If more devices or users are added, move from a static API key to JWT or OAuth2 device tokens.
- **Data retention / archival**: Define a policy (e.g. roll up daily rows into monthly aggregates after 1 year).
- **Observability**: Structured JSON logging, request-id tracing, and metrics (Prometheus or Railway's built-in).

---

*This file is a living document. Update it as decisions are made during implementation.*
