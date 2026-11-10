"""booking attempts log (C1)

Revision ID: 002
Revises: 001
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

UP = [
    """
    CREATE TABLE booking_attempts (
      id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      user_id            uuid NOT NULL REFERENCES users ON DELETE CASCADE,
      resource_id        uuid NOT NULL,
      start_time         timestamptz NOT NULL,
      end_time           timestamptz NOT NULL,
      quantity           int NOT NULL,
      waitlist_requested boolean NOT NULL,
      outcome            text NOT NULL CHECK (outcome IN ('CONFIRMED','WAITLISTED','REJECTED')),
      reason             text,
      detail             text,
      http_status        int NOT NULL,
      booking_id         uuid,
      user_group         text NOT NULL,
      created_at         timestamptz NOT NULL
    )""",
    "CREATE INDEX ix_attempts_time ON booking_attempts (created_at)",
    "CREATE INDEX ix_attempts_user ON booking_attempts (user_id, created_at)",
    "CREATE INDEX ix_attempts_resource ON booking_attempts (resource_id, created_at)",
    "CREATE INDEX ix_attempts_rejected ON booking_attempts (reason, created_at) "
    "WHERE outcome = 'REJECTED'",
]


def upgrade() -> None:
    for stmt in UP:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS booking_attempts")
