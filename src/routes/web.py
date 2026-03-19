from datetime import datetime

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request, Depends, Path
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from api_client import (
    fetch_podcasts,
    fetch_episodes,
    check_updates_from_bff,
    get_episode_info_cache,
)
from auth_dependencies import require_auth
from config import CACHE_TTL, BASE_URL, BUILD_COMMIT, BUILD_VERSION
from database import get_db
from database.operations import get_podcast_episodes
from database.favorite_operations import get_user_favorites
from helpers import (
    clean_html_text,
    format_duration,
    format_date_main,
    format_date_year,
    format_date_time,
    escapejs,
)
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Template engine
templates = Jinja2Templates(directory="templates")

# Registra globals e filtri una sola volta
templates.env.globals.update({
    "now": datetime.now,
    "min": min,
    "max": max,
    "clean_text": clean_html_text,
    "format_duration": format_duration,
    "formatDateMain": format_date_main,
    "formatDateYear": format_date_year,
    "formatDateTime": format_date_time,
})

templates.env.filters.update({
    "formatDateMain": format_date_main,
    "formatDateYear": format_date_year,
    "formatDateTime": format_date_time,
    "escapejs": escapejs,
    "clean_text": clean_html_text,
    "format_duration": format_duration,
})

# Cache per la directory dei podcast
_directory_cache = TTLCache(maxsize=1, ttl=CACHE_TTL)


async def update_podcast_directory_cache() -> bool:
    """Aggiorna la cache della directory dei podcast."""
    try:
        latest_updates = await check_updates_from_bff()
        if not latest_updates:
            logger.warning("Nessun aggiornamento trovato dal BFF")
            return False

        cached = _directory_cache.get("directory")

        if cached is not None:
            podcast_list = cached
            podcast_ids_in_cache = {p["id"] for p in podcast_list}

            for podcast in podcast_list:
                podcast_id = podcast["id"]
                if podcast_id in latest_updates:
                    latest = latest_updates[podcast_id]
                    current_date = podcast.get("last_episode_date")

                    if not current_date or latest["date"] > current_date:
                        podcast.update({
                            "last_episode_date": latest["date"],
                            "last_episode_title": clean_html_text(
                                latest["last_episode_title"]
                            ),
                            "last_episode_duration": format_duration(
                                latest["last_episode_duration"]
                            ),
                        })

            # Aggiungi podcast non presenti in cache
            all_podcasts = await fetch_podcasts(page=1, hits=100)
            for podcast in all_podcasts["data"]:
                if podcast["id"] not in podcast_ids_in_cache:
                    latest = latest_updates.get(podcast["id"], {})
                    podcast_list.append(_build_podcast_entry(podcast, latest))
        else:
            podcasts = await fetch_podcasts(page=1, hits=100)
            podcast_list = [
                _build_podcast_entry(
                    podcast, latest_updates.get(podcast["id"], {})
                )
                for podcast in podcasts["data"]
            ]

        podcast_list.sort(
            key=lambda x: x["last_episode_date"]
            or "1970-01-01T00:00:00+00:00",
            reverse=True,
        )

        _directory_cache["directory"] = podcast_list
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento directory: {e}")
        return False


def _build_podcast_entry(podcast: dict, latest: dict) -> dict:
    """Costruisce un dizionario podcast per la directory."""
    return {
        "id": podcast["id"],
        "title": clean_html_text(podcast["title"]),
        "image": podcast["image"],
        "description": clean_html_text(podcast["description"]),
        "author": clean_html_text(podcast["author"]),
        "rss_url": f"/podcast/{podcast['id']}/rss",
        "slug": podcast["slug"],
        "last_episode_date": latest.get("date"),
        "last_episode_title": clean_html_text(
            latest.get("last_episode_title", "")
        ),
        "last_episode_duration": format_duration(
            latest.get("last_episode_duration")
        ),
    }


