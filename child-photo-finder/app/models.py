from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    event_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    event_name = Column(
        String,
        nullable=False
    )

    drive_folder_id = Column(
        String,
        nullable=False
    )

    status = Column(
        String,
        nullable=False,
        default="Pending"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    photos = relationship(
        "Photo",
        back_populates="event"
    )


class Photo(Base):
    __tablename__ = "photos"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    event_id = Column(
        Integer,
        ForeignKey("events.id"),
        nullable=True
    )

    drive_file_id = Column(
        String,
        unique=True,
        nullable=False
    )

    file_name = Column(
        String,
        nullable=False
    )

    mime_type = Column(
        String,
        nullable=True
    )

    drive_url = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    event = relationship(
        "Event",
        back_populates="photos"
    )

    embeddings = relationship(
        "FaceEmbedding",
        back_populates="photo",
        cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    photo_id = Column(
        Integer,
        ForeignKey("photos.id"),
        nullable=False
    )

    face_index = Column(
        Integer,
        nullable=False
    )

    embedding = Column(
        JSON,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    photo = relationship(
        "Photo",
        back_populates="embeddings"
    )