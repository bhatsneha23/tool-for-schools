Child Photo Finder API — Integration Handover

1. Complete Python/FastAPI Project Source Code

The complete backend source code is provided in this repository.

Project Structure

File                        Purpose

main.py            Creates the FastAPI application, configures CORS and registers API routes.

app/config.py      Loads environment variables and application configuration.

app/database.py    Creates the SQLAlchemy database connection and session management.

app/models.py      Defines Event, Photo and FaceEmbedding database models.

app/api/routes.py   Defines API endpoints, authentication, validation and image retrieval.

app/face/face_service.py    Performs face detection and generates normalized face embeddings.

app/services/ingestion_service.py     Ingests Google Drive photos and stores their metadata and face embeddings.

app/services/matching_service.py    Performs event-specific face matching using cosine        similarity.

app/services/event_service.py  Provides event creation and event lookup functionality.

app/drive/drive_service.py  Handles Google Drive authentication, file listing and file downloads.

scripts/ingest_drive.py  Runs photo ingestion for the configured Google Drive folder.

scripts/find_child.py   Local command-line utility for testing child photo search.

tests/test_face_service.py   Face service test module.





The repository is a backend/API service and does not contain a separate parent-facing frontend.

The current test file is a manual script rather than a pytest suite. Running pytest currently reports that no tests are collected.



2. Requirements / Dependencies

The project uses the following dependencies:



fastapi

uvicorn[standard]

python-dotenv

sqlalchemy

psycopg2-binary

google-api-python-client

google-auth

google-auth-httplib2

google-auth-oauthlib

opencv-python

insightface

onnxruntime

numpy

python-multipart

pillow

requests





These are available in requirements.txt.

3. Model Files and Model Details

Face Recognition Model

The project uses:



Framework: InsightFace

Model Pack: buffalo_l

Execution Provider: CPUExecutionProvider

Detection Size: 640 × 640





The buffalo_l model pack is loaded by InsightFace at runtime.

The face service:

Decodes the uploaded image using OpenCV.

Detects faces using InsightFace.

Generates a face embedding for each detected face.

L2-normalizes each embedding.

Stores the normalized embedding as JSON for ingested event photos.

Multiple Faces

For event photos, every detected face is stored separately.

For a parent search image, if multiple faces are detected, the system selects the largest detected face as the query face.

4. FastAPI API Endpoints Currently Available

All /api endpoints require:

X-API-Key: <API_KEY>

Endpoint 1 — Create Event (Admin)

POST /api/events

Purpose: Creates a new event from the MyClassAdmin Admin panel using the event name and Google Drive folder link.

The API extracts the Google Drive folder ID, generates a public event identifier such as EVT003, and stores the event in PostgreSQL.

Important: Event creation starts the event-aware Google Drive photo-ingestion flow. The event status is updated according to the actual ingestion result.

Endpoint 2 — Get Events

GET /api/events

Purpose: Returns all events available to the portal, including the event ID, event name, Google Drive link, and current status.

Endpoint 3 — Get Event Photos

GET /api/events/{event_id}/photos

Purpose: Returns all photos associated with the selected event. This can be used for the portal's View All Photos functionality.

Endpoint 4 — Search for a Child

POST /api/events/{event_id}/search

Purpose: Accepts a child's image and searches for matching photos within the selected event.

The image is sent as multipart/form-data using the field:

file

Endpoint 5 — Retrieve Photo Image

GET /api/photos/{photo_id}/image

Purpose: Retrieves and streams the original/full-quality image associated with the photo ID.

Endpoint 6 — Retrieve Photo Thumbnail

GET /api/photos/{photo_id}/thumbnail

Purpose: Retrieves a smaller JPEG thumbnail for faster gallery loading. The original image endpoint remains available for full-quality viewing/download.

5. API Request and Response Formats

5.1 Creating an Event from the Admin Panel

The MyClassAdmin Admin panel sends the event name and Google Drive folder link to:

POST /api/events

X-API-Key: <API_KEY>

Content-Type: application/json

Request body:

{

  "event_name": "Annual Sports Meet 2026",

  "drive_link": "https://drive.google.com/drive/folders/<FOLDER_ID>"

}

The API:

Validates the event name.

Extracts the Google Drive folder ID.

Checks for a duplicate event name.

Checks whether the Drive folder is already associated with another event.

