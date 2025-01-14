from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, create_engine, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

__all__ = ["Base", "Podcast", "Episode"]

Base = declarative_base()


class Podcast(Base):
    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True)
    ilpost_id = Column(String, unique=True, index=True)
    title = Column(String)
    description = Column(Text)
    image_url = Column(String)
    last_checked = Column(DateTime, default=datetime.utcnow)
    episodes = relationship("Episode", back_populates="podcast", cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True)
    ilpost_id = Column(String, unique=True, nullable=False)
    podcast_id = Column(Integer, ForeignKey("podcasts.id"), nullable=False)
    title = Column(String)
    description = Column(Text)
    description_verified = Column(Boolean, default=False)
    audio_url = Column(String)
    publication_date = Column(DateTime(timezone=True))
    duration = Column(Integer)  # in seconds
    podcast = relationship("Podcast", back_populates="episodes")
