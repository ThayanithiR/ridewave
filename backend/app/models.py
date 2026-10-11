import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, Enum):
    RIDER = "RIDER"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"


class DriverStatus(str, Enum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    BUSY = "BUSY"


class RideStatus(str, Enum):
    REQUESTED = "REQUESTED"
    MATCHING = "MATCHING"
    ACCEPTED = "ACCEPTED"
    ARRIVED = "ARRIVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role_enum"), default=UserRole.RIDER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    driver_profile: Mapped[Optional["Driver"]] = relationship(
        "Driver", back_populates="user", uselist=False
    )
    rides_as_rider: Mapped[list["Ride"]] = relationship(
        "Ride", back_populates="rider", foreign_keys="[Ride.rider_id]"
    )


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[DriverStatus] = mapped_column(
        SAEnum(DriverStatus, name="driver_status_enum"),
        default=DriverStatus.OFFLINE,
        nullable=False,
    )
    vehicle_make: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_model: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_plate: Mapped[str] = mapped_column(String(50), nullable=False)
    last_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_location_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="driver_profile")
    rides: Mapped[list["Ride"]] = relationship(
        "Ride", back_populates="driver", foreign_keys="[Ride.driver_id]"
    )


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=True, index=True
    )
    status: Mapped[RideStatus] = mapped_column(
        SAEnum(RideStatus, name="ride_status_enum"),
        default=RideStatus.REQUESTED,
        nullable=False,
        index=True,
    )

    pickup_latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    pickup_longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    pickup_address: Mapped[str] = mapped_column(String(255), nullable=False)

    dropoff_latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    dropoff_longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    dropoff_address: Mapped[str] = mapped_column(String(255), nullable=False)

    estimated_fare: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    final_fare: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rider: Mapped["User"] = relationship(
        "User", back_populates="rides_as_rider", foreign_keys=[rider_id]
    )
    driver: Mapped[Optional["Driver"]] = relationship(
        "Driver", back_populates="rides", foreign_keys=[driver_id]
    )
    events: Mapped[list["RideEvent"]] = relationship(
        "RideEvent", back_populates="ride", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Invariant: Driver cannot have two active rides
        Index(
            "idx_driver_single_active_ride",
            "driver_id",
            unique=True,
            postgresql_where=(
                status.in_([RideStatus.ACCEPTED, RideStatus.ARRIVED, RideStatus.IN_PROGRESS])
            ),
        ),
    )


class RideEvent(Base):
    __tablename__ = "ride_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    ride: Mapped["Ride"] = relationship("Ride", back_populates="events")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    request_path: Mapped[str] = mapped_column(String(255), nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_idempotency_key"),)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(50), default="RIDE", nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )  # PENDING, PUBLISHED, FAILED
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
