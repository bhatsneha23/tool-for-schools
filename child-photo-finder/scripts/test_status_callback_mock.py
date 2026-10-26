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


def make_response(status_code):
    response = MagicMock()
    response.status_code = status_code

    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"Mock HTTP {status_code}",
            response=response,
        )

    return response


def run_test(name, responses, expected_calls):
    service = create_service()

    with (
        patch.object(
            ingestion_module,
            "MYCLASSADMIN_STATUS_URL",
            "https://mock.invalid/PhotoAlbum/updateStatus",
        ),
        patch.object(
            ingestion_module,
            "MYCLASSADMIN_STATUS_API_KEY",
            "mock-test-key",
        ),
        patch.object(
            ingestion_module.requests,
            "post",
            side_effect=responses,
        ) as mock_post,
        patch.object(ingestion_module.time, "sleep") as mock_sleep,
    ):
        service._notify_status(FakeEvent(), "Processing")

        assert mock_post.call_count == expected_calls, (
            f"{name}: expected {expected_calls} calls, "
            f"got {mock_post.call_count}"
        )

        print(f"PASS: {name} ({mock_post.call_count} attempt(s))")


if __name__ == "__main__":
    run_test(
        "Success on first attempt",
        [make_response(200)],
        1,
    )

    run_test(
        "Retry after HTTP 500, then succeed",
        [make_response(500), make_response(200)],
        2,
    )

    run_test(
        "Stop after three HTTP 500 failures",
        [make_response(500), make_response(500), make_response(500)],
        3,
    )

    run_test(
        "Do not retry HTTP 401",
        [make_response(401)],
        1,
    )

    print("All callback retry tests passed.")
