import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    aggregate_type: str = "RIDE"
    aggregate_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any]


class RideRequestedEvent(DomainEvent):
    event_type: str = "ride.requested"


class RideAcceptedEvent(DomainEvent):
    event_type: str = "ride.accepted"


class RideCompletedEvent(DomainEvent):
    event_type: str = "ride.completed"


class RideCancelledEvent(DomainEvent):
    event_type: str = "ride.cancelled"
