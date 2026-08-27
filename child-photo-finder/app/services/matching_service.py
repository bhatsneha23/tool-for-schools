import numpy as np
from sqlalchemy.orm import Session

from app.face.face_service import FaceService
from app.models import Photo, FaceEmbedding
from app.config import SIMILARITY_THRESHOLD


class MatchingService:

    def __init__(self, db: Session):
        self.db = db
        self.face_service = FaceService()

    def find_matches(
        self,
        image_bytes: bytes,
        top_k: int = 20,
        face_index: int | None = None
    ):

        # Generate embedding for the uploaded/test image
        faces = self.face_service.detect_faces(image_bytes)

        if len(faces) == 0:
            raise ValueError("No face detected in the test image.")

        if len(faces) > 1 and face_index is None:
            raise ValueError(
                "Multiple faces detected. Use --face-index to select the child's face."
            )

        if face_index is not None and not 0 <= face_index < len(faces):
            raise ValueError(
                f"Invalid face index {face_index}. Choose a value from 0 to {len(faces) - 1}."
            )

        selected_face = faces[0] if face_index is None else faces[face_index]

        query_embedding = np.array(
            selected_face["embedding"],
            dtype=np.float32
        )

        # Normalize query embedding
        norm = np.linalg.norm(query_embedding)

        if norm == 0:
            raise ValueError("Invalid face embedding.")

        query_embedding = query_embedding / norm

        # Get all stored embeddings
        records = (
            self.db.query(FaceEmbedding, Photo)
            .join(
                Photo,
                FaceEmbedding.photo_id == Photo.id
            )
            .all()
        )

        photo_matches = {}

        for face_embedding, photo in records:

            stored_embedding = np.array(
                face_embedding.embedding,
                dtype=np.float32
            )

            stored_norm = np.linalg.norm(stored_embedding)

            if stored_norm == 0:
                continue

            stored_embedding = stored_embedding / stored_norm

            # Cosine similarity
            similarity = float(
                np.dot(
                    query_embedding,
                    stored_embedding
                )
            )

            # Keep only matches above threshold
            if similarity >= SIMILARITY_THRESHOLD:

                # If multiple faces from the same photo match,
                # keep only the highest similarity.
                if (
                    photo.id not in photo_matches
                    or similarity > photo_matches[photo.id]["similarity"]
                ):

                    photo_matches[photo.id] = {
                        "photo_id": photo.id,
                        "file_name": photo.file_name,
                        "drive_file_id": photo.drive_file_id,
                        "drive_url": photo.drive_url,
                        "similarity": similarity
                    }

        # Sort by similarity
        matches = sorted(
            photo_matches.values(),
            key=lambda x: x["similarity"],
            reverse=True
        )

        return matches[:top_k]