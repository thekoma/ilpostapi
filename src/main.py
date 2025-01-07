import os
import time
from functools import lru_cache
from datetime import datetime
import xml.etree.ElementTree as ET
import html  # Aggiungi questo import all'inizio del file
import re  # Aggiungi questo import per la funzione re

import requests
from difflib import get_close_matches
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response
from fastapi import Path
from dotenv import load_dotenv, find_dotenv
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

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
PODCAST_API_BASE_URL = "https://api-prod.ilpost.it./podcast/v1/podcast"
API_AUTH_LOGIN = "https://api-prod.ilpost.it./user/v1/auth/login"

# Token caching configuration
TOKEN_CACHE_TTL = 2 * 60 * 60  # 2 hours in seconds

# --- FastAPI App ---
app = FastAPI()

# Configurazione template e file statici
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# Aggiungiamo le funzioni necessarie ai globals di Jinja2
templates.env.globals.update({
    'now': datetime.now,
    'min': min,  # Aggiungiamo la funzione min
    'max': max   # Aggiungiamo anche max per sicurezza
})

# Dopo la creazione dell'istanza templates
templates.env.globals.update(now=datetime.now)

# Aggiungiamo la funzione helper a livello globale per poterla usare ovunque
def clean_html_text(text: str) -> str:
    if not text:
        return ""
    # Prima decodifichiamo le entità HTML
    text = html.unescape(text)
    # Poi rimuoviamo eventuali tag HTML
    text = re.sub(r'<[^>]+>', '', text)
    # Rimuoviamo spazi multipli
    text = ' '.join(text.split())
    return text.strip()

# Aggiungiamo la funzione ai globals di Jinja2
templates.env.globals.update({
    'now': datetime.now,
    'min': min,
    'max': max,
    'clean_text': clean_html_text  # Aggiungiamo la funzione di pulizia
})

# Aggiungi questa funzione helper
def format_duration(milliseconds: int) -> str:
    """Converte i millisecondi in formato MM:SS"""
    if not milliseconds:
        return "N/D"
    
    total_seconds = milliseconds // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"

# Aggiungi la funzione ai globals di Jinja2
templates.env.globals.update({
    'now': datetime.now,
    'min': min,
    'max': max,
    'clean_text': clean_html_text,
    'format_duration': format_duration  # Aggiungi la nuova funzione
})

# --- Helper Functions ---

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

