# Child Photo Finder API — Integration Handover

This document is prepared specifically for the MyClassAdmin parent-side integration of the Photo Search functionality.

---

## 1. Complete Python/FastAPI Project Source Code

The complete backend source code is provided in this repository.

### Project Structure
```
File                        Purpose

main.py            Creates the FastAPI application, configures CORS and registers API routes.

app/config.py      Loads environment variables and application configuration.

app/database.py    Creates the SQLAlchemy database connection and session management.

app/models.py      Defines Event, Photo and FaceEmbedding database models.

app/api/routes.py   Defines API endpoints, authentication, validation and image retrieval.

app/face/face_service.py    Performs face detection and generates normalized face embeddings.

app/services/ingestion_service.py     Ingests Google Drive photos and stores their metadata and face embeddings.

app/services/matching_service.py    Performs event-specific face matching using cosine        similarity.

app/services/event_service.py  Provides event creation and event lookup functionality.

app/drive/drive_service.py  Handles Google Drive authentication, file listing and file downloads.

scripts/ingest_drive.py  Runs photo ingestion for the configured Google Drive folder.

scripts/find_child.py   Local command-line utility for testing child photo search.

tests/test_face_service.py   Face service test module.


The repository is a backend/API service and does not contain a separate parent-facing frontend.
```
---

## 2. Requirements / Dependencies

The project uses the following dependencies:

```text
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
```

These are available in `requirements.txt`.

---

## 3. Model Files and Model Details

### Face Recognition Model

The project uses:

```text
Framework: InsightFace
Model Pack: buffalo_l
Execution Provider: CPUExecutionProvider
Detection Size: 640 × 640
```

The `buffalo_l` model pack is loaded by InsightFace at runtime.

The face service:
- Decodes the uploaded image using OpenCV.
- Detects faces using InsightFace.
- Generates a face embedding for each detected face.
- L2-normalizes each embedding.
- Stores the normalized embedding as JSON for ingested event photos.

### Multiple Faces

For event photos, every detected face is stored separately.

For a parent search image, if multiple faces are detected, the system selects the largest detected face as the query face.

---

## 4. FastAPI API Endpoints Currently Available

All `/api` endpoints require:

```http
X-API-Key: <API_KEY>
```

### Endpoint 1 — Get Events

```http
GET /api/events
```

Purpose: Returns all events available to the portal.

### Endpoint 2 — Get Event Photos

```http
GET /api/events/{event_id}/photos
```

Purpose: Returns all photos associated with the selected event. This can be used for the portal's **View All Photos** functionality.

### Endpoint 3 — Search for a Child

```http
POST /api/events/{event_id}/search
```

Purpose: Accepts a child's image and searches for matching photos within the selected event.

The image is sent as `multipart/form-data` using the field:

```text
file
```

### Endpoint 4 — Retrieve Photo Image

```http
GET /api/photos/{photo_id}/image
```

Purpose: Retrieves and streams the actual image associated with the photo ID.

---

## 5. API Request and Response Formats

### 5.1 Uploading / Registering a Child's Photo

There is currently **no separate child-registration endpoint**.

The current system does not create a permanent child profile from the uploaded image.

The uploaded image is used as a search/query image through:

```http
POST /api/events/{event_id}/search
```

### Request

```http
POST /api/events/EVT001/search
X-API-Key: <API_KEY>
Content-Type: multipart/form-data
```

Form field:

```text
file = child.jpg
```

### Example cURL

```bash
curl -X POST   "https://<API-DOMAIN>/api/events/EVT001/search"   -H "X-API-Key: <API_KEY>"   -F "file=@child.jpg"
```

---

### 5.2 Searching for a Child's Photos

The search response contains:

- `event_id`
- `event_name`
- `match_count`
- matching `photo_id`
- `file_name`
- `similarity`
- `image_url`

Example:

```json
{
  "event_id": "EVT001",
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
```

The API returns a maximum of 20 ranked matches.

---

### 5.3 Getting the Matched Event Photos

After receiving a `photo_id`, the portal can request:

```http
GET /api/photos/{photo_id}/image
X-API-Key: <API_KEY>
```

The API retrieves the corresponding Google Drive file and returns the actual image bytes.

For **View All Photos**, the portal can use:

```http
GET /api/events/{event_id}/photos
```

