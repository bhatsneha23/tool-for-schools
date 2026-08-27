from app.config import GOOGLE_DRIVE_FOLDER_ID
from app.database import SessionLocal
from app.services.ingestion_service import IngestionService


def main():

    print("Starting photo ingestion...")

    db = SessionLocal()

    try:

        service = IngestionService(db)

        service.ingest_folder(
            GOOGLE_DRIVE_FOLDER_ID
        )

    finally:

        db.close()


if __name__ == "__main__":
    main()