@lru_cache(maxsize=1)  # Cache only the latest token
def get_cached_token():
    """Retrieves and caches the token with a TTL."""
    token, expires_at = None, 0  # Initialize token and expiration time

    try:
        response = requests.post(
            API_AUTH_LOGIN, data={"username": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data["data"]["data"]["token"]
        print(token)  # Consider logging this instead of printing
        expires_in = token_data.get(
            "expires_in", TOKEN_CACHE_TTL
        )  # Use default TTL if not provided
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


async def fetch_podcasts(page: int = 1, hits: int = 10000):
    """Fetches podcast data from the external API."""
    url = f"{PODCAST_API_BASE_URL}/?pg={page}&hits={hits}"
    token = await get_token()  # Use await to get the token
    headers = {"Apikey": "testapikey", "Token": token}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching podcasts: {e}")


""" By default get only the last episode """


async def fetch_episodes(podcast_id: int, page: int = 1, hits: int = 1):
    """Fetches episode data for a specific podcast from the external API."""
    if not isinstance(podcast_id, int):
        raise HTTPException(
            status_code=400, detail="Invalid podcast_id. Must be an integer."
        )
    url = f"{PODCAST_API_BASE_URL}/{podcast_id}/?pg={page}&hits={hits}"
    print(url)  # Consider logging this instead of printing
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes: {e}")


async def fetch_all_episodes(podcast_id: int, batch_size: int = 10000):
    """Fetches all episodes for a podcast using pagination."""
    all_episodes = {"data": []}
    page = 1
    
    while True:
        try:
            batch = await fetch_episodes(podcast_id, page=page, hits=batch_size)
            
            # Aggiungiamo gli episodi di questa pagina
            all_episodes["data"].extend(batch["data"])
            
            # Controlliamo se ci sono altre pagine
            total_hits = batch.get("total_hits", 0)
            if len(all_episodes["data"]) >= total_hits:
                break
                
            page += 1
        except Exception as e:
            print(f"Errore nel recupero della pagina {page}: {e}")
            break
    
    return all_episodes


class PodcastRSSGenerator:
    def __init__(self):
        self.base_url = None  # Non impostiamo più un default
        
    def generate_feed(self, podcast_data, episodes, request_base_url):
        # Usiamo l'URL base dalla richiesta se non è configurato
        base_url = os.getenv("BASE_URL") or request_base_url.rstrip('/')
        
        rss = ET.Element("rss", {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
            "xmlns:atom": "http://www.w3.org/2005/Atom"
        })
        
        channel = ET.SubElement(rss, "channel")
        
        # Usiamo l'URL base dalla richiesta
        atom_link = ET.SubElement(channel, "atom:link")
        atom_link.set("href", f"{base_url}/podcast/{podcast_data['id']}/rss")
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")
        
        # Informazioni base del podcast
        title = ET.SubElement(channel, "title")
        title.text = podcast_data["title"]
        
        link = ET.SubElement(channel, "link")
        link.text = f"{base_url}/podcast/{podcast_data['id']}"
        
        description = ET.SubElement(channel, "description")
        description.text = podcast_data.get("description", "")
        
        # Informazioni iTunes richieste
        language = ET.SubElement(channel, "language")
        language.text = "it"
        
        # Categoria iTunes corretta
        itunes_category = ET.SubElement(channel, "itunes:category")
        itunes_category.set("text", "News & Politics")
        
        itunes_explicit = ET.SubElement(channel, "itunes:explicit")
        itunes_explicit.text = "no"
        
        itunes_owner = ET.SubElement(channel, "itunes:owner")
        itunes_email = ET.SubElement(itunes_owner, "itunes:email")
        itunes_email.text = "podcast@ilpost.it"
        
        itunes_image = ET.SubElement(channel, "itunes:image")
        itunes_image.set("href", podcast_data["image"])
        
        itunes_author = ET.SubElement(channel, "itunes:author")
        itunes_author.text = podcast_data["author"]
        
        # Funzione helper per pulire il testo
        def clean_text(text):
            # Mappa di sostituzione per i caratteri speciali
            char_map = {
                "'": "'",
                "'": "'",
                """: '"',
                """: '"',
                "è": "e'",
                "à": "a'",
                "ì": "i'",
                "ò": "o'",
                "ù": "u'",
                "é": "e'",
                "…": "...",
                "–": "-",
                "—": "-",
                "&": "e",
                "&#8217;": "'",  # apostrofo
                "&#8211;": "-",  # en dash
                "&#8212;": "-",  # em dash
            }
            
            for old, new in char_map.items():
                text = text.replace(old, new)
            
            # Rimuove eventuali caratteri HTML residui
            text = text.replace("&amp;", "e")
            return text
        
        # Aggiungiamo gli episodi
        for episode in episodes["data"]:
            item = ET.SubElement(channel, "item")
            
            episode_title = ET.SubElement(item, "title")
            episode_title.text = clean_text(episode["title"])
            
            episode_link = ET.SubElement(item, "link")
            episode_link.text = episode["episode_raw_url"]
            
            # Aggiungiamo guid (richiesto per la validazione)
            guid = ET.SubElement(item, "guid")
            guid.text = episode["episode_raw_url"]
            guid.set("isPermaLink", "true")
            
            # Aggiungiamo enclosure con length
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", episode["episode_raw_url"])
            enclosure.set("type", "audio/mpeg")
            enclosure.set("length", "0")  # Idealmente dovremmo ottenere la dimensione reale del file
            
            if "description" in episode:
                item_description = ET.SubElement(item, "description")
                item_description.text = episode["description"]
            
            # Aggiungiamo la data di pubblicazione
            if "publish_date" in episode:
                pubDate = ET.SubElement(item, "pubDate")
                try:
                    pub_date = datetime.strptime(episode["publish_date"], "%Y-%m-%d %H:%M:%S")
                    pubDate.text = pub_date.strftime("%a, %d %b %Y %H:%M:%S +0000")
                except (ValueError, TypeError):
                    pubDate.text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
            
        return ET.tostring(rss, encoding="unicode", method="xml", xml_declaration=True)

# Aggiungiamo l'istanza del generatore RSS
rss_generator = PodcastRSSGenerator()

# --- API Endpoints ---


@app.get("/podcasts", description="Returns a list of podcasts.")
async def get_podcasts(page: int = 1, hits: int = 50):
    """Returns a list of podcasts."""
    try:
        podcasts = await fetch_podcasts(page, hits)
        return podcasts
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@app.get(
    "/podcasts/search",
    description="Searches for podcasts by title using fuzzy matching.",
)
async def search_podcasts(query: str, request: Request):
    """Searches for podcasts by title using fuzzy matching."""
    podcasts = await fetch_podcasts()
    base_url = request.base_url
    titles = [podcast["title"] for podcast in podcasts["data"]]
    matches = get_close_matches(
        query, titles, n=1, cutoff=0.2
    )  # Adjust cutoff as needed

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


@app.get(
    "/podcast/{podcast_id}",
    description="Returns details of a specific podcast by its ID.",
)
async def get_podcast_by_id(
    podcast_id: int = Path(..., description="The ID of the podcast"),
    page: int = 1,
    hits: int = 1,
):
    """Returns details of a specific podcast by its ID."""
    try:
        podcast = await fetch_episodes(podcast_id, page, hits)
        return podcast
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@app.get(
    "/podcast/{podcast_id}/last",
    description="Returns the last episode of a specific podcast by its ID.",
)
@app.get(
    "/podcast/{podcast_id}/lastepisode",
    description="Returns the last episode of a specific podcast by its ID.",
)
async def get_podcast_by_id(
    podcast_id: int = Path(..., description="The ID of the podcast"),
):
    """Returns details of a specific podcast by its ID."""
    try:
        podcast = await fetch_episodes(podcast_id, page=1, hits=1)
        episode = await fetch_episodes(podcast_id=podcast_id)
        print(episode["data"][0])
        return episode["data"][0]
    except HTTPException as e:
        return JSONResponse(content={"detail": e.detail}, status_code=e.status_code)


@app.get("/healthcheck", description="Simple health check endpoint.")
async def healthcheck():
    """Simple health check endpoint."""
    return {"status": "ok"}


@app.get("/podcast/{podcast_id}/rss")
async def get_podcast_rss(
    podcast_id: int = Path(...),
    request: Request = None
):
    try:
        podcasts = await fetch_podcasts()
        podcast_info = next((p for p in podcasts["data"] if p["id"] == podcast_id), None)
        
        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")
        
        # Usiamo fetch_all_episodes invece di fetch_episodes
        episodes = await fetch_all_episodes(podcast_id)
        
        podcast_data = {
            "id": podcast_id,
            "title": podcast_info["title"],
            "description": podcast_info["description"],
            "author": podcast_info["author"],
            "image": podcast_info["image"]
        }
        
        # Otteniamo l'URL base dalla richiesta
        request_base_url = str(request.base_url).rstrip('/')
        
        rss_feed = rss_generator.generate_feed(podcast_data, episodes, request_base_url)
        
        return Response(
            content=rss_feed,
            media_type="application/rss+xml"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
@app.get("/podcasts/directory", response_class=HTMLResponse)
async def podcast_directory(request: Request):
    """Mostra la directory di tutti i podcast come pagina principale."""
    podcasts = await fetch_podcasts(page=1, hits=100)
    
    # Prepariamo i dati per il template
    podcast_list = [{
        'id': podcast['id'],
        'title': clean_html_text(podcast['title']),  # Puliamo il titolo
        'image': podcast['image'],
        'description': clean_html_text(podcast['description']),  # Puliamo la descrizione
        'author': clean_html_text(podcast['author']),  # Puliamo l'autore
        'rss_url': f"/podcast/{podcast['id']}/rss",
        'slug': podcast['slug']
    } for podcast in podcasts['data']]
    
    return templates.TemplateResponse(
        "podcast_directory.html",
        {
            "request": request,
            "podcasts": podcast_list,
            "year": datetime.now().year
        }
    )


@app.get("/podcast/{podcast_id}/episodes", response_class=HTMLResponse)
async def podcast_episodes(
    podcast_id: int = Path(...),
    request: Request = None,
    page: int = 1,
    per_page: int = 20  # Numero di episodi per pagina
):
    """Mostra gli episodi di un podcast con paginazione."""
    try:
        podcasts = await fetch_podcasts()
        podcast_info = next((p for p in podcasts["data"] if p["id"] == podcast_id), None)
        
        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")
        
        # Recuperiamo tutti gli episodi
        all_episodes = await fetch_all_episodes(podcast_id)
        
        # Calcoliamo la paginazione
        total_episodes = len(all_episodes["data"])
        total_pages = (total_episodes + per_page - 1) // per_page
        
        # Assicuriamoci che la pagina richiesta sia valida
        page = max(1, min(page, total_pages))
        
        # Selezioniamo gli episodi per la pagina corrente
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        current_episodes = all_episodes["data"][start_idx:end_idx]
        
        # Puliamo i dati del podcast
        podcast_info = {
            **podcast_info,
            'title': clean_html_text(podcast_info['title']),
            'description': clean_html_text(podcast_info.get('description', '')),
            'author': clean_html_text(podcast_info.get('author', ''))
        }
        
        # Puliamo i titoli degli episodi
        current_episodes = [{
            **episode,
            'title': clean_html_text(episode['title']),
            'description': clean_html_text(episode.get('description', ''))
        } for episode in all_episodes["data"][start_idx:end_idx]]
        
        return templates.TemplateResponse(
            "podcast_episodes.html",
            {
                "request": request,
                "podcast": podcast_info,
                "episodes": current_episodes,
                "year": datetime.now().year,
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "per_page": per_page,
                    "total_episodes": total_episodes,
                    "has_prev": page > 1,
                    "has_next": page < total_pages,
                    "pages": range(max(1, page - 2), min(total_pages + 1, page + 3))
                }
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/podcast/{podcast_id}/episodes")
async def get_podcast_episodes_json(
    podcast_id: int = Path(...),
    per_page: int = 100
):
    """Restituisce gli episodi di un podcast in formato JSON."""
    try:
        all_episodes = await fetch_all_episodes(podcast_id)
        return {
            "episodes": [{
                "title": clean_html_text(episode["title"]),
                "description": clean_html_text(episode.get("description", "")),
                "episode_raw_url": episode["episode_raw_url"],
                "publish_date": episode.get("publish_date", "")
            } for episode in all_episodes["data"]]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
