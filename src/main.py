import os
import time
from functools import lru_cache

import requests
from difflib import get_close_matches
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse

from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
load_dotenv(find_dotenv())

# --- Configuration ---
# Get EMAIL from environment
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# Raise an error if EMAIL is not found
if not EMAIL or not PASSWORD:
    raise ValueError("EMAIL and PASSWORD are required but not set properly")

# Base URLs for the external APIs
PODCAST_API_BASE_URL = "https://api-prod.ilpost.it/podcast/v1/podcast"
API_AUTH_LOGIN = "https://api-prod.ilpost.it/user/v1/auth/login"

# Token caching configuration
TOKEN_CACHE_TTL = 2 * 60 * 60  # 2 hours in seconds

# --- FastAPI App ---
app = FastAPI()

# --- Helper Functions ---

@lru_cache(maxsize=1)  # Cache only the latest token
def get_cached_token():
    """Retrieves and caches the token with a TTL."""
    token, expires_at = None, 0  # Initialize token and expiration time

    try:
        response = requests.post(
            API_AUTH_LOGIN,
            data={"username": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data['data']['data']['token']
        print(token)  # Consider logging this instead of printing
        expires_in = token_data.get("expires_in", TOKEN_CACHE_TTL)  # Use default TTL if not provided
        expires_at = time.time() + expires_in
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching token: {e}")

    return token, expires_at


async def get_token():
    """Provides the token, refreshing it if expired."""
    token, expires_at = get_cached_token()
    if time.time() > expires_at:
        # Token expired, refresh it
        get_cached_token.cache_clear()  # Clear the cache
        token, expires_at = get_cached_token()  # Fetch a new token
    return token


async def fetch_podcasts(page: int = 1, hits: int = 50):
    """Fetches podcast data from the external API."""
    url = f"{PODCAST_API_BASE_URL}/?pg={page}&hits={hits}"
    token = await get_token()  # Use await to get the token
    headers = {
        "Apikey": "testapikey",
        "Token": token
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching podcasts: {e}")


''' By default get only the last episode '''
async def fetch_episodes(podcast_id: int, page: int = 1, hits: int = 1):
    """Fetches episode data for a specific podcast from the external API."""
    if not isinstance(podcast_id, int):
        raise HTTPException(status_code=400, detail="Invalid podcast_id. Must be an integer.")
    url = f"{PODCAST_API_BASE_URL}/{podcast_id}/?pg={page}&hits={hits}"
    print(url)  # Consider logging this instead of printing
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes: {e}")


# --- API Endpoints ---

@app.get("/podcasts")
async def get_podcasts(page: int = 1, hits: int = 50):
    """Returns a list of podcasts."""
    try:
        podcasts = await fetch_podcasts(page, hits)
        return podcasts
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@app.get("/podcasts/search")
async def search_podcasts(query: str):
    """Searches for podcasts by title using fuzzy matching."""
    podcasts = await fetch_podcasts()
    titles = [podcast["title"] for podcast in podcasts["data"]]
    matches = get_close_matches(query, titles, n=1, cutoff=0.2)  # Adjust cutoff as needed

    if matches:
        matched_title = matches[0]
        matching_podcast = next(
            (p for p in podcasts["data"] if p["title"] == matched_title), None
        )
        if matching_podcast:
            episode = await fetch_episodes(podcast_id=matching_podcast["id"])
            return {
                "podcast_id": matching_podcast["id"],
                "podcast_title": matching_podcast["title"],
                "episode_title": episode["data"][0]["title"],
                "episode_url": episode["data"][0]["episode_raw_url"]
            }

    return JSONResponse(content={"message": "No matching podcast found"}, status_code=404)

@app.get("/healthcheck")
async def healthcheck():
    """Simple health check endpoint."""
    return {"status": "ok"}
