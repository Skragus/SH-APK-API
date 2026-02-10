Here is a complete, production-ready implementation using **FastAPI**, **SQLAlchemy (Async)**, and **PostgreSQL**. It includes the data model, validation logic, idempotent upsert strategy, and Docker configuration for Railway.

### Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   └── schemas.py
├── alembic/
├── alembic.ini
├── Dockerfile
└── requirements.txt
```

---

### 1. Configuration & Dependencies

**`requirements.txt`**
```text
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic[email]==2.6.0
pydantic-settings==2.1.0
sqlalchemy==2.0.25
alembic==1.13.1
asyncpg==0.29.0
python-dotenv==1.0.1
```

**`app/config.py`**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()
```

---

### 2. Database Setup

**`app/database.py`**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Ensure we use the async driver
db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

### 3. Database Model (SQLAlchemy)

**`app/models.py`**
```python
import uuid
from sqlalchemy import Column, Integer, String, Date, DateTime, JSON, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

class ShealthDaily(Base):
    __tablename__ = "shealth_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    
    steps_total = Column(Integer, nullable=False)
    sleep_sessions = Column(JSONB, nullable=True)
    heart_rate_summary = Column(JSONB, nullable=True)
    source = Column(JSONB, nullable=False)
    
    collected_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('device_id', 'date', 'schema_version', name='uq_device_date_version'),
    )
```

---

### 4. Schemas & Validation (Pydantic)

**`app/schemas.py`**
```python
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

class SourceSchema(BaseModel):
    device_id: str
    collected_at: datetime
    # Allow extra fields in source to be flexible
    model_config = {"extra": "allow"}

class DailyIngestRequest(BaseModel):
    schema_version: int = Field(default=1)
    date: date
    steps_total: int
    source: SourceSchema
    sleep_sessions: Optional[Dict[str, Any] | list] = None
    heart_rate_summary: Optional[Dict[str, Any] | list] = None

    @field_validator('steps_total')
    @classmethod
    def validate_steps(cls, v):
        if v < 0:
            raise ValueError('steps_total cannot be negative')
        return v

    @field_validator('date')
    @classmethod
    def validate_date_not_future(cls, v):
        # Simple check against UTC date
        if v > datetime.now(timezone.utc).date():
            raise ValueError('Date cannot be in the future')
        return v
```

---

### 5. API Logic (Main Application)

**`app/main.py`**
```python
import logging
from fastapi import FastAPI, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.database import get_db, engine, Base
from app.config import settings
from app.schemas import DailyIngestRequest
from app.models import ShealthDaily

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shealth-ingest")

app = FastAPI(title="Samsung Health Truth Layer")

# Security Dependency
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return x_api_key

@app.post("/v1/ingest/shealth/daily", status_code=200)
async def ingest_daily_stats(
    payload: DailyIngestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key)
):
    # Prepare data for DB
    ingest_data = {
        "device_id": payload.source.device_id,
        "date": payload.date,
        "schema_version": payload.schema_version,
        "steps_total": payload.steps_total,
        "sleep_sessions": payload.sleep_sessions,
        "heart_rate_summary": payload.heart_rate_summary,
        "source": payload.source.model_dump(mode='json'),
        "collected_at": payload.source.collected_at
    }

    # Construct Idempotent Upsert (On Conflict Do Update)
    stmt = insert(ShealthDaily).values(**ingest_data)
    
    stmt = stmt.on_conflict_do_update(
        constraint='uq_device_date_version',
        set_={
            "steps_total": stmt.excluded.steps_total,
            "sleep_sessions": stmt.excluded.sleep_sessions,
            "heart_rate_summary": stmt.excluded.heart_rate_summary,
            "source": stmt.excluded.source,
            "collected_at": stmt.excluded.collected_at,
            # We assume 'received_at' should represent the INITIAL ingestion time, 
            # so we do NOT update it. If you want it to update on every sync, add it here.
        }
    )

    try:
        await db.execute(stmt)
        await db.commit()
        
        logger.info(
            f"Ingest Success: device={payload.source.device_id} date={payload.date} "
            f"steps={payload.steps_total} status=upserted"
        )
        
        return {"status": "ok", "upserted": True}

    except Exception as e:
        logger.error(f"Ingest Failed: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error during upsert")

# Startup event to create tables (for dev/testing only - use Alembic in prod)
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to reset
        await conn.run_sync(Base.metadata.create_all)
```

---

### 6. Deployment Files

**`Dockerfile`**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7. Database Migrations (Alembic)

While the `startup` event in `main.py` creates tables, in production it is better to use Alembic.

1.  **Initialize:** `alembic init -t async alembic`
2.  **Edit `alembic/env.py`:** Import your `Base` and `settings` to set `target_metadata` and the DB URL.
3.  **Generate Migration:** `alembic revision --autogenerate -m "Initial schema"`
4.  **Run Migration:** `alembic upgrade head`

### Usage on Railway

1.  **New Service:** Create a new service from this GitHub repo.
2.  **Database:** Add a PostgreSQL plugin.
3.  **Variables:** Set the environment variables in Railway:
    *   `DATABASE_URL`: (Railway provides this automatically)
    *   `API_KEY`: `your_super_secret_key`

### Testing the Endpoint

```bash
curl -X POST https://your-app.up.railway.app/v1/ingest/shealth/daily \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_super_secret_key" \
  -d '{
    "schema_version": 1,
    "date": "2023-10-27",
    "steps_total": 8500,
    "source": {
        "device_id": "android_12345",
        "collected_at": "2023-10-27T23:55:00Z"
    },
    "sleep_sessions": {"total_minutes": 420},
    "heart_rate_summary": {"avg": 72, "min": 60, "max": 120}
  }'
```