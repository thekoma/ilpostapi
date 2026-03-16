from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Favorite


async def get_user_favorites(db: AsyncSession, user_id: int) -> list[int]:
    """Restituisce la lista dei podcast_id preferiti dell'utente."""
    result = await db.execute(
        select(Favorite.podcast_id).where(Favorite.user_id == user_id)
    )
    return list(result.scalars().all())


async def is_favorite(db: AsyncSession, user_id: int, podcast_id: int) -> bool:
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.podcast_id == podcast_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def add_favorite(db: AsyncSession, user_id: int, podcast_id: int) -> bool:
    """Aggiunge un podcast ai preferiti. Restituisce True se aggiunto, False se gia' presente."""
    existing = await is_favorite(db, user_id, podcast_id)
    if existing:
        return False
    db.add(Favorite(user_id=user_id, podcast_id=podcast_id))
    await db.commit()
    return True


async def remove_favorite(db: AsyncSession, user_id: int, podcast_id: int) -> bool:
    """Rimuove un podcast dai preferiti. Restituisce True se rimosso, False se non presente."""
    result = await db.execute(
        delete(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.podcast_id == podcast_id,
        )
    )
    await db.commit()
    return result.rowcount > 0
