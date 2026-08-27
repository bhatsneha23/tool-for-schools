from sqlalchemy.orm import Session

from app.drive.drive_service import (
    list_files_in_folder,
    download_file
)
from app.face.face_service import FaceService
from app.models import Photo, FaceEmbedding


class IngestionService:

    def __init__(self, db: Session):
        self.db = db
        self.face_service = FaceService()

    def ingest_folder(self, folder_id: str):

        files = list_files_in_folder(folder_id)

        image_files = [
            file
            for file in files
            if file["mimeType"].startswith("image/")
        ]

        print(f"Found {len(image_files)} images.")

        processed = 0
        skipped = 0
        total_faces = 0

        for index, file in enumerate(image_files, start=1):

            print(
                f"\n[{index}/{len(image_files)}] "
                f"{file['name']}"
            )

            # Avoid processing the same Drive file twice
            existing_photo = (
                self.db.query(Photo)
                .filter(
                    Photo.drive_file_id == file["id"]
                )
                .first()
            )

            if existing_photo:
                print("Already processed. Skipping.")
                skipped += 1
                continue

            try:
                file_data = download_file(file["id"])
                image_bytes = file_data.read()

                faces = self.face_service.detect_faces(
                    image_bytes
                )

                print(
                    f"Faces detected: {len(faces)}"
                )

                # Store photo metadata
                photo = Photo(
                    drive_file_id=file["id"],
                    file_name=file["name"],
                    mime_type=file["mimeType"],
                    drive_url=file.get("webViewLink")
                )

                self.db.add(photo)
                self.db.flush()

                # Store every detected face
                for face in faces:

                    embedding = FaceEmbedding(
                        photo_id=photo.id,
                        face_index=face["face_index"],
                        embedding=face["embedding"]
                    )

                    self.db.add(embedding)

                self.db.commit()

                processed += 1
                total_faces += len(faces)

            except Exception as e:

                self.db.rollback()

                print(
                    f"ERROR processing "
                    f"{file['name']}: {e}"
                )

        print("\n==============================")
        print("INGESTION COMPLETE")
        print("==============================")
        print(f"Processed : {processed}")
        print(f"Skipped   : {skipped}")
        print(f"Faces     : {total_faces}")