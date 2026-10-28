
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import IngestionJob, Event
from app.services.event_lock import event_lock
from app.services.ingestion_service import IngestionService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3
RETRY_DELAY_SECONDS = 10
STALE_JOB_MINUTES = 15


def _mark_event_failed(db, event, reason: str) -> None:
    """Mark an event failed and notify MyClassAdmin if its status changes."""
    if event is None or event.status == "Failed":
        return

    event.status = "Failed"
    db.commit()

    try:
        IngestionService(db)._notify_status(event, "Failed")
    except Exception:
        logger.exception(
            "Failed to notify MyClassAdmin for event %s.",
            event.event_id,
        )


def claim_job() -> int | None:
    """Atomically claim one eligible ingestion job."""

    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(minutes=STALE_JOB_MINUTES)

        job = (
            db.query(IngestionJob)
            .filter(
                or_(
                    IngestionJob.status == "Pending",
                    (
                        (IngestionJob.status == "Retrying")
                        & (
                            IngestionJob.next_retry_at.is_(None)
                            | (IngestionJob.next_retry_at <= now)
                        )
                    ),
                    (
                        (IngestionJob.status == "Processing")
                        & (IngestionJob.updated_at < stale_before)
                    ),
                )
            )
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .with_for_update(skip_locked=True)
            .first()
        )

        if job is None:
            return None

        # Never start another attempt after the configured limit.
        if job.attempts >= job.max_attempts:
            job.status = "Failed"
            job.next_retry_at = None
            job.last_error = (
                job.last_error
                or "Maximum attempts exhausted before recovery."
            )

            event = (
                db.query(Event)
                .filter(Event.id == job.event_id)
                .first()
            )

            should_notify = (
                event is not None and event.status != "Failed"
            )

            if should_notify:
                event.status = "Failed"

            db.commit()

            if should_notify:
                try:
                    IngestionService(db)._notify_status(event, "Failed")
                except Exception:
                    logger.exception(
                        "Failed to notify MyClassAdmin for event %s.",
                        event.event_id,
                    )

            logger.error(
                "Job %s marked Failed: maximum attempts exhausted.",
                job.id,
            )
            return None

        job.attempts += 1
        job.status = "Processing"
        job.next_retry_at = None
        job.updated_at = now

        # Preserve the previous error until success, so it remains
        # available if the worker crashes during this attempt.
        job_id = job.id
        event_id = job.event_id
        attempt = job.attempts
        max_attempts = job.max_attempts

        db.commit()

        logger.info(
            "Claimed job_id=%s event_id=%s attempt=%s/%s",
            job_id,
            event_id,
            attempt,
            max_attempts,
        )

        return job_id


def schedule_failure(job_id: int, error: Exception) -> None:
    """Record a failed attempt and schedule a retry if allowed."""

    with SessionLocal() as db:
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.id == job_id)
            .with_for_update()
            .first()
        )

        if job is None:
            return

        # Do not overwrite Completed, Failed, or already Retrying jobs.
        if job.status != "Processing":
            logger.info(
                "Skipping failure update for job %s; status is %s.",
                job_id,
                job.status,
            )
            return

        job.last_error = str(error)[:4000]

        if job.attempts >= job.max_attempts:
            job.status = "Failed"
            job.next_retry_at = None

            event = (
                db.query(Event)
                .filter(Event.id == job.event_id)
                .first()
            )

            should_notify = (
                event is not None and event.status != "Failed"
            )

            if should_notify:
                event.status = "Failed"

            db.commit()

            if should_notify:
                try:
                    IngestionService(db)._notify_status(event, "Failed")
                except Exception:
                    logger.exception(
                        "Failed to notify MyClassAdmin for event %s.",
                        event.event_id,
                    )

            logger.error(
                "Job %s exhausted all %s attempts.",
                job_id,
                job.max_attempts,
            )
            return

        delay = RETRY_DELAY_SECONDS * (2 ** (job.attempts - 1))
        job.status = "Retrying"
        job.next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=delay
        )
        db.commit()

        logger.warning(
            "Job %s will retry in %s seconds.",
            job_id,
            delay,
        )


def process_job(job_id: int) -> None:
    """Process one claimed job and persist its outcome."""

    with SessionLocal() as db:
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.id == job_id)
            .first()
        )

        if job is None or job.status != "Processing":
            return

        event = (
            db.query(Event)
            .filter(Event.id == job.event_id)
            .first()
        )

        if event is None:
            job.status = "Failed"
            job.next_retry_at = None
            job.last_error = "Associated event does not exist."
            db.commit()
            logger.error(
                "Job %s failed because its event does not exist.",
                job_id,
            )
            return

        internal_event_id = event.id
        folder_id = event.drive_folder_id

    try:
        # Coordinate ingestion and deletion for the same event.
        with event_lock(internal_event_id):
            with SessionLocal() as db:
                job = (
                    db.query(IngestionJob)
                    .filter(IngestionJob.id == job_id)
                    .with_for_update()
                    .first()
                )

                if job is None or job.status != "Processing":
                    return

                event = (
                    db.query(Event)
                    .filter(Event.id == internal_event_id)
                    .first()
                )

                if event is None:
                    job.status = "Failed"
                    job.next_retry_at = None
                    job.last_error = (
                        "Event was deleted before processing."
                    )
                    db.commit()
                    logger.error(
                        "Job %s failed because its event was deleted.",
                        job_id,
                    )
                    return

                try:
                    result = IngestionService(db).ingest_folder(
                        folder_id=folder_id,
                        event_id=internal_event_id,
                    )

                    db.refresh(event)

                    if (
                        result.get("status") == "Failed"
                        or result.get("failed", 0) > 0
                    ):
                        raise RuntimeError(
                            "Photo ingestion failed: "
                            f"{result.get('failed', 0)} photo(s) failed."
                        )

                    # An empty folder is a completed job, but the event
                    # remains Pending under the existing service logic.
                    job.status = "Completed"
                    job.last_error = None
                    job.next_retry_at = None
                    db.commit()

                    logger.info(
                        "Job %s completed; event status is %s.",
                        job_id,
                        event.status,
                    )

                except Exception as error:
                    db.rollback()
                    logger.exception(
                        "Ingestion failed for job %s.",
                        job_id,
                    )
                    schedule_failure(job_id, error)

    except Exception as error:
        logger.exception(
            "Worker could not process job %s.",
            job_id,
        )
        try:
            schedule_failure(job_id, error)
        except Exception:
            logger.exception(
                "Could not record failure for job %s.",
                job_id,
            )


def run_worker() -> None:
    """Continuously poll PostgreSQL for eligible ingestion jobs."""

    logger.info("Ingestion worker started.")

    while True:
        try:
            job_id = claim_job()

            if job_id is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            process_job(job_id)

        except Exception:
            logger.exception("Worker polling loop error.")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker()

