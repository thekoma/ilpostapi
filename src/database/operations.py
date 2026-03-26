from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Tuple, Optional, Dict, Any

from utils.logging import get_logger
from .models import Podcast, Episode

logger = get_logger(__name__)


async def get_or_create_podcast(
    db: AsyncSession, ilpost_id: str, podcast_data: Dict[str, Any]
) -> Podcast:
    """
    Recupera un podcast dal database o lo crea se non esiste.

    Args:
        db: Sessione del database
        ilpost_id: ID del podcast su Il Post
        podcast_data: Dati del podcast dall'API

    Returns:
        Podcast: L'istanza del podcast
    """
    stmt = select(Podcast).where(Podcast.ilpost_id == ilpost_id)
    result = await db.execute(stmt)
    podcast = result.scalar_one_or_none()

    # Dati del podcast dal payload (possono venire dal podcast diretto o dal parent di un episodio)
    parent = podcast_data.get("parent", podcast_data)

    if not podcast:
        podcast = Podcast(
            ilpost_id=ilpost_id,
            title=parent.get("title", ""),
            description=parent.get("description", ""),
            image_url=parent.get("image", ""),
            author=parent.get("author", ""),
            share_url=parent.get("share_url", ""),
            slug=parent.get("slug", ""),
        )
        db.add(podcast)
        await db.commit()
        await db.refresh(podcast)
    else:
        podcast.title = parent.get("title", podcast.title)
        podcast.description = parent.get("description", podcast.description)
        podcast.image_url = parent.get("image", podcast.image_url)
        podcast.author = parent.get("author", podcast.author)
        podcast.share_url = parent.get("share_url", podcast.share_url)
        podcast.slug = parent.get("slug", podcast.slug)
        await db.commit()
        await db.refresh(podcast)

    return podcast


async def update_podcast_check_time(db: AsyncSession, podcast: Podcast) -> None:
    """
    Aggiorna il timestamp dell'ultimo controllo del podcast.

    Args:
        db: Sessione del database
        podcast: Istanza del podcast da aggiornare
    """
    podcast.last_checked = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(podcast)


async def get_podcast_episodes(
    db: AsyncSession, podcast_id: int, needs_update: bool = False
) -> Tuple[List[Episode], bool]:
    """
    Recupera gli episodi di un podcast dal database.

    Args:
        db: Sessione del database
        podcast_id: ID del podcast (può essere sia l'ID interno che l'ID de Il Post)
        needs_update: Se True, forza un aggiornamento

    Returns:
        Tuple[List[Episode], bool]: Lista degli episodi e flag che indica se serve un aggiornamento
    """

    # Prima proviamo a cercare per ID interno
    stmt = (
        select(Podcast)
        .where(Podcast.id == podcast_id)
        .options(selectinload(Podcast.episodes))
    )
    result = await db.execute(stmt)
    podcast = result.scalar_one_or_none()

    if not podcast:
        # Se non lo troviamo, proviamo con l'ID de Il Post
        stmt = (
            select(Podcast)
            .where(Podcast.ilpost_id == str(podcast_id))
            .options(selectinload(Podcast.episodes))
        )
        result = await db.execute(stmt)
        podcast = result.scalar_one_or_none()

    if not podcast:
        return [], True

    # Check if last update is older than 15 minutes or if an update is explicitly requested
    last_checked = podcast.last_checked
    if last_checked and last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    if needs_update or not last_checked or (datetime.now(timezone.utc) - last_checked) > timedelta(minutes=15):
        return podcast.episodes, True

    logger.info(
        f"🎯 Cache HIT - Episodi del podcast {podcast_id} trovati nel database e aggiornati"
    )
    return podcast.episodes, False


async def save_episodes(
    db: AsyncSession, podcast: Podcast, episodes_data: List[Dict[str, Any]]
) -> None:
    """
    Salva o aggiorna gli episodi di un podcast nel database.

    Args:
        db: Sessione del database
        podcast: Istanza del podcast
        episodes_data: Lista dei dati degli episodi dall'API
    """
    for episode_data in episodes_data:
        ilpost_id = str(episode_data["id"])
        stmt = select(Episode).where(Episode.ilpost_id == ilpost_id)
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()

        # Convertiamo la data di pubblicazione
        try:
            publication_date = datetime.fromisoformat(episode_data["date"])
        except (ValueError, KeyError):
            publication_date = datetime.now(timezone.utc)

        # Otteniamo la descrizione dal content_html o dalla description
        description = episode_data.get("content_html", "") or episode_data.get(
            "description", ""
        )

        # Determina il tipo di episodio
        episode_type = "full"
        if episode_data.get("special"):
            episode_type = "bonus"

        # Campi comuni
        common_fields = dict(
            title=episode_data.get("title", ""),
            description=description,
            summary=episode_data.get("summary", ""),
            description_verified=True,
            audio_url=episode_data.get("episode_raw_url", ""),
            author=episode_data.get("author", ""),
            image_url=episode_data.get("image", ""),
            share_url=episode_data.get("share_url", ""),
            slug=episode_data.get("slug", ""),
            episode_type=episode_type,
            publication_date=publication_date,
            duration=episode_data.get("milliseconds", 0) // 1000,
        )

        if not episode:
            episode = Episode(ilpost_id=ilpost_id, podcast=podcast, **common_fields)
            db.add(episode)
        else:
            for key, value in common_fields.items():
                setattr(episode, key, value)

    await db.commit()


async def get_podcast_by_ilpost_id(
    db: AsyncSession, ilpost_id: str
) -> Optional[Podcast]:
    """
    Recupera un podcast dal database usando l'ID de Il Post.

    Args:
        db: Sessione del database
        ilpost_id: ID del podcast su Il Post

    Returns:
        Optional[Podcast]: Il podcast se trovato, None altrimenti
    """
    stmt = select(Podcast).where(Podcast.ilpost_id == ilpost_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_episode_by_ilpost_id(
    db: AsyncSession, ilpost_id: str
) -> Optional[Episode]:
    """
    Recupera un episodio dal database usando l'ID de Il Post.

    Args:
        db: Sessione del database
        ilpost_id: ID dell'episodio su Il Post

    Returns:
        Optional[Episode]: L'episodio se trovato, None altrimenti
    """
    stmt = select(Episode).where(Episode.ilpost_id == ilpost_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
