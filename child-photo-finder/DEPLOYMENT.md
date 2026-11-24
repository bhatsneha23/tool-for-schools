# Child Photo Finder Deployment Guide

This guide covers deploying the FastAPI backend and its ingestion worker.
Deploy the API and worker as separate supervised processes. Both must use the
same PostgreSQL database, environment configuration, and Google service-account
credentials.

## 1. Deployment requirements

Prepare:

- Python 3.11 (the project has been verified with Python 3.11).
- A reachable PostgreSQL database and a dedicated database user.
- A Google Cloud service account with the Google Drive API enabled.
- An HTTPS domain/reverse proxy or a hosting platform that provides HTTPS.
- A Google Drive test folder shared with the service-account email as a reader.
- MyClassAdmin callback URL and API key, if status callbacks are required.

Use an operating system and Python environment on which `insightface`,
`onnxruntime`, and OpenCV install and run successfully. The application uses
InsightFace's `buffalo_l` model on CPU; allow outbound access for model setup
if the model is not already present.

## 2. Get the application code

On the deployment host, clone the repository and enter the application folder:

```bash
git clone <REPOSITORY_URL>
cd <REPOSITORY_DIRECTORY>/child-photo-finder
```

Do not copy a developer's `.venv` directory to the server. Create a fresh
environment and install the project requirements.

### Linux/macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Configure secrets and services

Create `child-photo-finder/.env` on the server. Do not commit this file or put
secrets in frontend/browser code.

```dotenv
DATABASE_URL=postgresql://<DB_USER>:<URL_ENCODED_PASSWORD>@<DB_HOST>:5432/<DB_NAME>
API_KEY=<LONG_RANDOM_SERVER_SIDE_KEY>
SIMILARITY_THRESHOLD=0.45
MYCLASSADMIN_STATUS_URL=https://<ADMIN_HOST>/<STATUS_ENDPOINT>
MYCLASSADMIN_STATUS_API_KEY=<CALLBACK_API_KEY>
```

`MYCLASSADMIN_STATUS_URL` and `MYCLASSADMIN_STATUS_API_KEY` may be omitted if
callbacks are not used. `SIMILARITY_THRESHOLD` is optional and defaults to
`0.45`. `GOOGLE_DRIVE_FOLDER_ID` is not needed for event creation; each event
supplies its own Drive folder link.

Use the platform's secret manager where available. On Linux, restrict access
to the configuration file and credential:

```bash
chmod 600 .env credentials/service-account.json
```

Create `credentials/service-account.json` from the service-account key through
your approved secrets deployment process. Do not put its contents in source
control, issue trackers, or logs. Share each event folder with the service
account's email address.

Before production exposure, update `allow_origins` in `main.py` to contain
only the approved portal origins; CORS is currently configured with a wildcard
and is not controlled by an environment variable. Ensure the API key is sent
only by a trusted server. The current application uses a shared API key; it
does not provide user accounts or event-level authorization.

## 4. Prepare PostgreSQL and schema

Create the database and user, then ensure the deployment host can connect using
`DATABASE_URL`. Back up any existing database before applying schema changes.

The application calls `Base.metadata.create_all()` at startup. This creates
missing tables but does not update existing tables. The migration script adds
the ingestion-job columns required by the worker, and expects
`public.ingestion_jobs` to exist.

From `child-photo-finder`, initialize missing tables and run the migration:

```bash
python -c "from app import models; from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
python scripts/migrate_ingestion_jobs.py
```

Expected migration output:

```text
ingestion_jobs schema migration completed.
```

If migration fails, do not start the worker. Confirm the database URL, schema,
permissions, and table existence; correct the issue and rerun the migration.
The migration uses `ADD COLUMN IF NOT EXISTS` and can be rerun safely.

## 5. Start and supervise the API

For production, run Uvicorn behind a TLS-terminating reverse proxy or managed
HTTPS platform. Do not expose the Uvicorn port directly to the public internet.

### Linux/macOS

```bash
cd child-photo-finder
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
```

### Windows PowerShell

```powershell
cd C:\path\to\child-photo-finder
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
```

Use a process manager such as systemd, Supervisor, Docker, Kubernetes, or the
hosting platform to start the API on boot and restart it after failures. The
proxy should forward requests to the local Uvicorn port and provide HTTPS.

## 6. Start and supervise the ingestion worker

Run one worker process initially. It polls PostgreSQL for queued jobs and must
remain running independently of the API.

```bash
cd child-photo-finder
source .venv/bin/activate
python -m app.services.ingestion_worker
```

On Windows, activate the environment using:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.services.ingestion_worker
```

Run the worker under the same process manager as the API, but as a separate
process. Configure automatic restart and capture its logs. Starting Uvicorn
alone does not process ingestion jobs.

## 7. Smoke-test the deployment

Replace `<API-DOMAIN>` with the HTTPS domain and `<API_KEY>` with the server-side
API key.

Check public health:

```bash
curl https://<API-DOMAIN>/health
```

Expected response:

```json
{"status":"healthy"}
```

Check API authentication and event listing:

```bash
curl -i https://<API-DOMAIN>/api/events \
  -H "X-API-Key: <API_KEY>"
```

An empty deployment should return HTTP 200 and:

```json
{"events":[]}
```

An invalid key should return HTTP 401.

Create a test event using a numeric, positive `event_id` and a valid Google
Drive folder URL:

```bash
curl -i -X POST https://<API-DOMAIN>/api/events \
  -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": 990001,
    "event_name": "Deployment Verification",
    "drive_link": "https://drive.google.com/drive/folders/<TEST_FOLDER_ID>"
  }'
```

Confirm the response contains a `Pending` event and job. Then check the worker
logs for a claimed job and ingestion result. After successful processing:

1. `GET /api/events` reports the test event as `Ready`.
2. `GET /api/events/990001/photos` returns the expected photo count.
3. An image or thumbnail URL returns the corresponding image.
4. Search with a suitable test portrait returns matches or a valid empty result.
5. The callback is received by MyClassAdmin if callback settings are enabled.

Remove the test event using the authenticated `DELETE /api/events/990001`
endpoint after testing. This removes database records, not the original Drive
files.

## 8. Production operations and known limitations

- Back up PostgreSQL and test restore procedures before production use.
- Monitor API and worker logs, database connectivity, Drive permissions,
  callback failures, disk usage, and failed/retrying jobs.
- Keep API, worker, database, and credential secrets in the approved secret
  store; rotate them if exposed.
- The current API key is shared and does not implement per-user or per-event
  permissions. Do not expose it in browser code.
- The current application does not implement an upload size limit. Apply a
  conservative request-body limit at the reverse proxy until an application
  limit is added.
- Dependency versions in `requirements.txt` are not pinned. For reproducible
  production releases, validate and lock the tested dependency versions before
  deployment.
- The migration documented here covers the ingestion-job columns only. Review
  any future model/schema changes and provide explicit migrations for them.
- Perform a real Drive ingestion and face-search test in the target operating
  environment; successful compilation or API health checks alone do not prove
  model and Drive integration.

For the detailed system description and API contract, see
`INTEGRATION_HANDOVER.md`. For the record of recent code fixes and checks, see
`CODE_CHANGES.md`.