Generates a public event ID such as EVT003.

Stores the event in PostgreSQL.

Returns the created event details.

Example response:

{

  "message": "Event created and photo ingestion completed.",

  "event": {

    "event_id": "EVT003",

    "event_name": "Annual Sports Meet 2026",

    "drive_folder_id": "<FOLDER_ID>",

    "drive_link": "https://drive.google.com/drive/folders/<FOLDER_ID>",

    "status": "Ready"

  }

}

The event starts with status Pending. During synchronous ingestion it moves to Processing. A successful ingestion results in Ready; an unsuccessful or failed ingestion results in Failed. The POST response is returned after the ingestion attempt completes.

The event status can be: Pending, Processing, Ready, or Failed.

Possible validation responses:

400 — invalid or empty event name / invalid Drive folder link

409 — duplicate event name / Drive folder already associated with an event

5.2 Uploading / Registering a Child's Photo

There is currently no separate child-registration endpoint.

The current system does not create a permanent child profile from the uploaded image.

The uploaded image is used as a search/query image through:

POST /api/events/{event_id}/search

Request

POST /api/events/EVT002/search

X-API-Key: <API_KEY>

Content-Type: multipart/form-data

Form field:

file = child.jpg

Example cURL

curl -X POST "https://<API-DOMAIN>/api/events/EVT002/search" -H "X-API-Key: <API_KEY>" -F "file=@child.jpg"

5.3 Searching for a Child's Photos

The search response contains:

event_id

event_name

match_count

matching photo_id

file_name

similarity

image_url

Example:

{

  "event_id": "EVT002",

  "event_name": "Annual Day 2026",

  "match_count": 6,

  "matches": [

    {

      "photo_id": 14,

      "file_name": "IMG_1058.JPG",

      "similarity": 0.7600321173667908,

      "image_url": "/api/photos/14/image"

    },

    {

      "photo_id": 15,

      "file_name": "IMG_1057.JPG",

      "similarity": 0.6708787679672241,

      "image_url": "/api/photos/15/image"

    }

  ]

}

The API returns a maximum of 20 ranked matches.

5.4 Getting the Matched Event Photos

After receiving a photo_id, the portal can request:

GET /api/photos/{photo_id}/image

X-API-Key: <API_KEY>

The API retrieves the corresponding Google Drive file and returns the actual image bytes.

For View All Photos, the portal can use:

GET /api/events/{event_id}/photos

Example response:

{

  "event_id": "EVT002",

  "event_name": "Annual Day 2026",

  "photo_count": 1034,

  "photos": [

    {

      "photo_id": 14,

      "file_name": "IMG_1058.JPG",

      "image_url": "/api/photos/14/image"

    }

  ]

}

6. How the Child's Image / Face Is Stored and Identified

The current system does not permanently store the uploaded child's image or create a child-specific face record.

Event Photo Registration

Before searching, event photos are ingested from Google Drive:



Google Drive Photo

        ↓

Face Detection

        ↓

Face Embedding Generation

        ↓

Embedding Normalization

        ↓

PostgreSQL





For every detected face, the system stores:



photo_id

face_index

embedding



Search

When a parent uploads a child's image:



Child Image

     ↓

Face Detection

     ↓

Face Embedding

     ↓

Normalization

     ↓

Compare with selected event embeddings

     ↓

Matching Photos





The uploaded image is processed in memory for the search request and is not registered as a permanent child profile by the current API.

7. Google Drive Integration

The application uses the Google Drive API with OAuth 2.0 and read-only Drive access.

Credentials

The local application uses:



credentials/google_credentials.json

credentials/token.json





These files contain credentials/tokens and must not be shared or committed to Git.

Event / Folder Mapping

Each event has a Google Drive folder ID stored in the events table:



event_id

event_name

drive_folder_id





Example:



EVT001

Annual Day 2026

<Google Drive folder ID>



Photo Metadata

The actual photos remain in Google Drive.

PostgreSQL stores:



drive_file_id

file_name

mime_type

drive_url





The drive_file_id is used to retrieve the original image.

Retrieval Flow

Portal

   ↓

photo_id

   ↓

PostgreSQL

   ↓

drive_file_id

   ↓

Google Drive

   ↓

Actual Image



8. Database Structure / Tables

The project uses PostgreSQL with SQLAlchemy.

