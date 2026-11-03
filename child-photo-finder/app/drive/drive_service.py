
import io
import os
import re

import requests

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

SERVICE_ACCOUNT_FILE = os.path.join(
    BASE_DIR,
    "credentials",
    "service-account.json"
)


def get_drive_credentials():
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )


def get_drive_service():
    credentials = get_drive_credentials()

    return build(
        "drive",
        "v3",
        credentials=credentials
    )


def list_files_in_folder(folder_id):
    service = get_drive_service()

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    results = []
    page_token = None

    while True:
        response = service.files().list(
            q=query,
            spaces="drive",
            fields=(
                "nextPageToken, "
                "files(id, name, mimeType, webViewLink, thumbnailLink)"
            ),
            pageToken=page_token
        ).execute()

        results.extend(response.get("files", []))

        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return results


def download_file(file_id):
    """
    Download the original full-quality file from Google Drive.
    """
    service = get_drive_service()

    request = service.files().get_media(
        fileId=file_id
    )

    file_data = io.BytesIO()

    downloader = MediaIoBaseDownload(
        file_data,
        request
    )

    done = False

    while not done:
        _, done = downloader.next_chunk()

    file_data.seek(0)

    return file_data


def get_thumbnail_link(file_id):
    """
    Get the temporary Google Drive thumbnail URL
    and request a larger thumbnail.
    """
    service = get_drive_service()

    response = service.files().get(
        fileId=file_id,
        fields="id, mimeType, thumbnailLink"
    ).execute()

    thumbnail_link = response.get("thumbnailLink")

    if not thumbnail_link:
        return None

    if "=s" in thumbnail_link:
        thumbnail_link = re.sub(
            r"=s\d+",
            "=s800",
            thumbnail_link
        )
    else:
        thumbnail_link += "=s800"

    return thumbnail_link


def download_thumbnail(file_id):
    """
    Download thumbnail using Service Account credentials.
    Returns BytesIO containing the thumbnail image.
    """
    thumbnail_link = get_thumbnail_link(file_id)

    if not thumbnail_link:
        return None

    credentials = get_drive_credentials()
    credentials.refresh(Request())

    response = requests.get(
        thumbnail_link,
        headers={
            "Authorization": f"Bearer {credentials.token}"
        },
        timeout=30
    )

    response.raise_for_status()

    thumbnail_data = io.BytesIO(response.content)
    thumbnail_data.seek(0)

    return thumbnail_data
