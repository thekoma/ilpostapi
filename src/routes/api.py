from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends, Path
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from api_client import (
    fetch_podcasts,
    fetch_episodes,
    fetch_all_episodes,
    fetch_episode_details,
    check_updates_from_bff,
    clear_all_caches,
)
from auth import clear_token_cache
from database import get_db, Podcast, Episode
from database.operations import (
    get_or_create_podcast,
    update_podcast_check_time,
    get_podcast_episodes,
    save_episodes,
)
from feeds import rss_generator, rdf_generator
from helpers import clean_html_text, format_duration
from utils.logging import get_logger
from utils.rate_limiter import api_rate_limiter

logger = get_logger(__name__)

router = APIRouter()


def serialize_episode(episode) -> dict:
    """Serializza un episodio del database in un dizionario."""
    return {
        "id": episode.id,
        "ilpost_id": episode.ilpost_id,
        "title": episode.title,
        "description": episode.description,
        "audio_url": episode.audio_url,
        "date": (
            episode.publication_date.isoformat()
            if episode.publication_date
            else None
        ),
        "duration": (
            episode.duration * 1000 if episode.duration else None
        ),
    }


def serialize_episode_full(episode) -> dict:
    """Serializza un episodio con tutti i campi per i template."""
    return {
        "id": episode.id,
        "ilpost_id": episode.ilpost_id,
        "title": clean_html_text(episode.title),
        "description": clean_html_text(episode.description),
        "content_html": episode.description,
        "episode_raw_url": episode.audio_url,
        "audio_url": episode.audio_url,
        "date": (
            episode.publication_date.isoformat()
            if episode.publication_date
            else None
        ),
        "milliseconds": episode.duration * 1000 if episode.duration else None,
        "duration": format_duration(
            episode.duration * 1000 if episode.duration else None
        ),
    }


# --- JSON API Endpoints ---


@router.get("/podcasts", description="Returns a list of podcasts.")
async def get_podcasts(page: int = 1, hits: int = 50):
    try:
        return await fetch_podcasts(page, hits)
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@router.get(
    "/podcasts/search",
    description="Searches for podcasts by title using fuzzy matching.",
)
async def search_podcasts(query: str, request: Request):
    from difflib import get_close_matches

    podcasts = await fetch_podcasts()
    base_url = request.base_url
    titles = [podcast["title"] for podcast in podcasts["data"]]
    matches = get_close_matches(query, titles, n=1, cutoff=0.2)

    if matches:
        matched_title = matches[0]
        matching_podcast = next(
            (p for p in podcasts["data"] if p["title"] == matched_title), None
        )
        if matching_podcast:
            podcast_id = matching_podcast["id"]
            episode = await fetch_episodes(podcast_id=podcast_id)
            return {
                "podcast_id": podcast_id,
                "podcast_title": matching_podcast["title"],
                "episode_title": episode["data"][0]["title"],
                "last_episode_url": episode["data"][0]["episode_raw_url"],
                "podcast_api": f"{base_url}podcast/{podcast_id}/last",
            }

    return JSONResponse(
        content={"message": "No matching podcast found"}, status_code=404
    )


@router.get(
    "/podcast/{podcast_id}",
    description="Returns details of a specific podcast by its ID.",
)
async def get_podcast_detail(
    podcast_id: int = Path(..., description="The ID of the podcast"),
    page: int = 1,
    hits: int = 1,
):
    try:
        return await fetch_episodes(podcast_id, page, hits)
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@router.get(
    "/podcast/{podcast_id}/last",
    description="Returns the last episode of a specific podcast.",
)
@router.get(
    "/podcast/{podcast_id}/lastepisode",
    description="Returns the last episode of a specific podcast.",
)
async def get_last_episode(
    podcast_id: int = Path(..., description="The ID of the podcast"),
):
    try:
        episode = await fetch_episodes(podcast_id=podcast_id)
        return episode["data"][0]
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@router.get("/healthz", description="Liveness probe: verifica che l'app sia viva e il DB raggiungibile.")
async def liveness(db: AsyncSession = Depends(get_db)):
    """Kubernetes liveness probe. Fallisce se il DB non risponde."""
    checks = {}
    healthy = True

    # Check database connectivity
    try:
        result = await db.execute(select(Podcast).limit(1))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        content={"status": "ok" if healthy else "unhealthy", "checks": checks},
        status_code=status_code,
    )


