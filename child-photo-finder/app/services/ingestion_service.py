from sqlalchemy.orm import Session

from app.drive.drive_service import (
    list_files_in_folder,
    download_file
)
from app.face.face_service import FaceService
from app.models import Photo, FaceEmbedding, Event


class IngestionService:

    def __init__(self, db: Session):
        self.db = db
        self.face_service = FaceService()

    def _get_all_image_files(self, folder_id: str):
        """Recursively find all image files inside a Drive folder."""

        all_images = []

        files = list_files_in_folder(folder_id)

        for file in files:
            mime_type = file["mimeType"]

            if mime_type.startswith("image/"):
                all_images.append(file)

            elif mime_type == "application/vnd.google-apps.folder":
                all_images.extend(
                    self._get_all_image_files(file["id"])
                )

        return all_images

    def ingest_folder(self, folder_id: str, event_id: int):
        """
        Ingest all images from a Google Drive folder.

        Event status:
        Pending -> Processing -> Ready
        Processing -> Failed if ingestion encounters a critical error.
        """

        # --------------------------------------------------------
        # Get event
        # --------------------------------------------------------

        event = (
            self.db.query(Event)
            .filter(Event.id == event_id)
            .first()
        )

        if event is None:
            raise ValueError(f"Event with ID {event_id} not found.")

        # --------------------------------------------------------
        # Mark event as Processing
        # --------------------------------------------------------

        event.status = "Processing"
        self.db.commit()

        try:
            # ----------------------------------------------------
            # Find all images
            # ----------------------------------------------------

            image_files = self._get_all_image_files(folder_id)

            print(f"Found {len(image_files)} images.")

            processed = 0
            skipped = 0
            total_faces = 0
            failed = 0

            # ----------------------------------------------------
            # Handle no photos
            # ----------------------------------------------------

            if len(image_files) == 0:
                event.status = "Pending"
                self.db.commit()

                print("No images found. Event remains Pending.")

                return {
                    "processed": 0,
                    "skipped": 0,
                    "failed": 0,
                    "total_faces": 0,
                    "status": "Pending"
                }

            # ----------------------------------------------------
            # Process every image
            # ----------------------------------------------------

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
                    # --------------------------------------------
                    # Download image
                    # --------------------------------------------

                    file_data = download_file(file["id"])
                    image_bytes = file_data.read()

                    # --------------------------------------------
                    # Detect faces
                    # --------------------------------------------

                    faces = self.face_service.detect_faces(
                        image_bytes
                    )

                    print(
                        f"Faces detected: {len(faces)}"
                    )

                    # --------------------------------------------
                    # Store photo metadata
                    # --------------------------------------------

                    photo = Photo(
                        event_id=event_id,
                        drive_file_id=file["id"],
                        file_name=file["name"],
                        mime_type=file["mimeType"],
                        drive_url=file.get("webViewLink")
                    )

                    self.db.add(photo)
                    self.db.flush()

                    # --------------------------------------------
                    # Store every detected face
                    # --------------------------------------------

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

                    failed += 1

                    print(
                        f"ERROR processing "
                        f"{file['name']}: {e}"
                    )

            # ----------------------------------------------------
            # Determine final event status
            # ----------------------------------------------------

            if failed > 0:
                event.status = "Failed"
            else:
                event.status = "Ready"

            self.db.commit()

            # ----------------------------------------------------
            # Ingestion summary
            # ----------------------------------------------------

            print("\n==============================")
            print("INGESTION COMPLETE")
            print("==============================")
            print(f"Processed : {processed}")
            print(f"Skipped   : {skipped}")
            print(f"Failed    : {failed}")
            print(f"Faces     : {total_faces}")
            print(f"Status    : {event.status}")

            return {
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "total_faces": total_faces,
                "status": event.status
            }

        except Exception as e:

            # ----------------------------------------------------
            # Critical ingestion failure
            # ----------------------------------------------------

            self.db.rollback()

            event = (
                self.db.query(Event)
                .filter(Event.id == event_id)
                .first()
            )

            if event:
                event.status = "Failed"
                self.db.commit()

            print(f"Critical ingestion error: {e}")

            raise