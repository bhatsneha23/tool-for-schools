import numpy as np
from sqlalchemy.orm import Session

from app.face.face_service import FaceService
from app.models import Event, Photo, FaceEmbedding
from app.config import SIMILARITY_THRESHOLD


class MatchingService:

    def __init__(self, db: Session):
        self.db = db
        self.face_service = FaceService()

    def get_event(self, event_id: str):
        """
        Get an event using its public Event ID.
        Example: EVT001
        """

        return (
            self.db.query(Event)
            .filter(Event.event_id == event_id)
            .first()
        )

    def find_matches(
        self,
        image_bytes: bytes,
        event_id: str,
        top_k: int = 20
    ):
        """
        Find photos containing the child within a specific event.
        """

        # -----------------------------------------
        # 1. Find the event
        # -----------------------------------------

        event = self.get_event(event_id)

        if event is None:
            raise ValueError(
                f"Event '{event_id}' not found."
            )

        # -----------------------------------------
        # 2. Detect faces in query image
        # -----------------------------------------

        faces = self.face_service.detect_faces(
            image_bytes
        )

        if len(faces) == 0:
            raise ValueError(
                "No face detected in the test image."
            )

        # -----------------------------------------
        # 3. If multiple faces are detected,
        #    use the largest face
        # -----------------------------------------

        if len(faces) > 1:

            print(
                f"Multiple faces detected ({len(faces)}). "
                "Using the largest face."
            )

            faces = sorted(
                faces,
                key=lambda face: (
                    (face["bbox"][2] - face["bbox"][0])
                    *
                    (face["bbox"][3] - face["bbox"][1])
                ),
                reverse=True
            )

        # -----------------------------------------
        # 4. Get query face embedding
        # -----------------------------------------

        query_embedding = np.array(
            faces[0]["embedding"],
            dtype=np.float32
        )

        query_norm = np.linalg.norm(
            query_embedding
        )

        if query_norm == 0:
            raise ValueError(
                "Invalid face embedding."
            )

        # Normalize query embedding

        query_embedding = (
            query_embedding / query_norm
        )

        # -----------------------------------------
        # 5. Get ONLY embeddings belonging
        #    to this event
        # -----------------------------------------

        records = (
            self.db.query(
                FaceEmbedding,
                Photo
            )
            .join(
                Photo,
                FaceEmbedding.photo_id == Photo.id
            )
            .filter(
                Photo.event_id == event.id
            )
            .all()
        )

        print(
            f"Comparing against "
            f"{len(records)} stored faces "
            f"from {event.event_name}"
        )

        # -----------------------------------------
        # 6. Compare face embeddings
        # -----------------------------------------

        photo_matches = {}

        for face_embedding, photo in records:

            try:

                stored_embedding = np.array(
                    face_embedding.embedding,
                    dtype=np.float32
                )

            except Exception:

                continue

            stored_norm = np.linalg.norm(
                stored_embedding
            )

            if stored_norm == 0:
                continue

            # Normalize stored embedding

            stored_embedding = (
                stored_embedding / stored_norm
            )

            # Cosine similarity

            similarity = float(
                np.dot(
                    query_embedding,
                    stored_embedding
                )
            )

            # -----------------------------------------
            # 7. Apply similarity threshold
            # -----------------------------------------

            if similarity >= SIMILARITY_THRESHOLD:

                # A photo can contain multiple faces.
                # Keep the highest similarity for that photo.

                if (
                    photo.id not in photo_matches
                    or
                    similarity >
                    photo_matches[
                        photo.id
                    ]["similarity"]
                ):

                    photo_matches[photo.id] = {

                        "photo_id": photo.id,

                        "file_name":
                            photo.file_name,

                        "drive_file_id":
                            photo.drive_file_id,

                        "drive_url":
                            photo.drive_url,

                        "similarity":
                            similarity
                    }

        # -----------------------------------------
        # 8. Sort matches by similarity
        # -----------------------------------------

        matches = sorted(
            photo_matches.values(),
            key=lambda x: x["similarity"],
            reverse=True
        )

        # -----------------------------------------
        # 9. Return top matches
        # -----------------------------------------

        return matches[:top_k]