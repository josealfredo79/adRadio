from app.core.redact import redact_url


def test_hides_the_password_and_keeps_the_rest():
    assert redact_url("redis://default:WQJk-secret@redis.railway.internal:6379") == "redis://default:***@redis.railway.internal:6379"
    assert redact_url("postgresql+asyncpg://neondb_owner:p@ss@ep-x.neon.tech/db") == "postgresql+asyncpg://neondb_owner:***@ep-x.neon.tech/db"
    assert redact_url("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert redact_url(None) == ""
