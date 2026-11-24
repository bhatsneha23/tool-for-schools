
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import engine


STATEMENTS = (
    """
    ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS last_error TEXT
    """,
    """
    ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
    NOT NULL DEFAULT NOW()
    """,
    """
    ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
    NOT NULL DEFAULT NOW()
    """,
)


def migrate() -> None:
    with engine.begin() as connection:
        table = connection.execute(
            text(
                "SELECT to_regclass('public.ingestion_jobs')"
            )
        ).scalar_one()

        if table is None:
            raise RuntimeError(
                "Table public.ingestion_jobs does not exist. "
                "Start the API once or run create_all() before "
                "executing this migration."
            )

        for statement in STATEMENTS:
            connection.execute(text(statement))

    print("ingestion_jobs schema migration completed.")


if __name__ == "__main__":
    migrate()