The primary tables are:



events

   |

   | 1-to-many

   ↓

photos

   |

   | 1-to-many

   ↓

face_embeddings



events

| Field | Description |

|---|---|

| id | Internal primary key |

| event_id | Public event identifier such as EVT001 |

| event_name | Event name |

| drive_folder_id | Google Drive folder ID |

| created_at | Creation timestamp |

photos

| Field | Description |

|---|---|

| id | Internal photo ID |

| event_id | Foreign key to events.id |

| drive_file_id | Google Drive file ID |

| file_name | Original file name |

| mime_type | Image MIME type |

| drive_url | Google Drive URL |

| created_at | Creation timestamp |

face_embeddings

| Field | Description |

|---|---|

| id | Internal embedding ID |

| photo_id | Foreign key to photos.id |

| face_index | Detected face index |

| embedding | Normalized face embedding stored as JSON |

| created_at | Creation timestamp |

A single photo may contain multiple faces, so multiple embedding records can belong to the same photo.

9. Environment Variables / Configuration

The application loads configuration using python-dotenv.

The application configuration uses the following environment variables:



DATABASE_URL=<PostgreSQL connection string>

GOOGLE_DRIVE_FOLDER_ID=<Google Drive folder ID>

SIMILARITY_THRESHOLD=0.45

API_KEY=<API key>





A safe .env.example can be provided:



DATABASE_URL=

SIMILARITY_THRESHOLD=0.45

API_KEY=



10. Steps to Run the Project Locally

Step 1 — Clone the repository

git clone <repository-url>

*cd* child-photo-finder



Step 2 — Create a virtual environment

Windows:



python -m venv venv





Activate:



.\venv\Scripts\Activate.ps1



Step 3 — Install dependencies

pip install -r requirements.txt



Step 4 — Configure .env

Create a .env file with the required environment variables.

Step 5 — Configure Google Drive

Place the Google OAuth client file at:



credentials/google_credentials.json





The application creates token.json after successful OAuth authorization.

Step 6 — Configure PostgreSQL

Create/configure the PostgreSQL database and set:



DATABASE_URL



Step 7 — Start FastAPI

uvicorn main:app --reload





Local API:



http://127.0.0.1:8000





Swagger:



http://127.0.0.1:8000/docs



11. Python and FastAPI/Uvicorn Versions

The current development environment uses:



Python: 3.11.9

FastAPI: 0.120.2

Uvicorn: 0.38.0



12. Sample API Requests / Responses

Create Event

POST /api/events

X-API-Key: <API_KEY>

Content-Type: application/json

Request:

{

  "event_name": "Annual Sports Meet 2026",

  "drive_link": "https://drive.google.com/drive/folders/<FOLDER_ID>"

}

Response:

{

  "message": "Event created and photo ingestion completed.",

  "event": {

    "event_id": "EVT003",

    "event_name": "Annual Sports Meet 2026",

    "drive_folder_id": "<FOLDER_ID>",

    "drive_link": "https://drive.google.com/drive/folders/<FOLDER_ID>",

    "status": "Ready"

  }

}

Get Events

GET /api/events

X-API-Key: <API_KEY>

Response:

{

  "events": [

    {

      "event_id": "EVT001",

      "event_name": "Sports Day",

      "drive_link": "https://drive.google.com/drive/folders/<SPORTS_DAY_FOLDER_ID>",

      "status": "Ready"

    },

    {

      "event_id": "EVT002",

      "event_name": "Annual Day 2026",

      "drive_link": "https://drive.google.com/drive/folders/<ANNUAL_DAY_FOLDER_ID>",

      "status": "Ready"

    }

  ]

}

Get Event Photos

GET /api/events/EVT002/photos

X-API-Key: <API_KEY>

Response:

{

  "event_id": "EVT002",

  "event_name": "Annual Day 2026",

  "photo_count": 1034,

  "photos": [

    {

      "photo_id": 14,

      "file_name": "IMG_1058.JPG",

      "image_url": "/api/photos/14/image"

    }

  ]

}

Search Child

POST /api/events/EVT002/search

X-API-Key: <API_KEY>

Content-Type: multipart/form-data

Form field:

file = child.jpg

Response:

