from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WatermarkSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(default="DRAFT", min_length=1, max_length=60)
    color: str = Field(default="#64746c", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=0.2, ge=0.05, le=1)
    font_size: int = Field(default=60, ge=12, le=120)
    rotation: int = Field(default=45, ge=-90, le=90)
    position: Literal["center", "top", "bottom"] = "center"
    template_id: Literal["draft", "confidential", "sample", "copyright", "personalized", "custom"] = "draft"
    schema_version: Literal[1] = 1

    @field_validator("text")
    @classmethod
    def supported_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 or ord(character) > 126 for character in value):
            raise ValueError("Use printable English letters, numbers, and symbols in this first release.")
        return value


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    request_id: UUID
    operation: Literal["add"] = "add"
    settings: WatermarkSettings


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    job_id: UUID
    correlation_id: UUID
    schema_version: Literal[1]
    type: Literal["ProcessingRequested", "ProcessingStarted", "ProcessingCompleted", "ProcessingFailed", "PreviewRequested", "PreviewReady", "PreviewFailed"]
    timestamp: datetime
    data: dict


def event(kind: str, job_id: str, data: dict) -> dict:
    return Event(
        event_id=uuid4(), job_id=job_id, correlation_id=job_id,
        schema_version=1, type=kind, timestamp=datetime.now(timezone.utc), data=data,
    ).model_dump(mode="json")

