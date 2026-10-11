import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import DomainEvent
from app.models import OutboxEvent


class TransactionalOutbox:
    @staticmethod
    async def record_event(db: AsyncSession, event: DomainEvent) -> OutboxEvent:
        """Writes domain event into the outbox table within the active database transaction."""
        outbox_entry = OutboxEvent(
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload_json=json.dumps(event.model_dump()),
            status="PENDING",
            retry_count=0,
        )
        db.add(outbox_entry)
        return outbox_entry

    @staticmethod
    async def fetch_pending_events(db: AsyncSession, limit: int = 10) -> list[OutboxEvent]:
        """Fetch pending outbox events awaiting publish."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()
