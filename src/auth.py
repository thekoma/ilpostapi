import httpx
from cachetools import TTLCache, cached
from fastapi import HTTPException

from config import EMAIL, PASSWORD, API_AUTH_LOGIN, TOKEN_CACHE_TTL, API_KEY
from utils.logging import get_logger

logger = get_logger(__name__)

token_cache = TTLCache(maxsize=1, ttl=TOKEN_CACHE_TTL)


@cached(cache=token_cache)
def _fetch_token() -> str:
    """Ottiene un token di autenticazione dall'API (cached con TTL)."""
    logger.info("Richiesta nuovo token di autenticazione")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                API_AUTH_LOGIN, data={"username": EMAIL, "password": PASSWORD}
            )
            response.raise_for_status()
            token_data = response.json()
            return token_data["data"]["data"]["token"]
    except httpx.HTTPError as e:
        logger.error(f"Errore durante l'autenticazione: {e}")
        raise HTTPException(status_code=500, detail="Errore di autenticazione")


def get_token() -> str:
    """Restituisce il token, riprovando una volta se fallisce."""
    try:
        return _fetch_token()
    except Exception:
        token_cache.clear()
        return _fetch_token()


def get_auth_headers() -> dict:
    """Restituisce gli header di autenticazione per le chiamate API."""
    return {"Apikey": API_KEY, "Token": get_token()}


def clear_token_cache():
    token_cache.clear()
