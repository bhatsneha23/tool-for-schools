import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceService:

    def __init__(self):
        self.model = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"]
        )

        self.model.prepare(
            ctx_id=0,
            det_size=(640, 640)
        )

    def detect_faces(self, image_bytes: bytes):

        # Convert bytes → numpy array
        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        # Decode image
        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if image is None:
            raise ValueError(
                "Could not decode image"
            )

        # Detect faces
        faces = self.model.get(image)

        results = []

        for index, face in enumerate(faces):

            embedding = face.embedding

            # Normalize embedding
            embedding = embedding / np.linalg.norm(
                embedding
            )

            results.append({
                "face_index": index,
                "embedding": embedding.tolist(),
                "bbox": face.bbox.tolist()
            })

        return results