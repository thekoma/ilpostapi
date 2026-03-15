from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, relationship

__all__ = ["Base", "Podcast", "Episode"]


class Base(DeclarativeBase):
    pass


class Podcast(Base):
    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True)
    ilpost_id = Column(String, unique=True, index=True)
    title = Column(String)
    description = Column(Text)
    image_url = Column(String)
    author = Column(String)
    share_url = Column(String)
    slug = Column(String)
    last_checked = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    episodes = relationship(
        "Episode", back_populates="podcast", cascade="all, delete-orphan"
    )


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True)
    ilpost_id = Column(String, unique=True, nullable=False)
    podcast_id = Column(Integer, ForeignKey("podcasts.id"), nullable=False)
    title = Column(String)
    description = Column(Text)
    summary = Column(Text)
    description_verified = Column(Boolean, default=False)
    audio_url = Column(String)
    author = Column(String)
    image_url = Column(String)
    share_url = Column(String)
    slug = Column(String)
    episode_type = Column(String)  # "full", "bonus", "trailer"
    publication_date = Column(DateTime(timezone=True))
    duration = Column(Integer)  # in seconds
    podcast = relationship("Podcast", back_populates="episodes")
