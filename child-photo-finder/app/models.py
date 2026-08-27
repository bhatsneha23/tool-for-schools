from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    JSON
)
from sqlalchemy.sql import func

from app.database import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(
        Integer,
        primary_key=True,
        index=True
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