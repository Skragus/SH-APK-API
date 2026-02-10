from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SourceSchema(BaseModel):
    device_id: str
    collected_at: datetime

    model_config = {"extra": "allow"}


class DailyIngestRequest(BaseModel):
    schema_version: int = Field(default=1)
    date: date
    steps_total: int
    source: SourceSchema
    sleep_sessions: Optional[Union[Dict[str, Any], List[Any]]] = None
    heart_rate_summary: Optional[Union[Dict[str, Any], List[Any]]] = None

    @field_validator("steps_total")
    @classmethod
    def validate_steps(cls, v: int) -> int:
        if v < 0:
            raise ValueError("steps_total cannot be negative")
        return v

    @field_validator("date")
    @classmethod
    def validate_date_not_future(cls, v: date) -> date:
        if v > datetime.now(timezone.utc).date():
            raise ValueError("Date cannot be in the future")
        return v


class IngestResponse(BaseModel):
    status: str = "ok"
    upserted: bool = True
