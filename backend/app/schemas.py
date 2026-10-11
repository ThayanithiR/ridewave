import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import DriverStatus, RideStatus, UserRole


# --- Auth Schemas ---
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: UserRole = UserRole.RIDER


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    role: UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True


# --- Driver Schemas ---
class DriverRegisterRequest(BaseModel):
    vehicle_make: str
    vehicle_model: str
    vehicle_plate: str


class DriverResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: DriverStatus
    vehicle_make: str
    vehicle_model: str
    vehicle_plate: str
    last_latitude: float | None = None
    last_longitude: float | None = None

    class Config:
        from_attributes = True


class DriverStatusUpdateRequest(BaseModel):
    status: DriverStatus


# --- Ride Schemas ---
class Coordinate(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class FareEstimateRequest(BaseModel):
    pickup: Coordinate
    dropoff: Coordinate


class FareEstimateResponse(BaseModel):
    distance_km: float
    estimated_duration_minutes: float
    base_fare: float
    distance_fare: float
    time_fare: float
    total_fare: float
    currency: str = "USD"


class RideCreateRequest(BaseModel):
    pickup_latitude: float = Field(ge=-90.0, le=90.0)
    pickup_longitude: float = Field(ge=-180.0, le=180.0)
    pickup_address: str
    dropoff_latitude: float = Field(ge=-90.0, le=90.0)
    dropoff_longitude: float = Field(ge=-180.0, le=180.0)
    dropoff_address: str
    idempotency_key: str | None = None


class RideResponse(BaseModel):
    id: uuid.UUID
    rider_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    status: RideStatus
    pickup_latitude: float
    pickup_longitude: float
    pickup_address: str
    dropoff_latitude: float
    dropoff_longitude: float
    dropoff_address: str
    estimated_fare: float
    final_fare: float | None = None
    currency: str
    requested_at: datetime
    accepted_at: datetime | None = None
    picked_up_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    class Config:
        from_attributes = True


class RideCancelRequest(BaseModel):
    reason: str | None = "Rider requested cancellation"
