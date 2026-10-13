import hashlib
import json
import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_role
from app.core.database import get_db
from app.events.outbox import TransactionalOutbox
from app.events.schemas import (
    DomainEvent,
    RideAcceptedEvent,
    RideCancelledEvent,
    RideCompletedEvent,
    RideRequestedEvent,
)
from app.models import (
    Driver,
    DriverStatus,
    IdempotencyKey,
    Ride,
    RideEvent,
    RideStatus,
    User,
    UserRole,
)
from app.schemas import (
    FareEstimateRequest,
    FareEstimateResponse,
    RideCancelRequest,
    RideCreateRequest,
    RideResponse,
)
from app.services.lifecycle import validate_and_apply_transition
from app.services.pricing import calculate_fare, haversine_distance_km

router = APIRouter(prefix="/rides", tags=["Rides"])


@router.post("/estimate", response_model=FareEstimateResponse)
async def estimate_fare(req: FareEstimateRequest):
    distance = haversine_distance_km(
        req.pickup.latitude, req.pickup.longitude, req.dropoff.latitude, req.dropoff.longitude
    )
    return calculate_fare(distance)


@router.post("", response_model=RideResponse, status_code=status.HTTP_201_CREATED)
async def create_ride(
    req: RideCreateRequest,
    current_user: User = Depends(require_role(UserRole.RIDER)),
    db: AsyncSession = Depends(get_db),
):
    # Compute deterministic SHA-256 payload hash
    payload_dict = {
        "pickup_latitude": float(req.pickup_latitude),
        "pickup_longitude": float(req.pickup_longitude),
        "pickup_address": str(req.pickup_address),
        "dropoff_latitude": float(req.dropoff_latitude),
        "dropoff_longitude": float(req.dropoff_longitude),
        "dropoff_address": str(req.dropoff_address),
    }
    payload_hash = hashlib.sha256(
        json.dumps(payload_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    # 1. Idempotency check if key provided
    if req.idempotency_key:
        stmt = select(IdempotencyKey).where(
            and_(
                IdempotencyKey.user_id == current_user.id, IdempotencyKey.key == req.idempotency_key
            )
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            # Always validate hash on replay — including concurrent conflict paths
            if existing.payload_hash and existing.payload_hash != payload_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reused with different request payload.",
                )
            # Replay: return 200 (not 201) to signal cached response
            return Response(
                content=existing.response_body,
                status_code=status.HTTP_200_OK,
                media_type="application/json",
            )

    # 2. Check if rider already has an active ongoing ride
    active_ride_stmt = select(Ride).where(
        and_(
            Ride.rider_id == current_user.id,
            Ride.status.in_(
                [
                    RideStatus.REQUESTED,
                    RideStatus.MATCHING,
                    RideStatus.ACCEPTED,
                    RideStatus.ARRIVED,
                    RideStatus.IN_PROGRESS,
                ]
            ),
        )
    )
    active_ride = (await db.execute(active_ride_stmt)).scalar_one_or_none()
    if active_ride:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active ride request in progress.",
        )

    # 3. Calculate fare
    distance = haversine_distance_km(
        req.pickup_latitude, req.pickup_longitude, req.dropoff_latitude, req.dropoff_longitude
    )
    estimate = calculate_fare(distance)

    ride = Ride(
        rider_id=current_user.id,
        status=RideStatus.REQUESTED,
        pickup_latitude=req.pickup_latitude,
        pickup_longitude=req.pickup_longitude,
        pickup_address=req.pickup_address,
        dropoff_latitude=req.dropoff_latitude,
        dropoff_longitude=req.dropoff_longitude,
        dropoff_address=req.dropoff_address,
        estimated_fare=estimate.total_fare,
        currency="USD",
    )
    db.add(ride)
    await db.flush()

    # Record ride lifecycle event
    db.add(RideEvent(
        ride_id=ride.id,
        event_type="RIDE_REQUESTED",
        actor_role=current_user.role.value,
        actor_id=current_user.id,
        metadata_json={"estimated_fare": float(estimate.total_fare), "distance_km": distance},
    ))

    # --- Transactional Outbox: write domain event in the SAME transaction ---
    await TransactionalOutbox.record_event(
        db,
        RideRequestedEvent(
            aggregate_id=str(ride.id),
            payload={
                "ride_id": str(ride.id),
                "rider_id": str(current_user.id),
                "pickup_address": req.pickup_address,
                "dropoff_address": req.dropoff_address,
                "estimated_fare": float(estimate.total_fare),
            },
        ),
    )

    # Store idempotency record if requested
    if req.idempotency_key:
        response_data = RideResponse.model_validate(ride).model_dump(mode="json")
        idemp_record = IdempotencyKey(
            user_id=current_user.id,
            key=req.idempotency_key,
            request_path="/api/v1/rides",
            payload_hash=payload_hash,
            response_status=201,
            response_body=json.dumps(response_data),
        )
        db.add(idemp_record)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Handle concurrent retry race with identical idempotency key
        if req.idempotency_key:
            stmt = select(IdempotencyKey).where(
                and_(
                    IdempotencyKey.user_id == current_user.id,
                    IdempotencyKey.key == req.idempotency_key,
                )
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                # Re-validate payload hash even on the conflict retry path
                if existing.payload_hash and existing.payload_hash != payload_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key reused with different request payload.",
                    )
                return Response(
                    content=existing.response_body,
                    status_code=status.HTTP_200_OK,
                    media_type="application/json",
                )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict processing request.",
        )

    await db.refresh(ride)
    return ride


