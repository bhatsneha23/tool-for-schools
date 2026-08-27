from pathlib import Path

from app.face.face_service import FaceService


def main():

    image_path = Path(
        "data/temp/test_image.jpg"
    )

    image_bytes = image_path.read_bytes()

    print("Loading face model...")

    face_service = FaceService()

    print("Detecting faces...")

    faces = face_service.detect_faces(
        image_bytes
    )

    print(f"\nFaces detected: {len(faces)}")

    for face in faces:

        print(
            f"Face {face['face_index']}: "
            f"embedding size = "
            f"{len(face['embedding'])}"
        )


if __name__ == "__main__":
    main()