## Goal
Make intraday ingestion overwrite the prior same-day snapshot for a device instead of accumulating rows throughout the day.

## Non-goals
- Change daily ingestion behavior.
- Redesign query endpoints outside intraday overwrite semantics.
- Add new dependencies.

## Blast radius
- `app/main.py` intraday ingest SQL behavior.
- Potentially intraday logs query behavior if response format needs compatibility.

## Acceptance checks
- `POST /v1/ingest/intraday` does not create multiple rows for the same `(device_id, date)`.
- Repeated intraday syncs on the same day return success and preserve only the latest snapshot.
- Existing daily ingestion and read endpoints continue to work.

## Test plan
1. Run focused test/lint checks for changed files.
2. If no tests exist, run project test command and report outcome.
3. Verify no new lint errors in edited files.
