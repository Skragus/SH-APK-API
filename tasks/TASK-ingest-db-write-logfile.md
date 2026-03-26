## Goal
Log all database writes performed by ingest endpoints to a file with reliable timestamps.

## Non-goals
- Change query endpoint behavior.
- Add external logging dependencies.
- Implement log shipping/rotation infrastructure.

## Blast radius
- `app/main.py` logging setup and ingest write paths.
- `app/config.py` optional file path setting for DB write logs.

## Acceptance checks
- `POST /v1/ingest/daily` writes a DB audit entry to a log file when insert succeeds.
- `POST /v1/ingest/intraday` writes DB audit entries for delete/insert flow.
- Audit entries include timestamp and write context (table, operation, device/date, row id or rows affected).

## Test plan
1. Run Python syntax check for edited modules.
2. Run lint diagnostics for edited files.
3. Review diff to confirm only ingest/logging scope changed.