@router.get("/{ride_id}", response_model=RideResponse)
async def get_ride_details(
    ride_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ride).where(Ride.id == ride_id)
    ride = (await db.execute(stmt)).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    # Authorization check
    if current_user.role != UserRole.ADMIN and current_user.id != ride.rider_id:
        driver_stmt = select(Driver).where(Driver.user_id == current_user.id)
        driver = (await db.execute(driver_stmt)).scalar_one_or_none()
        if not driver or ride.driver_id != driver.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this ride."
            )

    return ride


@router.post("/{ride_id}/accept", response_model=RideResponse)
async def accept_ride(
    ride_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    # Atomic row-lock on driver
    driver_stmt = select(Driver).where(Driver.user_id == current_user.id).with_for_update()
    driver = (await db.execute(driver_stmt)).scalar_one_or_none()
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Driver profile not found."
        )

    if driver.status != DriverStatus.ONLINE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Driver is not available to accept rides (must be ONLINE).",
        )

    # Atomic row-lock on ride
    ride_stmt = select(Ride).where(Ride.id == ride_id).with_for_update()
    ride = (await db.execute(ride_stmt)).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    # Validate transition through domain state machine
    validate_and_apply_transition(ride, RideStatus.ACCEPTED)

    # Concurrency safe assignment
    ride.driver_id = driver.id
    driver.status = DriverStatus.BUSY

    db.add(RideEvent(
        ride_id=ride.id,
        event_type="RIDE_ACCEPTED",
        actor_role=current_user.role.value,
        actor_id=driver.id,
    ))

    # --- Transactional Outbox: same transaction as ride state change ---
    await TransactionalOutbox.record_event(
        db,
        RideAcceptedEvent(
            aggregate_id=str(ride.id),
            payload={
                "ride_id": str(ride.id),
                "driver_id": str(driver.id),
                "rider_id": str(ride.rider_id),
            },
        ),
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Driver already assigned to an active ride or concurrent assignment conflict.",
        )

    await db.refresh(ride)
    return ride


@router.post("/{ride_id}/arrive", response_model=RideResponse)
async def arrive_ride(
    ride_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    ride = (
        await db.execute(select(Ride).where(Ride.id == ride_id).with_for_update())
    ).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    driver = (
        await db.execute(select(Driver).where(Driver.user_id == current_user.id))
    ).scalar_one_or_none()
    if not driver or ride.driver_id != driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned driver."
        )

    validate_and_apply_transition(ride, RideStatus.ARRIVED)
    db.add(RideEvent(
        ride_id=ride.id, event_type="DRIVER_ARRIVED", actor_role="DRIVER", actor_id=driver.id
    ))
    await db.commit()
    await db.refresh(ride)
    return ride


