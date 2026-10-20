"""initial schema (HLD/LLD section 17)

Revision ID: 001
Revises:
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# asyncpg cannot run several commands in one statement, so each is its own string.
UP = [
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    "CREATE EXTENSION IF NOT EXISTS citext",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE TYPE user_role AS ENUM ('student','admin')",
    "CREATE TYPE resource_type AS ENUM ('SEAT','ROOM','COMPUTE_POOL')",
    "CREATE TYPE booking_status AS ENUM "
    "('REQUESTED','CONFIRMED','WAITLISTED','CANCELLED','COMPLETED','EXPIRED')",
    "CREATE TYPE waitlist_status AS ENUM ('ACTIVE','PROMOTED','CANCELLED','EXPIRED')",
    """
    CREATE TABLE users (
      user_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      email         citext NOT NULL UNIQUE,
      name          text NOT NULL,
      password_hash text NOT NULL,
      role          user_role NOT NULL DEFAULT 'student',
      user_group    text NOT NULL DEFAULT 'general',
      is_active     boolean NOT NULL DEFAULT true,
      created_at    timestamptz NOT NULL DEFAULT now()
    )""",
    """
    CREATE TABLE resources (
      resource_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      type          resource_type NOT NULL,
      name          text NOT NULL,
      parent_id     uuid REFERENCES resources(resource_id),
      capacity      int NOT NULL CHECK (capacity > 0),
      slot_minutes  int NOT NULL CHECK (slot_minutes IN (15,30,60,120)),
      open_time     time NOT NULL,
      close_time    time NOT NULL,
      timezone      text NOT NULL,
      max_slots_per_booking     int NOT NULL DEFAULT 4,
      max_quantity_per_booking  int NOT NULL DEFAULT 1,
      max_active_per_user       int NOT NULL DEFAULT 2,
      min_cancel_notice_minutes int NOT NULL DEFAULT 0,
      booking_horizon_days      int NOT NULL DEFAULT 14,
      policy_name   text NOT NULL DEFAULT 'FIFO',
      lat double precision,
      lon double precision,
      active        boolean NOT NULL DEFAULT true,
      version       int NOT NULL DEFAULT 1,
      created_at    timestamptz NOT NULL DEFAULT now(),
      CHECK (max_quantity_per_booking <= capacity),
      CHECK (type <> 'SEAT' OR capacity = 1)
    )""",
    """
    CREATE TABLE resource_eligibility (
      resource_id uuid REFERENCES resources ON DELETE CASCADE,
      user_group  text NOT NULL,
      PRIMARY KEY (resource_id, user_group)
    )""",
    """
    CREATE TABLE slot_usage (
      resource_id uuid NOT NULL REFERENCES resources,
      slot_start  timestamptz NOT NULL,
      used        int NOT NULL DEFAULT 0 CHECK (used >= 0),
      capacity    int NOT NULL CHECK (capacity > 0),
      PRIMARY KEY (resource_id, slot_start),
      CHECK (used <= capacity)
    )""",
    """
    CREATE TABLE bookings (
      booking_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id         uuid NOT NULL REFERENCES users,
      resource_id     uuid NOT NULL REFERENCES resources,
      start_time      timestamptz NOT NULL,
      end_time        timestamptz NOT NULL,
      quantity        int NOT NULL DEFAULT 1 CHECK (quantity > 0),
      status          booking_status NOT NULL,
      is_exclusive    boolean NOT NULL,
      idempotency_key text NOT NULL,
      request_hash    text NOT NULL,
      period          tstzrange GENERATED ALWAYS AS
                        (tstzrange(start_time, end_time, '[)')) STORED,
      created_at      timestamptz NOT NULL DEFAULT now(),
      updated_at      timestamptz NOT NULL DEFAULT now(),
      confirmed_at    timestamptz,
      cancelled_at    timestamptz,
      version         int NOT NULL DEFAULT 1,
      CHECK (end_time > start_time),
      UNIQUE (user_id, idempotency_key),
      EXCLUDE USING gist (resource_id WITH =, period WITH &&)
        WHERE (status = 'CONFIRMED' AND is_exclusive)
    )""",
    "CREATE INDEX ix_bookings_user ON bookings (user_id, start_time DESC)",
    "CREATE INDEX ix_bookings_active ON bookings (resource_id, start_time) "
    "WHERE status IN ('CONFIRMED','WAITLISTED')",
    """
    CREATE TABLE booking_status_history (
      id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      booking_id  uuid NOT NULL REFERENCES bookings,
      from_status booking_status,
      to_status   booking_status NOT NULL,
      actor_id    uuid,
      reason      text,
      created_at  timestamptz NOT NULL DEFAULT now()
    )""",
    """
    CREATE TABLE waitlist_entries (
      waitlist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      seq         bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
      booking_id  uuid NOT NULL UNIQUE REFERENCES bookings,
      user_id     uuid NOT NULL REFERENCES users,
      resource_id uuid NOT NULL REFERENCES resources,
      start_time  timestamptz NOT NULL,
      end_time    timestamptz NOT NULL,
      quantity    int NOT NULL,
      status      waitlist_status NOT NULL DEFAULT 'ACTIVE',
      created_at  timestamptz NOT NULL DEFAULT now(),
      promoted_at timestamptz,
      expires_at  timestamptz NOT NULL
    )""",
    "CREATE INDEX ix_wl_active ON waitlist_entries (resource_id, start_time, seq) "
    "WHERE status = 'ACTIVE'",
    """
    CREATE TABLE allocation_records (
      id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      booking_id     uuid NOT NULL REFERENCES bookings,
      policy_name    text NOT NULL,
      policy_version text NOT NULL,
      decision_type  text NOT NULL CHECK
        (decision_type IN ('ADMIT','PROMOTE','REJECT_FULL','SKIP_INELIGIBLE')),
      inputs         jsonb NOT NULL,
      reason         text,
      decided_at     timestamptz NOT NULL DEFAULT now()
    )""",
    """
    CREATE TABLE idempotency_keys (
      user_id       uuid NOT NULL REFERENCES users,
      idem_key      text NOT NULL CHECK (length(idem_key) BETWEEN 8 AND 128),
      request_hash  text NOT NULL,
      response_code int NOT NULL,
      response_body jsonb NOT NULL,
      booking_id    uuid,
      created_at    timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, idem_key)
    )""",
    """
    CREATE TABLE outbox_events (
      id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      event_id       uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
      aggregate_type text NOT NULL,
      aggregate_id   uuid NOT NULL,
      event_type     text NOT NULL,
      schema_version int NOT NULL DEFAULT 1,
      payload        jsonb NOT NULL,
      created_at     timestamptz NOT NULL DEFAULT now(),
      published_at   timestamptz,
      attempts       int NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX ix_outbox_pending ON outbox_events (id) WHERE published_at IS NULL",
    """
    CREATE TABLE processed_events (
      consumer     text NOT NULL,
      event_id     uuid NOT NULL,
      processed_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (consumer, event_id)
    )""",
    # Added after the mobile decision: in-app notifications replace push.
    """
    CREATE TABLE notifications (
      id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      user_id    uuid NOT NULL REFERENCES users,
      type       text NOT NULL,
      payload    jsonb NOT NULL,
      event_id   uuid,
      read_at    timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id, event_id, type)
    )""",
    "CREATE INDEX ix_notifications_user ON notifications (user_id, id DESC)",
    """
    CREATE TABLE refresh_tokens (
      token_hash text PRIMARY KEY,
      user_id    uuid NOT NULL REFERENCES users,
      expires_at timestamptz NOT NULL,
      revoked    boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )""",
]

DROP_TABLES = [
    "refresh_tokens",
    "notifications",
    "processed_events",
    "outbox_events",
    "idempotency_keys",
    "allocation_records",
    "waitlist_entries",
    "booking_status_history",
    "bookings",
    "slot_usage",
    "resource_eligibility",
    "resources",
    "users",
]
DROP_TYPES = ["waitlist_status", "booking_status", "resource_type", "user_role"]


def upgrade() -> None:
    for stmt in UP:
        op.execute(stmt)


def downgrade() -> None:
    for t in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t}")
    for t in DROP_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {t}")