async def get_last_episode_info(podcast_id: int, db: AsyncSession = None):
    """Recupera le informazioni dell'ultimo episodio con caching."""
    cache = get_episode_info_cache()

    if podcast_id in cache:
        return cache[podcast_id]

    if db:
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)
        if episodes and not needs_update:
            episodes.sort(
                key=lambda x: x.publication_date or datetime.min, reverse=True
            )
            if episodes:
                latest = episodes[0]
                info = (
                    (
                        latest.publication_date.isoformat()
                        if latest.publication_date
                        else None
                    ),
                    latest.title,
                    latest.duration * 1000 if latest.duration else None,
                )
                cache[podcast_id] = info
                return info

    last_episode = await fetch_episodes(podcast_id, page=1, hits=1)

    if (
        last_episode
        and last_episode.get("data")
        and len(last_episode["data"]) > 0
    ):
        episode = last_episode["data"][0]
        info = (
            episode.get("date"),
            episode.get("title"),
            episode.get("milliseconds"),
        )
    else:
        info = (None, None, None)

    cache[podcast_id] = info
    return info


# --- Web Endpoints ---


@router.get("/", response_class=HTMLResponse)
@router.get("/podcasts/directory", response_class=HTMLResponse)
async def podcast_directory(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    try:
        needs_update = False
        cached = _directory_cache.get("directory")

        if cached is not None:
            podcast_list = cached
        else:
            needs_update = True
            await update_podcast_directory_cache()
            podcast_list = _directory_cache.get("directory", [])

        favorites = await get_user_favorites(db, user.id)
        base_url = BASE_URL.rstrip("/")
        return templates.TemplateResponse(
            "podcast_directory.html",
            {
                "request": request,
                "user": user,
                "podcasts": podcast_list,
                "favorites": favorites,
                "year": datetime.now().year,
                "needs_update": needs_update,
                "base_url": base_url,
                "build_commit": BUILD_COMMIT,
                "build_version": BUILD_VERSION,
            },
        )
    except Exception as e:
        logger.error(f"Errore directory podcast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/podcast/{podcast_id}/episodes", response_class=HTMLResponse)
async def podcast_episodes(
    podcast_id: int = Path(...),
    request: Request = None,
    page: int = 1,
    per_page: int = 20,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    try:
        podcasts = await fetch_podcasts()
        podcast_info = next(
            (p for p in podcasts["data"] if p["id"] == podcast_id), None
        )

        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")

        podcast = {
            "id": podcast_info["id"],
            "title": clean_html_text(podcast_info["title"]),
            "image": podcast_info["image"],
            "description": clean_html_text(podcast_info["description"]),
            "author": clean_html_text(podcast_info["author"]),
            "rss_url": f"/podcast/{podcast_info['id']}/rss",
            "slug": podcast_info["slug"],
        }

        episodes, needs_update = await get_podcast_episodes(db, podcast_id)
        episodes.sort(
            key=lambda x: x.publication_date or datetime.min, reverse=True
        )

        # Paginazione
        total_items = len(episodes)
        total_pages = (total_items + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1

        max_visible_pages = 5
        if total_pages <= max_visible_pages:
            pages = list(range(1, total_pages + 1))
        else:
            pages = [1]
            start_page = max(2, page - 1)
            end_page = min(total_pages - 1, page + 1)
            if start_page > 2:
                pages.append("...")
            pages.extend(range(start_page, end_page + 1))
            if end_page < total_pages - 1:
                pages.append("...")
            pages.append(total_pages)

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_episodes = episodes[start_idx:end_idx]

        pagination = {
            "current_page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_episodes": total_items,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "pages": pages,
            "needs_update": needs_update,
        }

        from routes.api import serialize_episode_full

        serialized_episodes = [
            serialize_episode_full(ep) for ep in paginated_episodes
        ]

        base_url = BASE_URL.rstrip("/")
        return templates.TemplateResponse(
            "podcast_episodes.html",
            {
                "request": request,
                "user": user,
                "podcast": podcast,
                "episodes": serialized_episodes,
                "pagination": pagination,
                "podcast_id": podcast_id,
                "year": datetime.now().year,
                "base_url": base_url,
                "build_commit": BUILD_COMMIT,
                "build_version": BUILD_VERSION,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Errore episodi podcast {podcast_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))
