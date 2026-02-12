import logging

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, case

from app.config import settings
from app.database import Base, engine, get_db
from app.models import ShealthDaily
from app.schemas import DailyIngestRequest, IngestResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shealth-ingest")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Samsung Health Truth Layer")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/debug/status")
async def debug_status(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Debug endpoint to check database status and recent ingests."""
    try:
        # Total record count
        count_result = await db.execute(
            text("SELECT COUNT(*) as total FROM shealth_daily")
        )
        total_records = count_result.scalar()

        # Count by source type
        type_result = await db.execute(
            text("""
                SELECT source_type, COUNT(*) as count 
                FROM shealth_daily 
                GROUP BY source_type
            """)
        )
        by_type = {row[0]: row[1] for row in type_result.fetchall()}

        # Last 10 records
        recent_result = await db.execute(
            text("""
                SELECT date, device_id, steps_total, source_type, 
                       collected_at, received_at
                FROM shealth_daily 
                ORDER BY received_at DESC 
                LIMIT 10
            """)
        )
        recent_records = [
            {
                "date": str(row[0]),
                "device_id": row[1],
                "steps_total": row[2],
                "source_type": row[3],
                "collected_at": row[4].isoformat() if row[4] else None,
                "received_at": row[5].isoformat() if row[5] else None,
            }
            for row in recent_result.fetchall()
        ]

        # Last ingest timestamp
        last_ingest = recent_records[0]["received_at"] if recent_records else None

        return {
            "status": "ok",
            "total_records": total_records,
            "by_source_type": by_type,
            "last_ingest_at": last_ingest,
            "recent_ingests": recent_records,
        }
    except Exception as e:
        logger.error("Debug status failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Shared upsert helper
# ---------------------------------------------------------------------------
def _serialize_optional(obj):
    """model_dump a Pydantic object if present, else None."""
    return obj.model_dump(mode="json") if obj else None


async def _upsert_shealth(
    payload: DailyIngestRequest,
    source_type: str,
    db: AsyncSession,
):
    """Build and execute an idempotent upsert for shealth_daily."""
    ingest_data = {
        "device_id": payload.source.device_id,
        "date": payload.date,
        "schema_version": payload.schema_version,
        "steps_total": payload.steps_total,
        "sleep_sessions": payload.sleep_sessions,
        "heart_rate_summary": _serialize_optional(payload.heart_rate_summary),
        "body_metrics": _serialize_optional(payload.body_metrics),
        "nutrition_summary": _serialize_optional(payload.nutrition_summary),
        "exercise_sessions": [
            s.model_dump(mode="json") for s in payload.exercise_sessions
        ]
        if payload.exercise_sessions
        else None,
        "source": payload.source.model_dump(mode="json"),
        "source_type": source_type,
        "collected_at": payload.source.collected_at,
    }

    # Idempotent upsert — on conflict update ONLY if new data is fresher (newer collected_at)
    # This protects against Android sending stale/incomplete data after fresh data
    stmt = insert(ShealthDaily).values(**ingest_data)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_device_date_version",
        set_={
            "steps_total": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.steps_total),
                else_=ShealthDaily.steps_total
            ),
            "sleep_sessions": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.sleep_sessions),
                else_=ShealthDaily.sleep_sessions
            ),
            "heart_rate_summary": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.heart_rate_summary),
                else_=ShealthDaily.heart_rate_summary
            ),
            "body_metrics": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.body_metrics),
                else_=ShealthDaily.body_metrics
            ),
            "nutrition_summary": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.nutrition_summary),
                else_=ShealthDaily.nutrition_summary
            ),
            "exercise_sessions": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.exercise_sessions),
                else_=ShealthDaily.exercise_sessions
            ),
            "source": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.source),
                else_=ShealthDaily.source
            ),
            "source_type": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.source_type),
                else_=ShealthDaily.source_type
            ),
            "collected_at": case(
                (stmt.excluded.collected_at > ShealthDaily.collected_at, stmt.excluded.collected_at),
                else_=ShealthDaily.collected_at
            ),
        },
    )

    try:
        await db.execute(stmt)
        await db.commit()
        logger.info(
            "Ingest OK [%s]: device=%s date=%s steps=%d",
            source_type,
            payload.source.device_id,
            payload.date,
            payload.steps_total,
        )
        return IngestResponse()
    except Exception as e:
        logger.error("Ingest failed [%s]: %s", source_type, e)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during upsert",
        )


# ---------------------------------------------------------------------------
# Daily — canonical/final reconciliation for past dates
# ---------------------------------------------------------------------------
@app.post("/v1/ingest/shealth/daily", response_model=IngestResponse)
async def ingest_daily(
    payload: DailyIngestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return await _upsert_shealth(payload, source_type="daily", db=db)


# ---------------------------------------------------------------------------
# Intraday — provisional/hot cumulative snapshot for today
# ---------------------------------------------------------------------------
@app.post("/v1/ingest/shealth/intraday", response_model=IngestResponse)
async def ingest_intraday(
    payload: DailyIngestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return await _upsert_shealth(payload, source_type="intraday", db=db)


# ---------------------------------------------------------------------------
# Startup — create tables (dev only; use Alembic in prod)
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