@router.post("/{ride_id}/start", response_model=RideResponse)
async def start_ride(
    ride_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    ride = (
        await db.execute(select(Ride).where(Ride.id == ride_id).with_for_update())
    ).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    driver = (
        await db.execute(select(Driver).where(Driver.user_id == current_user.id))
    ).scalar_one_or_none()
    if not driver or ride.driver_id != driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned driver."
        )

    validate_and_apply_transition(ride, RideStatus.IN_PROGRESS)
    db.add(RideEvent(
        ride_id=ride.id, event_type="TRIP_STARTED", actor_role="DRIVER", actor_id=driver.id
    ))
    await db.commit()
    await db.refresh(ride)
    return ride


@router.post("/{ride_id}/complete", response_model=RideResponse)
async def complete_ride(
    ride_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    ride = (
        await db.execute(select(Ride).where(Ride.id == ride_id).with_for_update())
    ).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    driver = (
        await db.execute(
            select(Driver).where(Driver.user_id == current_user.id).with_for_update()
        )
    ).scalar_one_or_none()
    if not driver or ride.driver_id != driver.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not the assigned driver."
        )

    validate_and_apply_transition(ride, RideStatus.COMPLETED)
    driver.status = DriverStatus.ONLINE  # Driver becomes available again

    db.add(RideEvent(
        ride_id=ride.id, event_type="TRIP_COMPLETED", actor_role="DRIVER", actor_id=driver.id
    ))

    # --- Transactional Outbox ---
    await TransactionalOutbox.record_event(
        db,
        RideCompletedEvent(
            aggregate_id=str(ride.id),
            payload={
                "ride_id": str(ride.id),
                "driver_id": str(driver.id),
                "rider_id": str(ride.rider_id),
                "final_fare": float(ride.final_fare or ride.estimated_fare),
            },
        ),
    )

    await db.commit()
    await db.refresh(ride)
    return ride


@router.post("/{ride_id}/cancel", response_model=RideResponse)
async def cancel_ride(
    ride_id: uuid.UUID,
    req: RideCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ride = (
        await db.execute(select(Ride).where(Ride.id == ride_id).with_for_update())
    ).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found.")

    # Only rider, assigned driver, or admin can cancel
    driver = (
        await db.execute(select(Driver).where(Driver.user_id == current_user.id))
    ).scalar_one_or_none()
    is_rider = ride.rider_id == current_user.id
    is_driver = driver and ride.driver_id == driver.id
    is_admin = current_user.role == UserRole.ADMIN

    if not (is_rider or is_driver or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to cancel this ride."
        )

    validate_and_apply_transition(ride, RideStatus.CANCELLED, cancellation_reason=req.reason)

    # Release driver back to ONLINE if assigned
    if ride.driver_id:
        assigned_driver = (
            await db.execute(
                select(Driver).where(Driver.id == ride.driver_id).with_for_update()
            )
        ).scalar_one_or_none()
        if assigned_driver:
            assigned_driver.status = DriverStatus.ONLINE

    db.add(RideEvent(
        ride_id=ride.id,
        event_type="RIDE_CANCELLED",
        actor_role=current_user.role.value,
        actor_id=current_user.id,
        metadata_json={"reason": req.reason},
    ))

    # --- Transactional Outbox ---
    await TransactionalOutbox.record_event(
        db,
        RideCancelledEvent(
            aggregate_id=str(ride.id),
            payload={
                "ride_id": str(ride.id),
                "cancelled_by_role": current_user.role.value,
                "reason": req.reason,
            },
        ),
    )

    await db.commit()
    await db.refresh(ride)
    return ride


@router.get("/me/history", response_model=list[RideResponse])
async def get_my_ride_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == UserRole.DRIVER:
        driver = (
            await db.execute(select(Driver).where(Driver.user_id == current_user.id))
        ).scalar_one_or_none()
        if not driver:
            return []
        stmt = select(Ride).where(Ride.driver_id == driver.id).order_by(Ride.requested_at.desc())
    else:
        stmt = (
            select(Ride).where(Ride.rider_id == current_user.id).order_by(Ride.requested_at.desc())
        )

    result = await db.execute(stmt)
    return result.scalars().all()