@router.get("/readyz", description="Readiness probe: verifica che l'app possa servire traffico.")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Kubernetes readiness probe. Fallisce se DB o API esterna non sono raggiungibili."""
    checks = {}
    ready = True

    # Check database
    try:
        result = await db.execute(select(Podcast).limit(1))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        ready = False

    # Check auth token (verifica che l'API esterna sia raggiungibile)
    try:
        from auth import get_token
        token = get_token()
        checks["auth"] = "ok" if token else "error: no token"
        if not token:
            ready = False
    except Exception as e:
        checks["auth"] = f"error: {e}"
        ready = False

    status_code = 200 if ready else 503
    return JSONResponse(
        content={"status": "ready" if ready else "not_ready", "checks": checks},
        status_code=status_code,
    )


@router.get("/healthcheck", description="Legacy health check, use /healthz or /readyz instead.")
async def healthcheck():
    return {"status": "ok"}


@router.get("/clear-cache")
async def clear_cache():
    """Pulisce tutte le cache."""
    clear_all_caches()
    clear_token_cache()
    return {"message": "Cache pulita con successo"}


@router.get("/api/podcast/{podcast_id}/episodes")
async def get_podcast_episodes_json(
    podcast_id: int = Path(...),
    per_page: int = 100,
    db: AsyncSession = Depends(get_db),
):
    try:
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)

        if needs_update:
            await api_rate_limiter.wait()
            response = await fetch_episodes(podcast_id, hits=10000)
            podcast_data = response.get("data", [])

            if not podcast_data:
                raise HTTPException(
                    status_code=404,
                    detail="Nessun episodio trovato per questo podcast",
                )

            podcast = await get_or_create_podcast(
                db, str(podcast_id), podcast_data[0]
            )
            if not podcast:
                raise HTTPException(
                    status_code=404,
                    detail="Impossibile creare o recuperare il podcast",
                )

            await save_episodes(db, podcast, podcast_data)
            await update_podcast_check_time(db, podcast)
            episodes, _ = await get_podcast_episodes(db, podcast.id)

        if not episodes:
            return {"data": []}

        episodes.sort(
            key=lambda x: x.publication_date or datetime.min, reverse=True
        )
        return {"data": [serialize_episode(ep) for ep in episodes[:per_page]]}
    except Exception as e:
        logger.error(f"Errore episodi podcast {podcast_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/podcast/{podcast_id}/episode/{episode_id}/description")
async def get_episode_description(
    podcast_id: int = Path(...),
    episode_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = select(Episode).where(Episode.ilpost_id == episode_id)
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()

        if episode and episode.description:
            return {
                "description": clean_html_text(episode.description),
                "content_html": episode.description,
            }

        await api_rate_limiter.wait()
        episode_details = await fetch_episode_details(
            podcast_id, int(episode_id)
        )
        if episode_details:
            episode_data = episode_details.get("data", {})
            description = episode_data.get("content_html", "") or episode_data.get(
                "summary", ""
            )

            # Salva nel DB se abbiamo i dettagli
            if episode and description:
                episode.description = description
                episode.description_verified = True
                await db.commit()

            return {
                "description": clean_html_text(description),
                "content_html": description,
            }

        return {"description": "", "content_html": ""}
    except Exception as e:
        logger.error(f"Errore descrizione episodio {episode_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/podcast/{podcast_id}/episode/{episode_id}/refresh")
async def refresh_episode(
    podcast_id: int = Path(...),
    episode_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = select(Episode).where(Episode.ilpost_id == episode_id)
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()

        if episode:
            episode.description_verified = False
            await db.commit()

        await api_rate_limiter.wait()
        episode_details = await fetch_episode_details(
            podcast_id, int(episode_id)
        )

        if not episode_details:
            raise HTTPException(status_code=404, detail="Episodio non trovato")

        # Aggiorna nel DB
        if episode and "data" in episode_details:
            ep_data = episode_details["data"]
            episode.title = ep_data.get("title", episode.title)
            episode.description = ep_data.get("content_html", "") or ep_data.get(
                "summary", episode.description
            )
            episode.description_verified = True
            episode.audio_url = ep_data.get("episode_raw_url", episode.audio_url)
            await db.commit()

        return {"message": "Episodio aggiornato con successo"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore refresh episodio {episode_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/podcast/{podcast_id}/update", response_class=JSONResponse)
async def update_podcast(
    podcast_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = select(Podcast).where(Podcast.ilpost_id == str(podcast_id))
        result = await db.execute(stmt)
        podcast = result.scalar_one_or_none()

        if podcast:
            podcast.last_checked = None
            await db.commit()

        await api_rate_limiter.wait()
        response = await fetch_all_episodes(podcast_id, batch_size=500)

        if not response or "data" not in response:
            raise HTTPException(
                status_code=404,
                detail="Nessun episodio trovato per questo podcast",
            )

        podcast_data = response["data"]
        podcast = await get_or_create_podcast(
            db, str(podcast_id), podcast_data[0]
        )
        if not podcast:
            raise HTTPException(
                status_code=404,
                detail="Impossibile creare o recuperare il podcast",
            )

        await save_episodes(db, podcast, podcast_data)
        await update_podcast_check_time(db, podcast)
        episodes, _ = await get_podcast_episodes(db, podcast_id)

        episodes.sort(
            key=lambda x: x.publication_date or datetime.min, reverse=True
        )

        return JSONResponse({
            "success": True,
            "episodes": [serialize_episode_full(ep) for ep in episodes],
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento podcast {podcast_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/podcasts/update", response_class=JSONResponse)
async def update_podcasts_directory(db: AsyncSession = Depends(get_db)):
    try:
        from routes.web import update_podcast_directory_cache, _directory_cache

        success = await update_podcast_directory_cache()
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error updating podcast directory",
            )

        cached_data = _directory_cache.get("directory", [])
        return JSONResponse({"success": True, "podcasts": cached_data})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore aggiornamento directory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Feed Endpoints ---


@router.get("/podcast/{podcast_id}/rss")
async def get_podcast_rss(
    podcast_id: int = Path(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        podcasts = await fetch_podcasts()
        podcast_info = next(
            (p for p in podcasts["data"] if p["id"] == podcast_id), None
        )

        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")

        episodes, needs_update = await get_podcast_episodes(db, podcast_id)

        if needs_update or not episodes:
            await api_rate_limiter.wait()
            api_episodes = await fetch_all_episodes(podcast_id)

            db_podcast = await get_or_create_podcast(
                db, str(podcast_id), api_episodes["data"][0]
            )
            if not db_podcast:
                raise HTTPException(
                    status_code=404,
                    detail="Impossibile creare o recuperare il podcast",
                )

            await save_episodes(db, db_podcast, api_episodes["data"])
            await update_podcast_check_time(db, db_podcast)
            episodes, _ = await get_podcast_episodes(db, podcast_id)

        # Aggiorna descrizioni non verificate
        episodes_to_update = [
            ep for ep in episodes if not ep.description_verified
        ]
        if episodes_to_update:
            total = len(episodes_to_update)
            logger.info(
                f"Aggiornamento {total} descrizioni per '{podcast_info['title']}'"
            )
            for idx, episode in enumerate(episodes_to_update, 1):
                try:
                    await api_rate_limiter.wait()
                    details = await fetch_episode_details(
                        podcast_id, int(episode.ilpost_id)
                    )
                    if details and "data" in details:
                        ep_data = details["data"]
                        episode.description = ep_data.get(
                            "content_html", ""
                        ) or ep_data.get("description", "")
                        episode.description_verified = True
                        await db.commit()
                except Exception as e:
                    logger.error(
                        f"Errore descrizione episodio {idx}/{total}: {e}"
                    )
                    continue

        episodes_data = {
            "data": [
                {
                    "id": ep.id,
                    "title": ep.title,
                    "description": ep.description,
                    "content_html": ep.description,
                    "summary": getattr(ep, "summary", "") or "",
                    "episode_raw_url": ep.audio_url,
                    "author": getattr(ep, "author", "") or "",
                    "image": getattr(ep, "image_url", "") or "",
                    "share_url": getattr(ep, "share_url", "") or "",
                    "slug": getattr(ep, "slug", "") or "",
                    "episode_type": getattr(ep, "episode_type", "full") or "full",
                    "date": (
                        ep.publication_date.isoformat()
                        if ep.publication_date
                        else None
                    ),
                    "milliseconds": (
                        ep.duration * 1000 if ep.duration else None
                    ),
                }
                for ep in episodes
            ]
        }

        podcast_data = {
            "id": podcast_id,
            "title": podcast_info["title"],
            "description": podcast_info["description"],
            "author": podcast_info["author"],
            "image": podcast_info["image"],
            "share_url": podcast_info.get("share_url", ""),
            "slug": podcast_info.get("slug", ""),
        }

        request_base_url = str(request.base_url).rstrip("/")
        rss_feed = rss_generator.generate_feed(
            podcast_data, episodes_data, request_base_url
        )

        return Response(content=rss_feed, media_type="application/rss+xml")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore generazione RSS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/podcast/{podcast_id}/rdf")
async def get_podcast_rdf(
    podcast_id: int = Path(...), request: Request = None
):
    try:
        podcasts = await fetch_podcasts()
        podcast_info = next(
            (p for p in podcasts["data"] if p["id"] == podcast_id), None
        )

        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")

        episodes = await fetch_all_episodes(podcast_id)

        podcast_data = {
            "id": podcast_id,
            "title": podcast_info["title"],
            "description": podcast_info["description"],
            "author": podcast_info["author"],
            "image": podcast_info["image"],
        }

        request_base_url = str(request.base_url).rstrip("/")
        rdf_feed = rdf_generator.generate_feed(
            podcast_data, episodes, request_base_url
        )

        return Response(content=rdf_feed, media_type="application/rdf+xml")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
