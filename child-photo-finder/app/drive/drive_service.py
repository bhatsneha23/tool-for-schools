import io
import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import requests


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]


BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


CREDENTIALS_FILE = os.path.join(
    BASE_DIR,
    "credentials",
    "google_credentials.json"
)


TOKEN_FILE = os.path.join(
    BASE_DIR,
    "credentials",
    "token.json"
)


def get_drive_service():
    credentials = None

    # Reuse previously generated token
    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    # Refresh expired token
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    # First-time login
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE,
            SCOPES
        )

        credentials = flow.run_local_server(
            port=0
        )

        with open(TOKEN_FILE, "w") as token:
            token.write(credentials.to_json())

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

        results.extend(
            response.get("files", [])
        )

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
    for a file.
    """

    service = get_drive_service()

    response = service.files().get(
        fileId=file_id,
        fields="id, mimeType, thumbnailLink"
    ).execute()

    return response.get("thumbnailLink")


def download_thumbnail(file_id):
    """
    Download the thumbnail from Google Drive using
    the authenticated Google credentials.

    Returns:
        BytesIO containing the thumbnail image.
    """

    thumbnail_link = get_thumbnail_link(file_id)

    if not thumbnail_link:
        return None

    credentials = None

    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        get_drive_service()

        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    response = requests.get(
        thumbnail_link,
        headers={
            "Authorization": f"Bearer {credentials.token}"
        },
        timeout=30
    )

    response.raise_for_status()

    thumbnail_data = io.BytesIO(
        response.content
    )

    thumbnail_data.seek(0)

    return thumbnail_data