Example response:

```json
{
  "event_id": "EVT001",
  "event_name": "Annual Day 2026",
  "photo_count": 487,
  "photos": [
    {
      "photo_id": 14,
      "file_name": "IMG_1058.JPG",
      "image_url": "/api/photos/14/image"
    }
  ]
}
```

---

## 6. How the Child's Image / Face Is Stored and Identified

The current system does not permanently store the uploaded child's image or create a child-specific face record.

### Event Photo Registration

Before searching, event photos are ingested from Google Drive:

```text
Google Drive Photo
        ↓
Face Detection
        ↓
Face Embedding Generation
        ↓
Embedding Normalization
        ↓
PostgreSQL
```

For every detected face, the system stores:

```text
photo_id
face_index
embedding
```

### Search

When a parent uploads a child's image:

```text
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
```

The uploaded image is processed in memory for the search request and is not registered as a permanent child profile by the current API.

---

## 7. Google Drive Integration

The application uses the Google Drive API with OAuth 2.0 and read-only Drive access.

### Credentials

The local application uses:

```text
credentials/google_credentials.json
credentials/token.json
```

These files contain credentials/tokens and must not be shared or committed to Git.

### Event / Folder Mapping

Each event has a Google Drive folder ID stored in the `events` table:

```text
event_id
event_name
drive_folder_id
```

Example:

```text
EVT001
Annual Day 2026
<Google Drive folder ID>
```

### Photo Metadata

The actual photos remain in Google Drive.

PostgreSQL stores:

```text
drive_file_id
file_name
mime_type
drive_url
```

The `drive_file_id` is used to retrieve the original image.

### Retrieval Flow

```text
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
```

---

## 8. Database Structure / Tables

The project uses PostgreSQL with SQLAlchemy.

The primary tables are:

```text
events
   |
   | 1-to-many
   ↓
photos
   |
   | 1-to-many
   ↓
face_embeddings
```

### `events`

| Field | Description |
|---|---|
| `id` | Internal primary key |
| `event_id` | Public event identifier such as `EVT001` |
| `event_name` | Event name |
| `drive_folder_id` | Google Drive folder ID |
| `created_at` | Creation timestamp |

### `photos`

| Field | Description |
|---|---|
| `id` | Internal photo ID |
| `event_id` | Foreign key to `events.id` |
| `drive_file_id` | Google Drive file ID |
| `file_name` | Original file name |
| `mime_type` | Image MIME type |
| `drive_url` | Google Drive URL |
| `created_at` | Creation timestamp |

### `face_embeddings`

| Field | Description |
|---|---|
| `id` | Internal embedding ID |
| `photo_id` | Foreign key to `photos.id` |
| `face_index` | Detected face index |
| `embedding` | Normalized face embedding stored as JSON |
| `created_at` | Creation timestamp |

A single photo may contain multiple faces, so multiple embedding records can belong to the same photo.

---

## 9. Environment Variables / Configuration

The application loads configuration using `python-dotenv`.

The required environment variable names are:

```env
DATABASE_URL=<PostgreSQL connection string>
GOOGLE_DRIVE_FOLDER_ID=<Google Drive folder ID>
SIMILARITY_THRESHOLD=0.45
API_KEY=<API key>
```

A safe `.env.example` can be provided:

```env
DATABASE_URL=
GOOGLE_DRIVE_FOLDER_ID=
SIMILARITY_THRESHOLD=0.45
API_KEY=
```

---

