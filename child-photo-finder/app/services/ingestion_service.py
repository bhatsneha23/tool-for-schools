
import requests
import time
from sqlalchemy.orm import Session

from app.drive.drive_service import (
    list_files_in_folder,
    download_file,
)
from app.face.face_service import FaceService
from app.models import Photo, FaceEmbedding, Event
from app.config import (
    MYCLASSADMIN_STATUS_URL,
    MYCLASSADMIN_STATUS_API_KEY,
)


class IngestionService:

    def __init__(self, db: Session):
        self.db = db
        self.face_service = FaceService()

    def _notify_status(self, event, status: str):
        """Notify MyClassAdmin with retries for temporary failures."""

        if not MYCLASSADMIN_STATUS_URL:
            print(
                "MyClassAdmin callback URL is not configured. "
                f"Notification skipped for event {event.event_id}."
            )
            return

        if not MYCLASSADMIN_STATUS_API_KEY:
            print(
                "MyClassAdmin callback API key is not configured. "
                f"Notification skipped for event {event.event_id}."
            )
            return

        try:
            external_event_id = int(event.event_id)
            if external_event_id <= 0:
                raise ValueError("Event ID must be positive.")
        except (TypeError, ValueError):
            print(
                "Invalid MyClassAdmin event ID: "
                f"{event.event_id}"
            )
            return

        status_mapping = {
            "Pending": "PENDING",
            "Processing": "PROCESSING",
            "Ready": "READY",
            "Failed": "FAILED",
        }

        callback_status = status_mapping.get(status)

        if callback_status is None:
            print(f"Unsupported callback status: {status}")
            return

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": MYCLASSADMIN_STATUS_API_KEY,
        }

        payload = {
            "event_id": external_event_id,
            "status": callback_status,
        }

        retryable_status_codes = {429, 500, 502, 503, 504}

        for attempt in range(3):
            try:
                response = requests.post(
                    MYCLASSADMIN_STATUS_URL,
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()

                print(
                    "MyClassAdmin notified successfully: "
                    f"event_id={external_event_id}, "
                    f"status={callback_status}"
                )
                return


            except requests.RequestException as error:
                response = getattr(error, "response", None)
                status_code = (
                    response.status_code
                    if response is not None
                    else None
                )
                response_body = (
                    response.text
                    if response is not None
                    else str(error)
                )

                print(
                    "MyClassAdmin callback error | "
                    f"event_id={external_event_id} | "
                    f"status={callback_status} | "
                    f"http_status={status_code} | "
                    f"response={response_body}"
                )

                should_retry = (
                    status_code is None
                    or status_code in retryable_status_codes
                )

                if not should_retry or attempt == 2:
                    print(
                        "Callback delivery stopped after "
                        f"{attempt + 1} attempt(s)."
                    )
                    return

                delay = 2 ** attempt
                print(f"Retrying callback in {delay}s...")
                time.sleep(delay)


    def _set_status(self, event, status: str):
        """Persist status and notify MyClassAdmin only when it changes."""

        if event.status == status:
            return

        event.status = status
        self.db.commit()
        self._notify_status(event, status)

    def _get_all_image_files(self, folder_id: str):
        """Recursively find all images in a Google Drive folder."""

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
        Ingest images using the existing workflow.

        Pending -> Processing -> Ready
        Processing -> Failed if ingestion fails.
        """

        event = (
            self.db.query(Event)
            .filter(Event.id == event_id)
            .first()
        )

        if event is None:
            raise ValueError(
                f"Event with ID {event_id} not found."
            )

        self._set_status(event, "Processing")

        try:
            image_files = self._get_all_image_files(folder_id)
            print(f"Found {len(image_files)} images.")

            processed = 0
            skipped = 0
            total_faces = 0
            failed = 0

            if len(image_files) == 0:
                self._set_status(event, "Pending")
                print("No images found. Event remains Pending.")

                return {
                    "processed": 0,
                    "skipped": 0,
                    "failed": 0,
                    "total_faces": 0,
                    "status": "Pending",
                }

            for index, file in enumerate(image_files, start=1):
                print(
                    f"\n[{index}/{len(image_files)}] "
                    f"{file['name']}"
                )

                existing_photo = (
                    self.db.query(Photo)
                    .filter(Photo.drive_file_id == file["id"])
                    .first()
                )

                if existing_photo:
                    print("Already processed. Skipping.")
                    skipped += 1
                    continue

                try:
                    file_data = download_file(file["id"])
                    image_bytes = file_data.read()

                    faces = self.face_service.detect_faces(image_bytes)
                    print(f"Faces detected: {len(faces)}")

                    photo = Photo(
                        event_id=event_id,
                        drive_file_id=file["id"],
                        file_name=file["name"],
                        mime_type=file["mimeType"],
                        drive_url=file.get("webViewLink"),
                    )

                    self.db.add(photo)
                    self.db.flush()

                    for face in faces:
                        embedding = FaceEmbedding(
                            photo_id=photo.id,
                            face_index=face["face_index"],
                            embedding=face["embedding"],
                        )
                        self.db.add(embedding)

                    self.db.commit()
                    processed += 1
                    total_faces += len(faces)

                except Exception as error:
                    self.db.rollback()
                    failed += 1
                    print(
                        f"ERROR processing {file['name']}: {error}"
                    )

            final_status = "Failed" if failed > 0 else "Ready"
            self._set_status(event, final_status)

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
                "status": event.status,
            }

        except Exception as error:
            self.db.rollback()

            event = (
                self.db.query(Event)
                .filter(Event.id == event_id)
                .first()
            )

            if event:
                try:
                    self._set_status(event, "Failed")

                except Exception as status_error:
                    self.db.rollback()
                    print(
                        "Could not persist failure status: "
                        f"{status_error}"
                    )

            print(f"Critical ingestion error: {error}")
            raise
