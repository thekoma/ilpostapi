from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Tuple, Optional, Dict, Any
import logging

from .models import Podcast, Episode

logger = logging.getLogger(__name__)


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

    if not podcast:
        podcast = Podcast(
            ilpost_id=ilpost_id,
            title=podcast_data.get("title", ""),
            description=podcast_data.get("description", ""),
            image_url=podcast_data.get("image", ""),
        )
        db.add(podcast)
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
    podcast.last_checked = datetime.utcnow()
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

    # Se l'ultimo controllo è più vecchio di 1 ora o se è richiesto un aggiornamento
    if needs_update or (datetime.utcnow() - podcast.last_checked) > timedelta(hours=1):
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
            publication_date = datetime.utcnow()

        # Otteniamo la descrizione dal content_html o dalla description
        description = episode_data.get("content_html", "") or episode_data.get(
            "description", ""
        )

        if not episode:
            # Creiamo un nuovo episodio
            episode = Episode(
                ilpost_id=ilpost_id,
                podcast=podcast,
                title=episode_data.get("title", ""),
                description=description,
                description_verified=True,  # La descrizione è verificata perché viene dal batch
                audio_url=episode_data.get("episode_raw_url", ""),
                publication_date=publication_date,
                duration=episode_data.get("milliseconds", 0) // 1000,
            )
            db.add(episode)
        else:
            # Aggiorniamo l'episodio esistente
            episode.title = episode_data.get("title", episode.title)
            episode.description = description
            episode.description_verified = True  # Aggiorniamo lo stato di verifica
            episode.audio_url = episode_data.get("episode_raw_url", episode.audio_url)
            episode.publication_date = publication_date
            episode.duration = episode_data.get("milliseconds", 0) // 1000

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
