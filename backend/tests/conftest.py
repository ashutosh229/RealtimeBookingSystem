import os

# Defaults so unit tests run without a .env; real environments override these.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://rtbs:change_me@localhost:5432/rtbs")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-unit-test-secret-1234")
