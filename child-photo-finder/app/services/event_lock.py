
from contextlib import contextmanager
from sqlalchemy import text
from app.database import engine


@contextmanager
def event_lock(event_id: int):
    """Acquire and release a PostgreSQL session-level lock."""
    with engine.connect() as connection:
        acquired = False

        try:
            connection.execute(
                text("SELECT pg_advisory_lock(:event_id)"),
                {"event_id": event_id},
            )
            connection.commit()
            acquired = True

            yield

        finally:
            if acquired:
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:event_id)"),
                        {"event_id": event_id},
                    )
                    connection.commit()
                except Exception:
                    connection.invalidate()
                    raise
