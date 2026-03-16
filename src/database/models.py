import secrets
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship

__all__ = ["Base", "Podcast", "Episode", "User", "Favorite"]


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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # nullable for OIDC-only users
    role = Column(String, nullable=False, default="user")  # "admin" or "user"
    rss_token = Column(String, unique=True, nullable=False, index=True,
                       default=lambda: secrets.token_urlsafe(32))
    oauth_sub = Column(String, unique=True, nullable=True, index=True)  # OIDC subject
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def is_admin(self):
        return self.role == "admin"


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "podcast_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    podcast_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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
