import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx
from cachetools import TTLCache
from fastapi import HTTPException

from auth import get_auth_headers
from config import PODCAST_API_BASE_URL, BFF_HP_URL, CACHE_TTL
from utils.logging import get_logger
from utils.rate_limiter import api_rate_limiter

logger = get_logger(__name__)

# Cache in-memory con TTL automatico
_podcasts_cache = TTLCache(maxsize=100, ttl=CACHE_TTL)
_episodes_list_cache = TTLCache(maxsize=100, ttl=CACHE_TTL)
_episode_info_cache = TTLCache(maxsize=500, ttl=CACHE_TTL)

# Client HTTP async condiviso (creato al primo uso)
_async_client: Optional[httpx.AsyncClient] = None

MAX_RETRIES = 3


async def get_async_client() -> httpx.AsyncClient:
    """Restituisce un client HTTP async condiviso."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=30.0)
    return _async_client


async def close_client():
    """Chiude il client HTTP async."""
    global _async_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None


async def make_api_request(
    url: str, headers: Optional[Dict] = None, retries: int = 0
) -> Dict:
    """Effettua una richiesta API con rate limiting e retry limitato."""
    await api_rate_limiter.wait()
    logger.info(f"Chiamata API: {url}")
    try:
        client = await get_async_client()
        response = await client.get(url, headers=headers)

        if response.status_code == 429:
            if retries >= MAX_RETRIES:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit raggiunto dopo troppi tentativi",
                )
            logger.warning(
                f"Rate limit raggiunto, retry {retries + 1}/{MAX_RETRIES}"
            )
            await asyncio.sleep(10)
            return await make_api_request(url, headers, retries + 1)

        response.raise_for_status()
        data = response.json()

        if "data" not in data:
            logger.error(f"Risposta API non valida: {data}")
            raise HTTPException(status_code=500, detail="Risposta API non valida")

        return data
    except httpx.HTTPError as e:
        logger.error(f"Errore nella richiesta API: {e} - URL: {url}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta API")


async def fetch_podcasts(page: int = 1, hits: int = 10000) -> Dict:
    """Recupera la lista dei podcast."""
    cache_key = f"podcasts_{page}_{hits}"
    if cache_key in _podcasts_cache:
        logger.info("Cache HIT - Lista podcast")
        return _podcasts_cache[cache_key]

    headers = get_auth_headers()
    data = await make_api_request(
        f"{PODCAST_API_BASE_URL}/?pg={page}&hits={hits}", headers=headers
    )
    _podcasts_cache[cache_key] = data
    return data


async def fetch_episodes(podcast_id: int, page: int = 1, hits: int = 1) -> Dict:
    """Recupera gli episodi di un podcast."""
    headers = get_auth_headers()
    return await make_api_request(
        f"{PODCAST_API_BASE_URL}/{podcast_id}/?pg={page}&hits={hits}",
        headers=headers,
    )


async def fetch_episodes_batch(episode_ids: list[int]) -> Dict:
    """Recupera un gruppo di episodi in una singola chiamata."""
    if not episode_ids:
        return {"data": []}

    headers = get_auth_headers()
    ids_str = ",".join(map(str, episode_ids))
    return await make_api_request(
        f"{PODCAST_API_BASE_URL}/episodes?ids={ids_str}", headers=headers
    )


async def fetch_all_episodes(podcast_id: int, batch_size: int = 500) -> Dict:
    """Recupera tutti gli episodi di un podcast con paginazione."""
    cache_key = f"all_episodes_{podcast_id}"
    if cache_key in _episodes_list_cache:
        logger.info(f"Cache HIT - Lista episodi podcast {podcast_id}")
        return _episodes_list_cache[cache_key]

    logger.info(f"Inizio recupero episodi per il podcast {podcast_id}")

    initial_data = await fetch_episodes(podcast_id, page=1, hits=1)
    total_episodes = initial_data["head"]["data"]["total"]
    logger.info(f"Totale episodi: {total_episodes}")

    if total_episodes <= batch_size:
        response = await fetch_episodes(podcast_id, page=1, hits=total_episodes)
        if response and "data" in response:
            result = {"data": response["data"]}
            _episodes_list_cache[cache_key] = result
            return result
        return {"data": []}

    all_episodes = []
    total_pages = (total_episodes + batch_size - 1) // batch_size

    for page in range(1, total_pages + 1):
        try:
            logger.info(f"Recupero pagina {page}/{total_pages}")
            response = await fetch_episodes(podcast_id, page, batch_size)

            if not response or "data" not in response:
                continue

            episodes = response["data"]
            if not episodes:
                break

            all_episodes.extend(episodes)
            logger.info(f"Recuperati {len(all_episodes)}/{total_episodes} episodi")
        except Exception as e:
            logger.error(f"Errore pagina {page}: {e}")
            continue

    if len(all_episodes) < total_episodes * 0.9:
        logger.error(
            f"Recuperati solo {len(all_episodes)}/{total_episodes} episodi"
        )
        return {"data": []}

    result = {"data": all_episodes}
    _episodes_list_cache[cache_key] = result
    return result


async def fetch_episode_details(podcast_id: int, episode_id: int) -> Optional[Dict]:
    """Recupera i dettagli di un singolo episodio dall'API."""
    url = f"{PODCAST_API_BASE_URL}/{podcast_id}/{episode_id}/"
    headers = get_auth_headers()
    await api_rate_limiter.wait()

    try:
        data = await make_api_request(url, headers)
        return data
    except HTTPException as e:
        if e.status_code == 404:
            logger.warning(f"Episodio {episode_id} non trovato")
            return None
        raise
    except Exception as e:
        logger.error(f"Errore recupero dettagli episodio {episode_id}: {e}")
        return None


async def check_updates_from_bff() -> Dict:
    """Controlla aggiornamenti usando l'endpoint BFF Homepage."""
    headers = get_auth_headers()

    try:
        client = await get_async_client()
        response = await client.get(BFF_HP_URL, headers=headers)
        response.raise_for_status()
        data = response.json()

        latest_episodes = {}

        if "data" in data:
            for component in data["data"]:
                if "data" not in component:
                    continue
                for episode in component["data"]:
                    if "parent" not in episode or "id" not in episode["parent"]:
                        continue
                    podcast_id = episode["parent"]["id"]
                    episode_date = episode.get("date")

                    if podcast_id not in latest_episodes or (
                        episode_date
                        and (
                            not latest_episodes[podcast_id]
                            or episode_date > latest_episodes[podcast_id]["date"]
                        )
                    ):
                        latest_episodes[podcast_id] = {
                            "date": episode_date,
                            "title": episode["parent"].get("title"),
                            "last_episode_title": episode.get("title"),
                            "last_episode_duration": episode.get("milliseconds"),
                        }

        return latest_episodes
    except Exception as e:
        logger.error(f"Errore nel controllo aggiornamenti BFF: {e}")
        return {}


def get_episode_info_cache():
    """Restituisce la cache delle info episodi (per uso esterno)."""
    return _episode_info_cache


def clear_all_caches():
    """Pulisce tutte le cache."""
    _podcasts_cache.clear()
    _episodes_list_cache.clear()
    _episode_info_cache.clear()