{

  "event_id": "EVT002",

  "event_name": "Annual Day 2026",

  "match_count": 6,

  "matches": [

    {

      "photo_id": 14,

      "file_name": "IMG_1058.JPG",

      "similarity": 0.7600321173667908,

      "image_url": "/api/photos/14/image"

    }

  ]

}

Get Actual Image

GET /api/photos/14/image

X-API-Key: <API_KEY>

13. Frontend / UI

No separate frontend application is included in this repository.

The MyClassAdmin application provides the Admin UI for event management and the Parent Portal UI for child photo search.

Admin Event Management Flow

MyClassAdmin Admin Panel

        ↓

Enter Event Name

        +

Enter Google Drive Link

        ↓

POST /api/events

        ↓

Event Created in PostgreSQL

        ↓

GET /api/events

        ↓

Admin sees Event Name + Google Drive Link + Status

The current POST /api/events endpoint creates the event and starts the event-aware Google Drive photo-ingestion flow. The returned status reflects the ingestion result.

Parent Photo Search Flow

MyClassAdmin Parent Portal

        ↓

GET /api/events

        ↓

Select Event

        ↓

Event ID

        ↓

Find My Child

        ↓

Upload Child Image

        ↓

POST /api/events/{event_id}/search

        ↓

Matching Photo IDs + Image URLs

        ↓

Portal displays actual photos

14. How Photo Matching Works

The system uses face-embedding-based facial recognition, not generic image similarity.

Matching Pipeline

Uploaded Child Image

        ↓

Face Detection

        ↓

Select Largest Face

        ↓

Generate Face Embedding

        ↓

L2 Normalize Embedding

        ↓

Retrieve Stored Embeddings

for Selected Event

        ↓

Cosine Similarity

        ↓

Apply Similarity Threshold

        ↓

Rank Matches

        ↓

Return Top 20



Similarity

Both query and stored embeddings are normalized.

The similarity is calculated as:



similarity = query_embedding · stored_embedding





This is equivalent to cosine similarity after normalization.

Event Scoping

Only embeddings belonging to the selected event are compared.

Therefore:



EVT001 Search

     ↓

Only EVT001 embeddings

     ↓

EVT001 matching photos





Photos from other events are not included in the comparison.

Multiple Faces in Event Photos

If one event photo contains multiple faces, each face has its own embedding.

If multiple embeddings from the same photo match, only the highest similarity score for that photo is returned.









SIMILARITY_THRESHOLD=0.45





The value can be changed through the .env configuration.

15. Pending Issues / Current Limitations

15.0 Admin Event Management

The backend supports Admin-side event creation through POST /api/events.

The Admin UI can submit:

Event Name

Google Drive Link

and can populate the Existing Events table from GET /api/events, which returns:

event_id

event_name

drive_link

status

Event creation and photo ingestion are handled as part of the same event-creation flow in the current implementation.







15.1 No Separate Child Registration Endpoint

There is currently no dedicated endpoint for registering a child's profile or face.

The existing workflow uses event photo ingestion to create the searchable face embeddings.

15.2 Event Creation and Photo Ingestion

Events can be created from the Admin panel using:

POST /api/events

The endpoint stores the event name and Google Drive folder ID in PostgreSQL and starts event-aware photo ingestion.

Current workflow:

Admin creates event

        ↓

POST /api/events

        ↓

Event record created with status Pending

        ↓

Ingestion starts and status becomes Processing

        ↓

Google Drive photos processed

        ↓

Photos + face embeddings associated with the event

        ↓

Status becomes Ready when ingestion completes successfully, or Failed when the result is incomplete or unsuccessful

The event status therefore reflects the actual ingestion state.

15.3 No Separate Frontend

The repository contains the backend/API only.







15.4 Google Drive Dependency

Actual event photos remain in Google Drive.

Image retrieval therefore depends on:

valid Google OAuth credentials,

access to the relevant Drive folder,

availability of the referenced Drive files.

For production, company-approved cloud/object storage may be considered for long-term image serving.

15.5 Current Embedding Search

The current implementation loads the event's stored embeddings and performs cosine similarity using NumPy.

For larger production datasets, vector-indexed similarity search can be considered.

15.6 Production Configuration

For development, CORS currently allows all origins.

For production, CORS should be restricted to the approved MyClassAdmin portal domain.

The API key should preferably be handled server-to-server by the portal backend rather than exposed directly in browser-side JavaScript.

