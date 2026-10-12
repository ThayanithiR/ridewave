from datetime import UTC, datetime
from typing import Set

from fastapi import HTTPException, status

from app.models import Ride, RideStatus

# Explicit transition matrix: current_status -> set of allowable next_statuses
PERMITTED_TRANSITIONS: dict[RideStatus, Set[RideStatus]] = {
    RideStatus.REQUESTED: {RideStatus.MATCHING, RideStatus.ACCEPTED, RideStatus.CANCELLED},
    RideStatus.MATCHING: {RideStatus.ACCEPTED, RideStatus.CANCELLED},
    RideStatus.ACCEPTED: {RideStatus.ARRIVED, RideStatus.CANCELLED},
    RideStatus.ARRIVED: {RideStatus.IN_PROGRESS, RideStatus.CANCELLED},
    RideStatus.IN_PROGRESS: {RideStatus.COMPLETED},
    RideStatus.COMPLETED: set(),  # Terminal state
    RideStatus.CANCELLED: set(),  # Terminal state
}


def validate_and_apply_transition(
    ride: Ride,
    target_status: RideStatus,
    cancellation_reason: str | None = None,
) -> None:
    """
    Enforces atomic state machine transitions and updates relevant audit timestamps.
    Raises HTTPException(400 or 409) if the transition is disallowed.
    """
    if ride.status == target_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ride is already in state '{ride.status.value}'.",
        )

    allowed = PERMITTED_TRANSITIONS.get(ride.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ride transition from '{ride.status.value}' to '{target_status.value}'.",
        )

    now = datetime.now(UTC)
    ride.status = target_status

    if target_status == RideStatus.ACCEPTED:
        ride.accepted_at = now
    elif target_status == RideStatus.ARRIVED:
        pass  # arrival marked via event
    elif target_status == RideStatus.IN_PROGRESS:
        ride.picked_up_at = now
    elif target_status == RideStatus.COMPLETED:
        ride.completed_at = now
        ride.final_fare = ride.estimated_fare
    elif target_status == RideStatus.CANCELLED:
        ride.cancelled_at = now
        ride.cancellation_reason = cancellation_reason or "Cancelled by user"
