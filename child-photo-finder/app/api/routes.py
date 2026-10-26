from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    Header
)
from app.services.event_lock import event_lock
from app.services.ingestion_service import IngestionService
from fastapi.responses import StreamingResponse
from pydantic import BaseModel , Field
from sqlalchemy.orm import Session
from io import BytesIO
from app.models import Event, Photo, FaceEmbedding, IngestionJob
from app.drive.drive_service import (
    download_file,
    download_thumbnail
)

from app.database import get_db
from app.models import Event, Photo
from app.services.matching_service import MatchingService
from app.config import API_KEY


router = APIRouter(
    prefix="/api",
    tags=["Child Photo Finder"]
)


# ============================================================
# API KEY SECURITY
# ============================================================

def verify_api_key(
    x_api_key: str = Header(...)
):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key."
        )

    return True


# ============================================================
# EVENT CREATE REQUEST MODEL
# ============================================================


class EventCreate(BaseModel):
    event_id: int = Field(gt = 0)
    event_name: str
    drive_link: str



# ============================================================
# EXTRACT GOOGLE DRIVE FOLDER ID
# ============================================================

def extract_drive_folder_id(drive_link: str) -> str:
    """
    Extract Google Drive folder ID from a Drive folder URL.

    Example:
    https://drive.google.com/drive/folders/ABC123
    -> ABC123
    """

    drive_link = drive_link.strip()

    if not drive_link:
        raise HTTPException(
            status_code=400,
            detail="Google Drive link cannot be empty."
        )

    # Standard Google Drive folder URL
    if "/folders/" in drive_link:
        folder_id = drive_link.split("/folders/")[1]

        # Remove query parameters if present
        folder_id = folder_id.split("?")[0]
        folder_id = folder_id.split("/")[0]

        if folder_id:
            return folder_id

    # If a folder ID itself is provided
    if "drive.google.com" not in drive_link:
        return drive_link

    raise HTTPException(
        status_code=400,
        detail="Invalid Google Drive folder link."
    )



# ============================================================
# CREATE EVENT
# ============================================================



@router.post("/events", status_code=202)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Create an event and queue photo ingestion."""

    event_name = event_data.event_name.strip()

    if not event_name:
        raise HTTPException(
            status_code=400,
            detail="Event name cannot be empty.",
        )

    try:
        drive_folder_id = extract_drive_folder_id(event_data.drive_link)
    except (ValueError, TypeError, HTTPException) as error:
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Google Drive link: {error}",
        )

    external_event_id = str(event_data.event_id)

    existing_event = (
        db.query(Event)
        .filter(Event.event_id == external_event_id)
        .first()
    )

    if existing_event:
        if (
            existing_event.event_name == event_name
            and existing_event.drive_folder_id == drive_folder_id
        ):
            existing_job = (
                db.query(IngestionJob)
                .filter(IngestionJob.event_id == existing_event.id)
                .order_by(IngestionJob.id.desc())
                .first()
            )

            return {
                "message": "Event already exists.",
                "event": {
                    "event_id": existing_event.event_id,
                    "event_name": existing_event.event_name,
                    "status": existing_event.status,
                },
                "job": (
                    {
                        "job_id": existing_job.id,
                        "status": existing_job.status,
                    }
                    if existing_job else None
                ),
            }

        raise HTTPException(
            status_code=409,
            detail="This event_id already exists with different details.",
        )

    existing_drive_event = (
        db.query(Event)
        .filter(Event.drive_folder_id == drive_folder_id)
        .first()
    )

    if existing_drive_event:
        raise HTTPException(
            status_code=409,
            detail="This Google Drive folder is already associated with an event.",
        )

    try:
        event = Event(
            event_id=external_event_id,
            event_name=event_name,
            drive_folder_id=drive_folder_id,
            status="Pending",
        )
        db.add(event)
        db.flush()

        job = IngestionJob(
            event_id=event.id,
            status="Pending",
            attempts=0,
            max_attempts=3,
        )
        db.add(job)

        # Persist both records together before returning 202.
        db.commit()
        db.refresh(event)
        db.refresh(job)

        return {
            "message": "Event created and ingestion job queued.",
            "event": {
                "event_id": event.event_id,
                "event_name": event.event_name,
                "status": event.status,
            },
            "job": {
                "job_id": job.id,
                "status": job.status,
            },
        }

    except Exception as error:
        db.rollback()
        print(f"Event/job creation error: {error}")
        raise HTTPException(
            status_code=500,
            detail="Could not create the event and ingestion job.",
        )



# ============================================================
# DELETE EVENT
# ============================================================




@router.delete("/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Delete an event and its database records, not Drive files."""

    event = (
        db.query(Event)
        .filter(Event.event_id == str(event_id))
        .first()
    )

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")

    internal_event_id = event.id

    try:
        # Serialize deletion with ingestion for this event.
        with event_lock(internal_event_id):
            event = (
                db.query(Event)
                .filter(Event.id == internal_event_id)
                .with_for_update()
                .first()
            )

            if event is None:
                raise HTTPException(
                    status_code=404,
                    detail="Event not found.",
                )

            # Remove associated jobs first to satisfy foreign keys.
            deleted_job_count = (
                db.query(IngestionJob)
                .filter(IngestionJob.event_id == event.id)
                .delete(synchronize_session=False)
            )

            photos = (
                db.query(Photo)
                .filter(Photo.event_id == event.id)
                .all()
            )
            deleted_photo_count = len(photos)

            for photo in photos:
                db.query(FaceEmbedding).filter(
                    FaceEmbedding.photo_id == photo.id
                ).delete(synchronize_session=False)
                db.delete(photo)

            db.delete(event)
            db.commit()

            return {
                "message": "Event and associated database records deleted successfully.",
                "event_id": event_id,
                "deleted_jobs": deleted_job_count,
                "deleted_photos": deleted_photo_count,
                "drive_files_deleted": False,
            }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print(f"Event deletion error: {error}")
        raise HTTPException(
            status_code=500,
            detail="Could not delete event.",
        )




