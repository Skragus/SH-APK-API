"""SH-APK-API — Health Connect Ingestion Layer (Simplified v2)"""

import hashlib
import json
import logging
import asyncio
import uuid
from pathlib import Path as FilePath
import httpx
from datetime import date as py_date, datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, status, Path, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine, get_db
from app.models import HealthConnectDaily, HealthConnectIntradayLog
from app.schemas import RawHealthConnectIngest, IngestResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-ingest")

db_write_logger = logging.getLogger("health-ingest.db-writes")
db_write_logger.setLevel(logging.INFO)
db_write_logger.propagate = False
if not db_write_logger.handlers:
    try:
        log_file_path = FilePath(settings.DB_WRITE_LOG_FILE)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        db_write_logger.addHandler(file_handler)
    except Exception as e:
        # Do not block API startup if file logging path is unavailable.
        logger.warning(f"DB write file logging disabled: {e}")

app = FastAPI(title="Health Connect Ingest API", version="2.0.0")


def _log_db_write(
    *,
    endpoint: str,
    operation: str,
    table: str,
    device_id: str,
    ingest_date: py_date,
    collected_at: datetime,
    row_id: uuid.UUID | None = None,
    rows_affected: int | None = None,
):
    """Write a structured audit line for ingest-triggered DB mutations."""
    record = {
        "event_ts_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "operation": operation,
        "table": table,
        "device_id": device_id,
        "date": ingest_date.isoformat(),
        "collected_at": collected_at.isoformat(),
    }
    if row_id is not None:
        record["row_id"] = str(row_id)
    if rows_affected is not None:
        record["rows_affected"] = rows_affected
    db_write_logger.info(json.dumps(record, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _canonical_payload_hash(raw_json: str) -> str:
    """SHA256 (hex) of canonicalized JSON for dedup/integrity."""
    parsed = json.loads(raw_json)
    canonical = json.dumps(parsed, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_raw_payload(
    payload: RawHealthConnectIngest,
    record_type: str,
) -> RawHealthConnectIngest:
    """Minimal validation for raw Health Connect payloads."""
    # Parse raw_json to check it's valid JSON
    try:
        json.loads(payload.raw_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in raw_json: {str(e)}"
        )
    
    # Check payload size (prevent abuse)
    if len(payload.raw_json) > 50_000_000:  # 50MB limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Payload exceeds 50MB limit"
        )
    
    # Ensure record_type matches endpoint
    if payload.record_type is not None and payload.record_type != record_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"record_type must be {record_type!r} for this endpoint",
        )
    return payload


# ---------------------------------------------------------------------------
# Data Processing / Deduplication
# ---------------------------------------------------------------------------

SOURCE_PRIORITY = {
    "com.sec.android.app.shealth": 1,
    "com.google.android.apps.fitness": 2,
    "com.health.openscale.sync.oss": 3,
}

def _get_source_priority(package_name: str) -> int:
    return SOURCE_PRIORITY.get(package_name, 99)

def _deduplicate_steps(steps_records: list) -> list:
    """
    Deduplicate by keeping only the latest (most recent endTime) record 
    from each source. This handles cumulative step counting where each
    sync contains updated totals for overlapping time periods.
    """
    if not steps_records:
        return []
    
    # Group by source
    by_source = {}
    for record in steps_records:
        pkg = record.get("metadata", {}).get("dataOrigin", {}).get("packageName", "unknown")
        end_time = record.get("endTime", "")
        
        if pkg not in by_source:
            by_source[pkg] = record
        else:
            # Keep the record with the latest endTime
            if end_time > by_source[pkg].get("endTime", ""):
                by_source[pkg] = record
    
    return list(by_source.values())

def _calculate_deduped_metrics(raw_data: dict) -> dict:
    """
    Calculate step count using only the highest priority source.
    Avoids double-counting when multiple apps track the same activity.
    """
    steps_records = raw_data.get("StepsRecord", [])
    
    # Raw count (sum everything - for reference only)
    raw_steps = sum(s.get("count", 0) for s in steps_records)
    
    # Group records by source
    by_source = {}
    for record in steps_records:
        pkg = record.get("metadata", {}).get("dataOrigin", {}).get("packageName", "unknown")
        if pkg not in by_source:
            by_source[pkg] = []
        by_source[pkg].append(record)
    
    # Calculate total for each source (latest timestamp wins per source)
    source_totals = {}
    for pkg, records in by_source.items():
        # Get the record with latest endTime
        latest_record = max(records, key=lambda r: r.get("endTime", ""))
        # Sum all counts from that source up to that point
        total = sum(r.get("count", 0) for r in records if r.get("endTime", "") <= latest_record.get("endTime", ""))
        source_totals[pkg] = total
    
    # Pick the highest priority source that has data
    best_source = None
    best_priority = 999
    best_steps = 0
    
    for pkg, total in source_totals.items():
        priority = _get_source_priority(pkg)
        if priority < best_priority:
            best_priority = priority
            best_source = pkg
            best_steps = total
    
    # Build source info for logging
    sources = {}
    for pkg, records in by_source.items():
        sources[pkg] = {
            "priority": _get_source_priority(pkg),
            "count": len(records),
            "total": source_totals[pkg]
        }
    
    return {
        "steps": {"raw": raw_steps, "deduped": best_steps, "source": best_source},
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def _send_notification(sync_type: str, payload: RawHealthConnectIngest):
    """Send formatted sync notification to Telegram (v3 raw format)."""
    try:
        # Parse raw JSON to extract basic stats
        raw_data = json.loads(payload.raw_json)
        
        lines = [f"✅ {sync_type.title()} Sync (v3)", f"📅 {payload.date}"]
        
        # Extract step count from StepsRecord if available
        metrics = _calculate_deduped_metrics(raw_data)
        steps_info = metrics["steps"]
        if steps_info["deduped"] > 0:
            if steps_info["raw"] != steps_info["deduped"]:
                lines.append(f"🚶 {steps_info['deduped']:,} steps (raw: {steps_info['raw']:,})")
            else:
                lines.append(f"🚶 {steps_info['deduped']:,} steps")
            logger.info(f"Steps breakdown: {metrics['sources']}")
        
        # Count exercise sessions
        exercise_records = raw_data.get("ExerciseSessionRecord", [])
        if exercise_records:
            lines.append(f"💪 {len(exercise_records)} workout(s)")
        
        # Sum nutrition calories
        nutrition_records = raw_data.get("NutritionRecord", [])
        if nutrition_records:
            total_calories = sum(
                n.get("energy", {}).get("value", 0) / 1000  # Convert from milli-calories
                for n in nutrition_records
            )
            lines.append(f"🍽️ {total_calories:.0f} cal")
        
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": "\n".join(lines),
                "parse_mode": "HTML"
            }, timeout=5.0)
        
        logger.info(f"Telegram notification sent for {sync_type} sync")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


