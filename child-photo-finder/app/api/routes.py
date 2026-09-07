from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Header
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.drive.drive_service import download_file
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

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key."
        )

    return True


# ============================================================
# GET ALL EVENTS
# ============================================================

@router.get("/events")
def get_events(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Return all events available in the system.
    """

    events = (
        db.query(Event)
        .order_by(Event.id)
        .all()
    )

    return {
        "events": [
            {
                "event_id": event.event_id,
                "event_name": event.event_name
            }
            for event in events
        ]
    }


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
                "image_url": f"/api/photos/{photo.id}/image"
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
                "image_url": f"/api/photos/{match['photo_id']}/image"
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
        file_data = download_file(photo.drive_file_id)
        image_bytes = file_data.read()

        return StreamingResponse(
            BytesIO(image_bytes),
            media_type=photo.mime_type or "image/jpeg"
        )

    except Exception as e:
        print(f"Image download error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve photo."
        )