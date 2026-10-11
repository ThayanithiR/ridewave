import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ride, RideStatus


class AuthorizedTripTools:
    """
    Deterministic read-only tools executing queries for the authenticated user only.
    The LLM never queries the database directly or computes fares.
    """

    @staticmethod
    async def get_my_recent_trips(
        user_id: uuid.UUID, db: AsyncSession, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Retrieve recent trips belonging strictly to the authenticated user."""
        stmt = (
            select(Ride)
            .where(Ride.rider_id == user_id)
            .order_by(Ride.requested_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rides = result.scalars().all()

        return [
            {
                "ride_id": str(r.id),
                "status": r.status.value,
                "pickup": r.pickup_address,
                "dropoff": r.dropoff_address,
                "fare": float(r.final_fare if r.final_fare else r.estimated_fare),
                "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            }
            for r in rides
        ]

    @staticmethod
    async def explain_fare_breakdown(
        user_id: uuid.UUID, ride_id: uuid.UUID, db: AsyncSession
    ) -> dict[str, Any]:
        """Explain the authoritative fare calculation for a specific trip belonging to the user."""
        stmt = select(Ride).where(Ride.id == ride_id, Ride.rider_id == user_id)
        result = await db.execute(stmt)
        ride = result.scalar_one_or_none()

        if not ride:
            return {"error": "Trip not found or unauthorized."}

        fare = float(ride.final_fare or ride.estimated_fare)
        return {
            "ride_id": str(ride.id),
            "status": ride.status.value,
            "currency": ride.currency,
            "total_fare": fare,
            "base_fare": 2.50,
            "fare_explanation": "Fare is computed using base fare ($2.50) + $1.20/km distance rate and $0.25/min estimated travel duration.",
        }

    @staticmethod
    async def get_active_ride_status(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
        """Retrieve current ongoing ride status for the user."""
        stmt = select(Ride).where(
            Ride.rider_id == user_id,
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
        result = await db.execute(stmt)
        active_ride = result.scalar_one_or_none()

        if not active_ride:
            return {"has_active_ride": False, "message": "You have no active rides currently."}

        return {
            "has_active_ride": True,
            "ride_id": str(active_ride.id),
            "status": active_ride.status.value,
            "pickup": active_ride.pickup_address,
            "dropoff": active_ride.dropoff_address,
            "driver_assigned": active_ride.driver_id is not None,
        }
