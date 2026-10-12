"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column(
            'role',
            sa.Enum('RIDER', 'DRIVER', 'ADMIN', name='user_role_enum'),
            nullable=False,
            server_default='RIDER',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. drivers table
    op.create_table(
        'drivers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('OFFLINE', 'ONLINE', 'BUSY', name='driver_status_enum'),
            nullable=False,
            server_default='OFFLINE',
        ),
        sa.Column('vehicle_make', sa.String(length=100), nullable=False),
        sa.Column('vehicle_model', sa.String(length=100), nullable=False),
        sa.Column('vehicle_plate', sa.String(length=50), nullable=False),
        sa.Column('last_latitude', sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column('last_longitude', sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column('last_location_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    # 3. rides table
    op.create_table(
        'rides',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('rider_id', sa.UUID(), nullable=False),
        sa.Column('driver_id', sa.UUID(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'REQUESTED',
                'MATCHING',
                'ACCEPTED',
                'ARRIVED',
                'IN_PROGRESS',
                'COMPLETED',
                'CANCELLED',
                name='ride_status_enum',
            ),
            nullable=False,
            server_default='REQUESTED',
        ),
        sa.Column('pickup_latitude', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('pickup_longitude', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('pickup_address', sa.String(length=255), nullable=False),
        sa.Column('dropoff_latitude', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dropoff_longitude', sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column('dropoff_address', sa.String(length=255), nullable=False),
        sa.Column('estimated_fare', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('final_fare', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='USD'),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('picked_up_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.id']),
        sa.ForeignKeyConstraint(['rider_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_rides_driver_id'), 'rides', ['driver_id'], unique=False)
    op.create_index(op.f('ix_rides_rider_id'), 'rides', ['rider_id'], unique=False)
    op.create_index(op.f('ix_rides_status'), 'rides', ['status'], unique=False)
    op.create_index(
        'idx_driver_single_active_ride',
        'rides',
        ['driver_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS')"),
        sqlite_where=sa.text("status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS')"),
    )

    # 4. ride_events table
    op.create_table(
        'ride_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ride_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('actor_role', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ride_id'], ['rides.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ride_events_ride_id'), 'ride_events', ['ride_id'], unique=False)

    # 5. idempotency_keys table
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('request_path', sa.String(length=255), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_idempotency_key'),
    )
    op.create_index(op.f('ix_idempotency_keys_key'), 'idempotency_keys', ['key'], unique=False)

    # 6. outbox_events table
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('aggregate_type', sa.String(length=50), nullable=False, server_default='RIDE'),
        sa.Column('aggregate_id', sa.String(length=100), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outbox_events_aggregate_id'), 'outbox_events', ['aggregate_id'], unique=False)
    op.create_index(op.f('ix_outbox_events_status'), 'outbox_events', ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('outbox_events')
    op.drop_table('idempotency_keys')
    op.drop_table('ride_events')
    op.drop_table('rides')
    op.drop_table('drivers')
    op.drop_table('users')
