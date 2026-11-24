# Ingestion Job Schema Update

## Purpose

The `IngestionJob` SQLAlchemy model already contains the fields used by
`app/services/ingestion_worker.py`.

The change prepares existing PostgreSQL databases for those fields by adding a
safe migration script. It is required only if the physical `ingestion_jobs`
table was created before the fields were added or was created manually.

## Code Changes

The model and worker use the following fields:

| Field | Type | Purpose |
| --- | --- | --- |
| `next_retry_at` | `TIMESTAMPTZ`, nullable | Time at which a retry job becomes eligible. |
| `last_error` | `TEXT`, nullable | Last error or worker failure description. |
| `created_at` | `TIMESTAMPTZ`, not null | Job creation timestamp. |
| `updated_at` | `TIMESTAMPTZ`, not null | Last job update timestamp used for stale-job recovery. |

No model field change was necessary because `app/models.py` already declares
these fields.

## Files Added or Changed

| File | Change |
| --- | --- |
| `app/models.py` | No source change required; it already defines the four fields. |
| `scripts/migrate_ingestion_jobs.py` | Added a PostgreSQL migration script that safely adds missing columns. |
| `INGESTION_JOB_SCHEMA_UPDATE.md` | Documents the change and deployment steps. |

No matching algorithm or Google Drive logic was changed. The API now includes
the documented `GET /api/events` event-list endpoint, and an empty Drive
folder is treated as a completed ingestion with event status `Ready`.

## Integrator Deployment Steps

Run these steps after pulling the code.

### 1. Configure the Environment

Ensure `.env` contains a valid PostgreSQL connection:

```dotenv
DATABASE_URL=postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DATABASE>
```

### 2. Install Dependencies

```bash
cd child-photo-finder
pip install -r requirements.txt
```

### 3. Run the Migration

```bash
python scripts/migrate_ingestion_jobs.py
```

The script executes PostgreSQL `ADD COLUMN IF NOT EXISTS` statements. Existing
database data is preserved. It is safe to run more than once.

### 4. Restart the API

Restart the FastAPI process after the migration:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

### 5. Restart or Start the Worker

```bash
python -m app.services.ingestion_worker
```

The API and worker must use the same `DATABASE_URL`.

## SQL Applied by the Script

For reference, the script adds:

```sql
ALTER TABLE ingestion_jobs
ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;

ALTER TABLE ingestion_jobs
ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE ingestion_jobs
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
NOT NULL DEFAULT NOW();

ALTER TABLE ingestion_jobs
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
NOT NULL DEFAULT NOW();
```

## Verification

After migration and restart:

1. Confirm the API health endpoint responds.
2. Create or select a test event.
3. Confirm the event receives a `Pending` ingestion job.
4. Confirm the worker claims the job and updates it to `Processing`.
5. Confirm successful ingestion changes the event to `Ready`.
6. Confirm failure handling changes the job to `Retrying` or `Failed` and
   stores `last_error`.
7. Confirm `next_retry_at` and `updated_at` are populated as expected.

The migration has been run successfully against the configured PostgreSQL
database, and all four required columns were verified afterward.
