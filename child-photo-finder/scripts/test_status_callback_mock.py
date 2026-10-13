import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import app.services.ingestion_service as ingestion_module


def create_service():
    return ingestion_module.IngestionService.__new__(
        ingestion_module.IngestionService
    )


class FakeEvent:
    event_id = "145"


def run_test(status_code):
    service = create_service()
    fake_url = "https://mock.invalid/PhotoAlbum/updateStatus"
    fake_key = "mock-test-key"

    fake_response = MagicMock()

    if status_code >= 400:
        fake_response.raise_for_status.side_effect = (
            requests.HTTPError(f"Mock HTTP {status_code}")
        )

    with (
        patch.object(
            ingestion_module,
            "MYCLASSADMIN_STATUS_URL",
            fake_url,
        ),
        patch.object(
            ingestion_module,
            "MYCLASSADMIN_STATUS_API_KEY",
            fake_key,
        ),
        patch.object(
            ingestion_module.requests,
            "post",
            return_value=fake_response,
        ) as mock_post,
    ):
        service._notify_status(FakeEvent(), "Processing")
        mock_post.assert_called_once()

        if status_code >= 400:
            print(f"PASS: HTTP {status_code} did not escape _notify_status.")
        else:
            print("PASS: Successful callback handled correctly.")


if __name__ == "__main__":
    run_test(200)
    run_test(500)
    print("All callback tests passed.")