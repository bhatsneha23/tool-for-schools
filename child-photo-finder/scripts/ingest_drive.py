from app.database import SessionLocal
from app.services.ingestion_service import IngestionService
from app.models import Event


ANNUAL_DAY_FOLDER_ID = "1j2Sb5wFEw2l7Hnf3CY1soxIuOSqrtIJD"
ANNUAL_DAY_PUBLIC_ID = "EVT002"


def main():
    print("Starting Annual Day photo ingestion...")

    db = SessionLocal()

    try:
        # Find Annual Day event
        event = (
            db.query(Event)
            .filter(Event.event_id == ANNUAL_DAY_PUBLIC_ID)
            .first()
        )

        if not event:
            raise ValueError(
                f"Event {ANNUAL_DAY_PUBLIC_ID} not found."
            )

        print(
            f"Event found: {event.event_id} - "
            f"{event.event_name}"
        )

        service = IngestionService(db)

        service.ingest_folder(
            ANNUAL_DAY_FOLDER_ID,
            event.id
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()