## 10. Steps to Run the Project Locally

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd child-photo-finder
```

### Step 2 — Create a virtual environment

Windows:

```powershell
python -m venv venv
```

Activate:

```powershell
.env\Scripts\Activate.ps1
```

### Step 3 — Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 4 — Configure `.env`

Create a `.env` file with the required environment variables.

### Step 5 — Configure Google Drive

Place the Google OAuth client file at:

```text
credentials/google_credentials.json
```

The application creates `token.json` after successful OAuth authorization.

### Step 6 — Configure PostgreSQL

Create/configure the PostgreSQL database and set:

```text
DATABASE_URL
```

### Step 7 — Start FastAPI

```powershell
uvicorn main:app --reload
```

Local API:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

## 11. Python and FastAPI/Uvicorn Versions

The current development environment uses:

```text
Python: 3.11.9
FastAPI: 0.120.2
Uvicorn: 0.38.0
```

---

## 12. Sample API Requests / Responses

### Get Events

```http
GET /api/events
X-API-Key: <API_KEY>
```

Response:

```json
{
  "events": [
    {
      "event_id": "EVT001",
      "event_name": "Annual Day 2026"
    }
  ]
}
```

### Get Event Photos

```http
GET /api/events/EVT001/photos
X-API-Key: <API_KEY>
```

Response:

```json
{
  "event_id": "EVT001",
  "event_name": "Annual Day 2026",
  "photo_count": 487,
  "photos": [
    {
      "photo_id": 14,
      "file_name": "IMG_1058.JPG",
      "image_url": "/api/photos/14/image"
    }
  ]
}
```

### Search Child

```http
POST /api/events/EVT001/search
X-API-Key: <API_KEY>
Content-Type: multipart/form-data
```

Form field:

```text
file = child.jpg
```

Response:

```json
{
  "event_id": "EVT001",
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
```

### Get Actual Image

```http
GET /api/photos/14/image
X-API-Key: <API_KEY>
```

---

## 13. Frontend / UI

No separate frontend application is included in the repository.

The backend has been tested using:

```text
FastAPI Swagger UI
http://127.0.0.1:8000/docs

text
MyClassAdmin Parent Portal
          ↓
Select Event
          ↓
Event ID
          ↓
Find My Child
          ↓
Upload Child Image
          ↓
FastAPI Search API
          ↓
Matching Photo IDs + Image URLs
          ↓
Portal displays actual photos
```

---

## 14. How Photo Matching Works

The system uses **face-embedding-based facial recognition**, not generic image similarity.

### Matching Pipeline

```text
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
```

### Similarity

Both query and stored embeddings are normalized.

The similarity is calculated as:

```text
similarity = query_embedding · stored_embedding
```

This is equivalent to cosine similarity after normalization.

### Event Scoping

Only embeddings belonging to the selected event are compared.

Therefore:

```text
EVT001 Search
     ↓
Only EVT001 embeddings
     ↓
EVT001 matching photos
```

Photos from other events are not included in the comparison.

### Multiple Faces in Event Photos

If one event photo contains multiple faces, each face has its own embedding.

If multiple embeddings from the same photo match, only the highest similarity score for that photo is returned.


```text
SIMILARITY_THRESHOLD=0.45
```

The value can be changed through the `.env` configuration.

---

# 15. Pending Issues / Current Limitations

## 15.1 No Separate Child Registration Endpoint

There is currently no dedicated endpoint for registering a child's profile or face.

The existing workflow uses event photo ingestion to create the searchable face embeddings.

## 15.2 Ingestion Is Currently Folder-Based

The current ingestion script uses:

```text
GOOGLE_DRIVE_FOLDER_ID
```

directly.

The event model contains a `drive_folder_id`, but the ingestion script does not currently perform automatic:

```text
Event ID
   ↓
Event Record
   ↓
drive_folder_id
   ↓
Ingestion
```

This should be considered when integrating automated event creation/ingestion.

## 15.3 No Separate Frontend

The repository contains the backend/API only.


## 15.4 Google Drive Dependency

Actual event photos remain in Google Drive.

Image retrieval therefore depends on:
- valid Google OAuth credentials,
- access to the relevant Drive folder,
- availability of the referenced Drive files.

For production, company-approved cloud/object storage may be considered for long-term image serving.

## 15.5 Current Embedding Search

The current implementation loads the event's stored embeddings and performs cosine similarity using NumPy.

For larger production datasets, vector-indexed similarity search can be considered.

## 15.6 Production Configuration

For development, CORS currently allows all origins.

For production, CORS should be restricted to the approved MyClassAdmin portal domain.

The API key should preferably be handled server-to-server by the portal backend rather than exposed directly in browser-side JavaScript.

---

# 16. Integration Summary for MyClassAdmin

After deployment, the integration engineer will need:

```text
API Base URL:
<API-DOMAIN>

Swagger:
<API-DOMAIN>/docs

Authentication:
X-API-Key

Event Listing:
GET /api/events

View All Photos:
GET /api/events/{event_id}/photos

Child Photo Search:
POST /api/events/{event_id}/search

Photo Retrieval:
GET /api/photos/{photo_id}/image
```

