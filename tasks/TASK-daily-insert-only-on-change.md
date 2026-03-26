## Goal
Make daily ingestion append a new row only when the daily payload content has changed for the same device/date.

## Non-goals
- Change intraday overwrite behavior.
- Add DB constraints/migrations.
- Change query endpoint response schema.

## Blast radius
- `app/main.py` daily ingest logic.

## Acceptance checks
- Same `(device_id, date)` + same `payload_hash` does not insert a new row.
- Same `(device_id, date)` + different `payload_hash` inserts a new row.
- Endpoint still returns success and stays backward compatible.

## Test plan
1. Run syntax check for edited file(s).
2. Run lints for edited file(s).
3. Verify diff only touches daily ingest flow and task file.
