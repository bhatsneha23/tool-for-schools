import argparse
import html
import os
import webbrowser
from pathlib import Path

from app.database import SessionLocal
from app.services.matching_service import MatchingService
from app.drive.drive_service import download_file


RESULTS_DIR = Path("data/results")
RESULTS_HTML = RESULTS_DIR / "results.html"


def create_results_page(matches):

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    cards = []

    for index, match in enumerate(matches, start=1):

        file_name = html.escape(
            match["file_name"]
        )

        similarity = match["similarity"]

        image_file = match.get("local_file")

        if image_file:
            image_src = image_file
        else:
            image_src = ""

        cards.append(
            f"""
            <div class="card">
                <img src="{image_src}" alt="{file_name}">
                <div class="info">
                    <h3>{file_name}</h3>
                    <p>Similarity: {similarity:.2%}</p>
                </div>
            </div>
            """
        )

    cards_html = "\n".join(cards)

    html_content = f"""
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<title>Child Photo Finder - Results</title>

<style>

body {{
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 30px;
    background: #f5f5f5;
}}

h1 {{
    text-align: center;
}}

.subtitle {{
    text-align: center;
    color: #666;
    margin-bottom: 30px;
}}

.grid {{
    display: grid;
    grid-template-columns: repeat(
        auto-fill,
        minmax(250px, 1fr)
    );
    gap: 25px;
    max-width: 1200px;
    margin: auto;
}}

.card {{
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}}

.card img {{
    width: 100%;
    height: 280px;
    object-fit: cover;
}}

.info {{
    padding: 15px;
}}

.info h3 {{
    margin: 0 0 8px 0;
    word-break: break-word;
}}

.info p {{
    margin: 0;
    color: #555;
}}

</style>

</head>

<body>

<h1>Child Photo Finder</h1>

<div class="subtitle">
    {len(matches)} matching photos found
</div>

<div class="grid">

{cards_html}

</div>

</body>
</html>
"""

    RESULTS_HTML.write_text(
        html_content,
        encoding="utf-8"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--image",
        default="data/uploads/child.jpg",
        help="Path to child's test image"
    )

    parser.add_argument(
        "--face-index",
        type=int,
        help="Index of the child's face when the image contains multiple faces"
    )

    args = parser.parse_args()

    image_path = Path(args.image)

    if not image_path.exists():

        print(
            f"\nERROR: Image not found:"
            f"\n{image_path}\n"
        )

        return

    print("\n==============================")
    print("      CHILD PHOTO FINDER")
    print("==============================")

    print(
        f"\nTest image: {image_path}"
    )

    # Read test image
    image_bytes = image_path.read_bytes()

    db = SessionLocal()

    try:

        matcher = MatchingService(db)

        print("\nSearching database...")

        matches = matcher.find_matches(
            image_bytes,
            face_index=args.face_index
        )

        print(
            f"\nFound {len(matches)} matching photos."
        )

        if not matches:

            print(
                "\nNo matching photos found."
            )

            create_results_page([])

            webbrowser.open(
                RESULTS_HTML.resolve().as_uri()
            )

            return

        RESULTS_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        # Download matched photos
        for index, match in enumerate(
            matches,
            start=1
        ):

            print(
                f"\n[{index}/{len(matches)}] "
                f"{match['file_name']}"
            )

            print(
                f"Similarity: "
                f"{match['similarity']:.2%}"
            )

            try:

                file_data = download_file(
                    match["drive_file_id"]
                )

                safe_name = (
                    f"{index}_"
                    f"{match['file_name']}"
                )

                output_path = (
                    RESULTS_DIR / safe_name
                )

                output_path.write_bytes(
                    file_data.read()
                )

                # HTML needs a relative path
                match["local_file"] = (
                    Path(
                        safe_name
                    ).as_posix()
                )

            except Exception as e:

                print(
                    f"Could not download "
                    f"{match['file_name']}: {e}"
                )

                match["local_file"] = None

        # Generate results page
        create_results_page(matches)

        print(
            "\n=============================="
        )

        print(
            "RESULTS READY"
        )

        print(
            f"\nOpening:"
            f"\n{RESULTS_HTML}"
        )

        webbrowser.open(
            RESULTS_HTML.resolve().as_uri()
        )

    finally:

        db.close()


if __name__ == "__main__":
    main()