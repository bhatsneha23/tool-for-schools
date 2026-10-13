import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

GOOGLE_DRIVE_FOLDER_ID = os.getenv(
    "GOOGLE_DRIVE_FOLDER_ID"
)

SIMILARITY_THRESHOLD = float(
    os.getenv("SIMILARITY_THRESHOLD", "0.45")
)

# Existing FastAPI API key — keep unchanged
API_KEY = os.getenv("API_KEY")

# MyClassAdmin status callback configuration
MYCLASSADMIN_STATUS_URL = os.getenv(
    "MYCLASSADMIN_STATUS_URL"
)

MYCLASSADMIN_STATUS_API_KEY = os.getenv(
    "MYCLASSADMIN_STATUS_API_KEY"
)
