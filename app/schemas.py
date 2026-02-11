from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SourceSchema(BaseModel):
    device_id: str
    collected_at: datetime

    model_config = {"extra": "allow"}


class BodyMetricsSchema(BaseModel):
    weight_kg: Optional[float] = None
    body_fat_percentage: Optional[float] = None

    model_config = {"extra": "ignore"}


class NutritionSummarySchema(BaseModel):
    calories_total: Optional[int] = None
    protein_grams: Optional[float] = None

    model_config = {"extra": "ignore"}


class ExerciseSessionSchema(BaseModel):
    start_time: str
    end_time: str
    duration_minutes: int
    title: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class HeartRateSummarySchema(BaseModel):
    avg_hr: Optional[int] = None
    min_hr: Optional[int] = None
    max_hr: Optional[int] = None
    resting_hr: Optional[int] = None

    # Allow forward compatibility if we ever add more fields on the client
    model_config = {"extra": "allow"}


class DailyIngestRequest(BaseModel):
    schema_version: int = Field(default=1)
    date: date
    steps_total: int
    source: SourceSchema
    sleep_sessions: Optional[Union[Dict[str, Any], List[Any]]] = None
    heart_rate_summary: Optional[HeartRateSummarySchema] = None
    body_metrics: Optional[BodyMetricsSchema] = None
    nutrition_summary: Optional[NutritionSummarySchema] = None
    exercise_sessions: Optional[List[ExerciseSessionSchema]] = None

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
