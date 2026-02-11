import uuid

from sqlalchemy import Column, Integer, String, Date, DateTime, UniqueConstraint, func
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
    body_metrics = Column(JSONB, nullable=True)
    nutrition_summary = Column(JSONB, nullable=True)
    exercise_sessions = Column(JSONB, nullable=True)
    source = Column(JSONB, nullable=False)

    # "daily" = canonical/final, "intraday" = provisional/hot
    source_type = Column(String, nullable=False, server_default="daily")

    collected_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "date",
            "schema_version",
            name="uq_device_date_version",
        ),
    )