# ============================================================
# GET ALL PHOTOS FOR AN EVENT
# ============================================================

@router.get("/events/{event_id}/photos")
def get_event_photos(
    event_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Return all photos belonging to a particular event.

    This will be used for the portal's 'View All' option.
    """

    event = (
        db.query(Event)
        .filter(Event.event_id == event_id)
        .first()
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event '{event_id}' not found."
        )

    photos = (
        db.query(Photo)
        .filter(Photo.event_id == event.id)
        .all()
    )

    return {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "photo_count": len(photos),
        "photos": [
            {
                "photo_id": photo.id,
                "file_name": photo.file_name,

                # Full-quality image
                "image_url": (
                    f"/api/photos/{photo.id}/image"
                ),

                # Thumbnail image
                "thumbnail_url": (
                    f"/api/photos/{photo.id}/thumbnail"
                )
            }
            for photo in photos
        ]
    }


# ============================================================
# SEARCH CHILD PHOTOS
# ============================================================

@router.post("/events/{event_id}/search")
async def search_child(
    event_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Search for a child inside a specific event.
    """

    # --------------------------------------------------------
    # Check event
    # --------------------------------------------------------

    event = (
        db.query(Event)
        .filter(Event.event_id == event_id)
        .first()
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event '{event_id}' not found."
        )

    # --------------------------------------------------------
    # Validate uploaded file
    # --------------------------------------------------------

    if not file.content_type:
        raise HTTPException(
            status_code=400,
            detail="Could not determine file type."
        )

    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Please upload an image."
        )

    # --------------------------------------------------------
    # Read image
    # --------------------------------------------------------

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty."
        )

    # --------------------------------------------------------
    # Run face matching
    # --------------------------------------------------------

    try:
        matcher = MatchingService(db)

        matches = matcher.find_matches(
            image_bytes=image_bytes,
            event_id=event_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:
        print(f"Search error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Face matching failed."
        )

    # --------------------------------------------------------
    # Return response
    # --------------------------------------------------------

    return {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "match_count": len(matches),
        "matches": [
            {
                "photo_id": match["photo_id"],
                "file_name": match["file_name"],
                "similarity": match["similarity"],

                # Full-quality image
                "image_url": (
                    f"/api/photos/{match['photo_id']}/image"
                ),

                # Thumbnail image
                "thumbnail_url": (
                    f"/api/photos/{match['photo_id']}/thumbnail"
                )
            }
            for match in matches
        ]
    }


# ============================================================
# GET PHOTO IMAGE
# ============================================================

@router.get("/photos/{photo_id}/image")
def get_photo_image(
    photo_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Retrieve an actual photo from Google Drive.
    """

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id)
        .first()
    )

    if photo is None:
        raise HTTPException(
            status_code=404,
            detail="Photo not found."
        )

    try:
        file_data = download_file(
            photo.drive_file_id
        )

        image_bytes = file_data.read()

        return StreamingResponse(
            BytesIO(image_bytes),
            media_type=photo.mime_type or "image/jpeg"
        )

    except Exception as e:
        print(f"Image download error for photo_id={photo_id}: {e!r}", flush=True)

        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve photo."
        )


# ============================================================
# GET PHOTO THUMBNAIL
# ============================================================

@router.get("/photos/{photo_id}/thumbnail")
def get_photo_thumbnail(
    photo_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Retrieve a thumbnail version of a photo from Google Drive.

    The original full-quality image remains available through:
    /api/photos/{photo_id}/image
    """

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id)
        .first()
    )

    if photo is None:
        raise HTTPException(
            status_code=404,
            detail="Photo not found."
        )

    try:
        thumbnail_data = download_thumbnail(
            photo.drive_file_id
        )

        if thumbnail_data is None:
            raise HTTPException(
                status_code=404,
                detail="Thumbnail not available."
            )

        thumbnail_bytes = thumbnail_data.read()

        return StreamingResponse(
            BytesIO(thumbnail_bytes),
            media_type="image/jpeg"
        )

    except HTTPException:
        raise

    except Exception as e:
        print(
            f"Thumbnail download error: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve photo thumbnail."
        )