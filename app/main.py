import logging

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

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


@app.post("/v1/ingest/shealth/daily", response_model=IngestResponse)
async def ingest_daily_stats(
    payload: DailyIngestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    ingest_data = {
        "device_id": payload.source.device_id,
        "date": payload.date,
        "schema_version": payload.schema_version,
        "steps_total": payload.steps_total,
        "sleep_sessions": payload.sleep_sessions,
        "heart_rate_summary": payload.heart_rate_summary.model_dump(mode="json")
        if payload.heart_rate_summary
        else None,
        "body_metrics": payload.body_metrics.model_dump(mode="json")
        if payload.body_metrics
        else None,
        "nutrition_summary": payload.nutrition_summary.model_dump(mode="json")
        if payload.nutrition_summary
        else None,
        "exercise_sessions": payload.exercise_sessions,
        "source": payload.source.model_dump(mode="json"),
        "collected_at": payload.source.collected_at,
    }

    # Idempotent upsert — on conflict update everything except received_at
    stmt = insert(ShealthDaily).values(**ingest_data)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_device_date_version",
        set_={
            "steps_total": stmt.excluded.steps_total,
            "sleep_sessions": stmt.excluded.sleep_sessions,
            "heart_rate_summary": stmt.excluded.heart_rate_summary,
            "body_metrics": stmt.excluded.body_metrics,
            "nutrition_summary": stmt.excluded.nutrition_summary,
            "exercise_sessions": stmt.excluded.exercise_sessions,
            "source": stmt.excluded.source,
            "collected_at": stmt.excluded.collected_at,
        },
    )

    try:
        await db.execute(stmt)
        await db.commit()
        logger.info(
            "Ingest OK: device=%s date=%s steps=%d",
            payload.source.device_id,
            payload.date,
            payload.steps_total,
        )
        return IngestResponse()
    except Exception as e:
        logger.error("Ingest failed: %s", e)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during upsert",
        )


# ---------------------------------------------------------------------------
# Startup — create tables (dev only; use Alembic in prod)
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