# ---------------------------------------------------------------------------
# Debug / Schema Discovery
# ---------------------------------------------------------------------------

@app.post("/v1/ingest/debug")
async def ingest_debug(
    payload: dict = Body(...),
    _: str = Depends(verify_api_key),
):
    """Raw schema capture for Health Connect development.
    
    Logs full JSON payload and returns it for inspection.
    Use this to discover actual field structure from watchdogbridge.
    """
    raw_json = json.dumps(payload, indent=2, default=str)
    logger.info(f"RAW HEALTH CONNECT PAYLOAD:\n{raw_json}")
    
    # Also save to a file for easy retrieval
    debug_file = f"/tmp/health_connect_debug_{payload.get('date', 'unknown')}_{datetime.now().isoformat()}.json"
    try:
        with open(debug_file, 'w') as f:
            f.write(raw_json)
    except Exception as e:
        logger.warning(f"Could not write debug file: {e}")
    
    return {
        "status": "debug_logged",
        "payload": payload,
        "size_bytes": len(raw_json),
        "top_level_keys": list(payload.keys()),
    }

@app.post("/v1/ingest/daily", response_model=IngestResponse)
async def ingest_daily(
    payload: RawHealthConnectIngest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Canonical daily ingestion with change-based history.
    
    For a given (device_id, date), inserts a new row only when payload content
    changes. Unchanged payloads are treated as no-op writes.
    """
    logger.info(f"Daily ingest: {payload.date} from {payload.source.device_id}")
    payload = _validate_raw_payload(payload, "daily")
    if payload.record_type is None:
        payload = payload.model_copy(update={"record_type": "daily"})
    payload_hash = payload.payload_hash or _canonical_payload_hash(payload.raw_json)
    row_id = payload.id or uuid.uuid4()

    existing_result = await db.execute(
        text("""
            SELECT id, payload_hash
            FROM health_connect_daily
            WHERE device_id = :device_id AND date = :date
            ORDER BY collected_at DESC, received_at DESC
            LIMIT 1
        """),
        {
            "device_id": payload.source.device_id,
            "date": payload.date,
        },
    )
    existing = existing_result.mappings().first()

    if existing and existing["payload_hash"] == payload_hash:
        logger.info(
            "Skipped daily insert (unchanged payload): date=%s device=%s",
            payload.date,
            payload.source.device_id,
        )
        return IngestResponse(inserted=False, id=existing["id"])

    await db.execute(
        text("""
            INSERT INTO health_connect_daily
                (id, device_id, date, collected_at, schema_version, source_app, raw_json, payload_hash, record_type)
            VALUES
                (:id, :device_id, :date, :collected_at, :schema_version, :source_app, :raw_json, :payload_hash, :record_type)
        """),
        {
            "id": row_id,
            "device_id": payload.source.device_id,
            "date": payload.date,
            "collected_at": payload.source.collected_at,
            "schema_version": str(payload.schema_version),
            "source_app": payload.source.source_app,
            "raw_json": payload.raw_json,
            "payload_hash": payload_hash,
            "record_type": payload.record_type or "daily",
        }
    )
    await db.commit()
    _log_db_write(
        endpoint="/v1/ingest/daily",
        operation="insert",
        table="health_connect_daily",
        device_id=payload.source.device_id,
        ingest_date=payload.date,
        collected_at=payload.source.collected_at,
        row_id=row_id,
        rows_affected=1,
    )

    asyncio.create_task(_send_notification("daily", payload))
    logger.info(f"Inserted daily record for {payload.date}")
    return IngestResponse(inserted=True, id=row_id)


@app.post("/v1/ingest/intraday", response_model=IngestResponse)
async def ingest_intraday(
    payload: RawHealthConnectIngest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Intraday snapshot ingestion — latest snapshot per day.
    
    Keeps one row per (device_id, date) in the intraday table by replacing
    the previous same-day snapshot on each sync. Does NOT touch daily table.
    """
    logger.info(f"Intraday ingest: {payload.date} from {payload.source.device_id}")
    payload = _validate_raw_payload(payload, "intraday")
    if payload.record_type is None:
        payload = payload.model_copy(update={"record_type": "intraday"})
    payload_hash = payload.payload_hash or _canonical_payload_hash(payload.raw_json)
    row_id = payload.id or uuid.uuid4()

    # Overwrite behavior: intraday should not accumulate within the same day.
    delete_result = await db.execute(
        text("""
            DELETE FROM health_connect_intraday_logs
            WHERE device_id = :device_id AND date = :date
        """),
        {
            "device_id": payload.source.device_id,
            "date": payload.date,
        }
    )

    result = await db.execute(
        text("""
            INSERT INTO health_connect_intraday_logs
                (id, device_id, date, collected_at, schema_version, source_app, raw_json, payload_hash, record_type)
            VALUES
                (:id, :device_id, :date, :collected_at, :schema_version, :source_app, :raw_json, :payload_hash, :record_type)
            RETURNING id
        """),
        {
            "id": row_id,
            "device_id": payload.source.device_id,
            "date": payload.date,
            "collected_at": payload.source.collected_at,
            "schema_version": str(payload.schema_version),
            "source_app": payload.source.source_app,
            "raw_json": payload.raw_json,
            "payload_hash": payload_hash,
            "record_type": payload.record_type or "intraday",
        }
    )
    await db.commit()
    inserted_id = result.scalar()
    _log_db_write(
        endpoint="/v1/ingest/intraday",
        operation="delete",
        table="health_connect_intraday_logs",
        device_id=payload.source.device_id,
        ingest_date=payload.date,
        collected_at=payload.source.collected_at,
        rows_affected=delete_result.rowcount or 0,
    )
    _log_db_write(
        endpoint="/v1/ingest/intraday",
        operation="insert",
        table="health_connect_intraday_logs",
        device_id=payload.source.device_id,
        ingest_date=payload.date,
        collected_at=payload.source.collected_at,
        row_id=inserted_id,
        rows_affected=1,
    )

    asyncio.create_task(_send_notification("intraday", payload))
    return IngestResponse(inserted=True, id=inserted_id)


# ---------------------------------------------------------------------------
# Query Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Health check with DB connectivity test."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "version": "2.0.0"}


@app.get("/v1/records/latest")
async def get_latest_record(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get latest canonical daily record.
    
    Returns the most recent daily record. Does NOT fall back to intraday —
    intraday is an audit log, not a source of truth.
    """
    result = await db.execute(
        text("""
            SELECT device_id, date, collected_at, received_at, schema_version, source_app, raw_json
            FROM health_connect_daily
            ORDER BY date DESC, collected_at DESC
            LIMIT 1
        """)
    )
    row = result.mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail="No daily records found")
    
    return {
        "device_id": row["device_id"],
        "date": row["date"].isoformat(),
        "collected_at": row["collected_at"].isoformat(),
        "received_at": row["received_at"].isoformat(),
        "schema_version": row["schema_version"],
        "source_app": row["source_app"],
        "data": row["raw_json"] if isinstance(row["raw_json"], dict) else json.loads(row["raw_json"]),
    }


@app.get("/v1/records/{date}")
async def get_record_by_date(
    date: str = Path(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get canonical daily record for specific date."""
    result = await db.execute(
        text("""
            SELECT device_id, date, collected_at, received_at, schema_version, source_app, raw_json
            FROM health_connect_daily
            WHERE date = :date
            ORDER BY received_at DESC
            LIMIT 1
        """),
        {"date": datetime.strptime(date, "%Y-%m-%d").date()},
    )
    row = result.mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"No record for {date}")
    
    return {
        "device_id": row["device_id"],
        "date": row["date"].isoformat(),
        "collected_at": row["collected_at"].isoformat(),
        "received_at": row["received_at"].isoformat(),
        "schema_version": row["schema_version"],
        "source_app": row["source_app"],
        "data": row["raw_json"] if isinstance(row["raw_json"], dict) else json.loads(row["raw_json"]),
    }


@app.get("/v1/records")
async def list_records(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """List canonical daily records within date range."""
    result = await db.execute(
        text("""
            SELECT device_id, date, collected_at, received_at, schema_version, source_app, raw_json
            FROM health_connect_daily
            WHERE date >= :start_date AND date <= :end_date
            ORDER BY date ASC
        """),
        {"start_date": datetime.strptime(start_date, "%Y-%m-%d").date(), "end_date": datetime.strptime(end_date, "%Y-%m-%d").date()},
    )
    rows = result.mappings().all()
    
    return {
        "count": len(rows),
        "records": [
            {
                "device_id": r["device_id"],
                "date": r["date"].isoformat(),
                "collected_at": r["collected_at"].isoformat(),
                "received_at": r["received_at"].isoformat(),
                "schema_version": r["schema_version"],
                "source_app": r["source_app"],
                "data": r["raw_json"] if isinstance(r["raw_json"], dict) else json.loads(r["raw_json"]),
            }
            for r in rows
        ],
    }


@app.get("/v1/logs")
async def get_intraday_logs(
    date: py_date | None = None,
    device_id: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Query latest intraday snapshots (one row per device/date).
    
    Use for inspecting the current intraday state.
    Results ordered by collected_at DESC (newest first).
    """
    conditions = []
    params = {"limit": limit}
    
    if date:
        conditions.append("date = :date")
        params["date"] = date
    
    if device_id:
        conditions.append("device_id = :device_id")
        params["device_id"] = device_id
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    result = await db.execute(
        text(f"""
            SELECT id, device_id, date, collected_at, received_at, schema_version, source_app, raw_json
            FROM health_connect_intraday_logs
            {where_clause}
            ORDER BY collected_at DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()
    
    return {
        "count": len(rows),
        "logs": [
            {
                "id": str(r["id"]),
                "device_id": r["device_id"],
                "date": r["date"].isoformat(),
                "collected_at": r["collected_at"].isoformat(),
                "received_at": r["received_at"].isoformat(),
                "schema_version": r["schema_version"],
                "source_app": r["source_app"],
                "data": r["raw_json"] if isinstance(r["raw_json"], dict) else json.loads(r["raw_json"]),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Create tables on startup (dev mode). Use Alembic in production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created (if not exists)")
