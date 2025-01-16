import os
import time
import logging
from functools import lru_cache
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import html
import re
from pathlib import Path as FilePath
from typing import Dict, Optional
import asyncio
import httpx

from difflib import get_close_matches
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response
from fastapi import Path
from dotenv import load_dotenv, find_dotenv
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from cachetools import TTLCache, cached
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy.sql import select

from utils.logging import setup_logging, get_logger, LogConfig
from utils.rate_limiter import rate_limiter, api_rate_limiter
from database import get_db, init_db, AsyncSessionLocal, Podcast, Episode
from database.operations import (
    get_or_create_podcast,
    update_podcast_check_time,
    get_podcast_episodes,
    save_episodes,
)

# Configurazione del logging
setup_logging()
logger = get_logger(__name__)

# Configurazione del client HTTP
http_client = httpx.Client(
    timeout=30.0, verify=False
)  # verify=False per gestire il punto extra nell'URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce il ciclo di vita dell'applicazione."""
    logger.info("🚀 Inizializzazione dell'applicazione...")
    try:
        # Inizializza il database
        logger.info("🗄️ Inizializzazione del database...")
        await init_db()
        logger.info("✅ Database inizializzato con successo")
        yield
    except Exception as e:
        logger.error(f"❌ Errore durante l'inizializzazione: {str(e)}")
        raise
    finally:
        logger.info("👋 Chiusura dell'applicazione...")
        # Chiudi il client HTTP
        http_client.close()


# Load environment variables from .env file
load_dotenv(find_dotenv())

# --- Configuration ---
# Get EMAIL from environment
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# Raise an error if EMAIL is not found
if not EMAIL or not PASSWORD:
    logger.error("EMAIL and PASSWORD are required but not set properly")
    raise ValueError("EMAIL and PASSWORD are required but not set properly")

# Base URLs for the external APIs
PODCAST_API_BASE_URL = "https://api-prod.ilpost.it/podcast/v1/podcast"
API_AUTH_LOGIN = "https://api-prod.ilpost.it/user/v1/auth/login"

# Token caching configuration
TOKEN_CACHE_TTL = 2 * 60 * 60  # 2 hours in seconds
EPISODE_CACHE = {}  # Cache per gli episodi
EPISODES_LIST_CACHE = {}  # Cache per le liste di episodi
PODCASTS_CACHE = {}  # Cache per la lista dei podcast
CACHE_TTL = 15 * 60  # 15 minuti in secondi

# Token caching configuration
token_cache = TTLCache(maxsize=1, ttl=TOKEN_CACHE_TTL)  # Cache per il token

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)

# Configurazione template e file statici
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# Aggiungiamo le funzioni necessarie ai globals di Jinja2
templates.env.globals.update(
    {
        "now": datetime.now,
        "min": min,  # Aggiungiamo la funzione min
        "max": max,  # Aggiungiamo anche max per sicurezza
    }
)

# Dopo la creazione dell'istanza templates
templates.env.globals.update(now=datetime.now)


# Aggiungiamo la funzione helper a livello globale per poterla usare ovunque
def clean_html_text(text: str) -> str:
    """Pulisce il testo da tag HTML e caratteri speciali."""
    if not text:
        return ""

    # Prima decodifichiamo le entità HTML
    text = html.unescape(text)

    # Poi rimuoviamo eventuali tag HTML
    text = re.sub(r"<[^>]+>", "", text)

    # Sostituiamo alcuni caratteri speciali comuni
    replacements = {
        "'": "'",
        "'": "'",
        """: '"',
        """: '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "\n": " ",  # Sostituiamo i newline con spazi
        "\r": " ",  # Sostituiamo i carriage return con spazi
        "\t": " ",  # Sostituiamo i tab con spazi
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Rimuoviamo spazi multipli
    text = " ".join(text.split())

    return text.strip()


# Aggiungiamo la funzione ai globals di Jinja2
templates.env.globals.update(
    {
        "now": datetime.now,
        "min": min,
        "max": max,
        "clean_text": clean_html_text,  # Aggiungiamo la funzione di pulizia
    }
)


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
templates.env.globals.update(
    {
        "now": datetime.now,
        "min": min,
        "max": max,
        "clean_text": clean_html_text,
        "format_duration": format_duration,  # Aggiungi la nuova funzione
    }
)


def format_date_main(isodate):
    """Formatta giorno e mese della data."""
    if not isodate:
        return "N/D"
    try:
        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return f"{date.day:02d}/{date.month:02d}"
    except (ValueError, AttributeError):
        return "N/D"


def format_date_year(isodate):
    """Estrae l'anno dalla data."""
    if not isodate:
        return ""
    try:
        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return str(date.year)
    except (ValueError, AttributeError):
        return ""


def format_date_time(isodate):
    """Formatta l'ora della data."""
    if not isodate:
        return ""
    try:
        date = datetime.fromisoformat(isodate.replace("Z", "+00:00"))
        return f"{date.hour:02d}:{date.minute:02d}"
    except (ValueError, AttributeError):
        return ""


# Aggiungiamo le funzioni ai globals di Jinja2
templates.env.globals.update(
    {
        "now": datetime.now,
        "min": min,
        "max": max,
        "clean_text": clean_html_text,
        "format_duration": format_duration,
        "formatDateMain": format_date_main,  # Aggiunte le nuove funzioni
        "formatDateYear": format_date_year,
        "formatDateTime": format_date_time,
    }
)

# Aggiungiamo le funzioni ai filtri di Jinja2
templates.env.filters.update(
    {
        "formatDateMain": format_date_main,
        "formatDateYear": format_date_year,
        "formatDateTime": format_date_time,
    }
)


# Funzione per l'escape di stringhe JavaScript
def escapejs(text):
    """Escape di stringhe per JavaScript."""
    if not text:
        return ""
    text = str(text)
    chars = {
        "\\": "\\\\",
        '"': '\\"',
        "'": "\\'",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\f": "\\f",
        "\b": "\\b",
        "<": "\\u003C",
        ">": "\\u003E",
        "&": "\\u0026",
    }
    return "".join(chars.get(c, c) for c in text)


# Aggiungiamo le funzioni ai filtri di Jinja2
templates.env.filters.update(
    {
        "formatDateMain": format_date_main,
        "formatDateYear": format_date_year,
        "formatDateTime": format_date_time,
        "escapejs": escapejs,  # Aggiungiamo il nuovo filtro
    }
)

# --- Helper Functions ---

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")


@cached(cache=token_cache)
def get_cached_token():
    """Ottiene un token di autenticazione (cached)."""
    logger.info("🔄 Cache MISS - Richiesta nuovo token di autenticazione")
    try:
        response = http_client.post(
            API_AUTH_LOGIN, data={"username": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data["data"]["data"]["token"]
        return token
    except httpx.HTTPError as e:
        logger.error(f"Errore durante l'autenticazione: {str(e)}")
        logger.error(
            f"Risposta API: {e.response.text if hasattr(e, 'response') else 'Nessuna risposta'}"
        )
        raise HTTPException(status_code=500, detail="Errore di autenticazione")


async def get_token():
    """Provides the token, refreshing it if expired."""
    try:
        return get_cached_token()
    except Exception as e:
        # Se c'è un errore, invalidiamo la cache e riproviamo
        token_cache.clear()
        return get_cached_token()


async def make_api_request(url: str, headers: Optional[Dict] = None) -> Dict:
    """Effettua una richiesta API con rate limiting."""
    await api_rate_limiter.wait()
    logger.info(f"🔄 Cache MISS - Chiamata API esterna: {url}")
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 429:  # Too Many Requests
                logger.warning("Rate limit raggiunto, attendo prima di riprovare")
                await asyncio.sleep(10)  # Attendi 1 minuto
                return await make_api_request(url, headers)
            response.raise_for_status()
            data = response.json()
            # Verifica la struttura della risposta
            if "data" not in data:
                logger.error(f"Risposta API non valida: {data}")
                raise HTTPException(status_code=500, detail="Risposta API non valida")
            return data
    except httpx.HTTPError as e:
        logger.error(f"Errore durante la richiesta API: {str(e)}")
        logger.error(f"URL: {url}")
        logger.error(f"Headers: {headers}")
        logger.error(
            f"Risposta: {e.response.text if hasattr(e, 'response') else 'Nessuna risposta'}"
        )
        raise HTTPException(status_code=500, detail="Errore nella richiesta API")


async def fetch_podcasts(page: int = 1, hits: int = 10000):
    """Recupera la lista dei podcast."""
    cache_key = f"{page}_{hits}"
    current_time = datetime.now().timestamp()

    # Controlla se abbiamo una versione cached valida
    if cache_key in PODCASTS_CACHE:
        cached_data, cache_time = PODCASTS_CACHE[cache_key]
        if current_time - cache_time < CACHE_TTL:
            logger.info(f"🎯 Cache HIT - Lista podcast trovata in cache")
            return cached_data

    token = get_cached_token()
    # Il Post API richiede sia il token di autenticazione che una Apikey statica
    headers = {"Apikey": "testapikey", "Token": token}
    logger.info(
        f"📻 Recupero podcast dalla pagina {page} con {hits} risultati per pagina"
    )
    data = await make_api_request(
        f"{PODCAST_API_BASE_URL}/?pg={page}&hits={hits}", headers=headers
    )

    # Salva nella cache
    PODCASTS_CACHE[cache_key] = (data, current_time)

    return data


async def fetch_episodes(podcast_id: int, page: int = 1, hits: int = 1):
    """Recupera gli episodi di un podcast."""
    token = get_cached_token()
    # Il Post API richiede sia il token di autenticazione che una Apikey statica
    headers = {"Apikey": "testapikey", "Token": token}
    logger.info(f"🎧 Recupero episodi per il podcast {podcast_id} dalla pagina {page}")
    return await make_api_request(
        f"{PODCAST_API_BASE_URL}/{podcast_id}/?pg={page}&hits={hits}", headers=headers
    )


async def fetch_episodes_batch(episode_ids: list[int]) -> Dict:
    """Recupera un gruppo di episodi in una singola chiamata.

    Args:
        episode_ids: Lista di ID degli episodi da recuperare
    Returns:
        Dict con i dati degli episodi
    """
    if not episode_ids:
        return {"data": []}

    token = get_cached_token()
    # Il Post API richiede sia il token di autenticazione che una Apikey statica
    headers = {"Apikey": "testapikey", "Token": token}

    # Convertiamo gli ID in stringa separata da virgole
    ids_str = ",".join(map(str, episode_ids))
    logger.info(f"🎧 Recupero batch di {len(episode_ids)} episodi")

    return await make_api_request(
        f"{PODCAST_API_BASE_URL}/episodes?ids={ids_str}", headers=headers
    )


async def fetch_all_episodes(podcast_id: int, batch_size: int = 500):
    """Recupera tutti gli episodi di un podcast usando la paginazione ottimizzata.

    Args:
        podcast_id: ID del podcast
        batch_size: Numero di episodi per pagina (default: 500 per performance ottimale)
    """
    current_time = datetime.now().timestamp()

    # Controlla se abbiamo una versione cached valida
    if podcast_id in EPISODES_LIST_CACHE:
        cached_data, cache_time = EPISODES_LIST_CACHE[podcast_id]
        if current_time - cache_time < CACHE_TTL:
            logger.info(
                f"🎯 Cache HIT - Lista episodi del podcast {podcast_id} trovata in cache"
            )
            return cached_data

    logger.info(f"📥 Inizio recupero di tutti gli episodi per il podcast {podcast_id}")

    # Prima richiesta per ottenere il totale degli episodi
    initial_data = await fetch_episodes(podcast_id, page=1, hits=1)
    total_episodes = initial_data["head"]["data"]["total"]
    logger.info(f"📊 Totale episodi da recuperare: {total_episodes}")

    # Se abbiamo meno di 500 episodi, li prendiamo tutti in una volta
    if total_episodes <= batch_size:
        try:
            logger.info(
                f"📦 Recupero tutti gli {total_episodes} episodi in una singola richiesta"
            )
            response = await fetch_episodes(podcast_id, page=1, hits=total_episodes)
            if response and "data" in response:
                result = {"data": response["data"]}
                EPISODES_LIST_CACHE[podcast_id] = (result, current_time)
                return result
        except Exception as e:
            logger.error(f"❌ Errore nel recupero degli episodi: {str(e)}")
            return {"data": []}

    # Per podcast più grandi, usiamo la paginazione con batch di 500
    all_episodes = []
    total_pages = (total_episodes + batch_size - 1) // batch_size

    for page in range(1, total_pages + 1):
        try:
            logger.info(
                f"📃 Recupero pagina {page}/{total_pages} (batch di {batch_size} episodi)"
            )
            response = await fetch_episodes(podcast_id, page, batch_size)

            if not response or "data" not in response:
                logger.error(f"❌ Risposta non valida per la pagina {page}")
                continue

            episodes = response["data"]
            if not episodes:
                logger.warning(f"⚠️ Nessun episodio trovato nella pagina {page}")
                break

            all_episodes.extend(episodes)
            logger.info(f"✅ Recuperati {len(all_episodes)}/{total_episodes} episodi")

        except Exception as e:
            logger.error(f"❌ Errore nel recupero della pagina {page}: {str(e)}")
            continue

    # Verifica che abbiamo recuperato almeno il 90% degli episodi
    if len(all_episodes) < total_episodes * 0.9:
        logger.error(
            f"❌ Recuperati solo {len(all_episodes)}/{total_episodes} episodi. "
            "Non abbastanza per considerare il recupero completo"
        )
        return {"data": []}

    result = {"data": all_episodes}
    EPISODES_LIST_CACHE[podcast_id] = (result, current_time)

    logger.info(f"✨ Recupero completato: {len(all_episodes)}/{total_episodes} episodi")
    return result


class PodcastRSSGenerator:
    def __init__(self):
        self.base_url = None  # Non impostiamo più un default

    def generate_feed(self, podcast_data, episodes, request_base_url):
        # Funzione helper per pulire il testo
        def clean_text(text):
            if not text:
                return ""
            # Mappa di sostituzione per i caratteri speciali
            char_map = {
                "'": "'",
                "'": "'",
                """: '"', """: '"',
                "è": "è",
                "à": "à",
                "ì": "ì",
                "ò": "ò",
                "ù": "ù",
                "é": "é",
                "…": "...",
                "–": "-",
                "—": "-",
                "&#8217;": "'",
                "&#8211;": "-",
                "&#8212;": "-",
            }

            for old, new in char_map.items():
                text = text.replace(old, new)

            return text.strip()

        base_url = os.getenv("BASE_URL") or request_base_url.rstrip("/")

        rss = ET.Element(
            "rss",
            {
                "version": "2.0",
                "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
                "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
                "xmlns:atom": "http://www.w3.org/2005/Atom",
                "xmlns:googleplay": "http://www.google.com/schemas/play-podcasts/1.0",
                "xmlns:podcast": "https://podcastindex.org/namespace/1.0",
            },
        )

        channel = ET.SubElement(rss, "channel")

        # Atom link (richiesto per la validazione)
        atom_link = ET.SubElement(channel, "atom:link")
        atom_link.set("href", f"{base_url}/podcast/{podcast_data['id']}/rss")
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

        # Informazioni base del podcast
        title = ET.SubElement(channel, "title")
        title.text = clean_text(podcast_data["title"])

        link = ET.SubElement(channel, "link")
        link.text = f"{base_url}/podcast/{podcast_data['id']}"

        description = ET.SubElement(channel, "description")
        description.text = clean_text(podcast_data.get("description", ""))

        # Informazioni sull'autore in vari formati per massima compatibilità
        author = clean_text(podcast_data.get("author", "Il Post"))

        # 1. Tag author standard RSS
        author_elem = ET.SubElement(channel, "author")
        author_elem.text = f"{author} (podcast@ilpost.it)"

        # 2. Tag managingEditor (per RSS 2.0)
        managing_editor = ET.SubElement(channel, "managingEditor")
        managing_editor.text = f"podcast@ilpost.it ({author})"

        # 3. Tag iTunes author
        itunes_author = ET.SubElement(channel, "itunes:author")
        itunes_author.text = author

        # 4. Tag googleplay:author
        googleplay_author = ET.SubElement(channel, "googleplay:author")
        googleplay_author.text = author

        # Immagine del podcast (in vari formati)
        image_url = podcast_data["image"]

        # 1. Tag image standard RSS
        image = ET.SubElement(channel, "image")
        image_title = ET.SubElement(image, "title")
        image_title.text = clean_text(podcast_data["title"])
        image_url_elem = ET.SubElement(image, "url")
        image_url_elem.text = image_url
        image_link = ET.SubElement(image, "link")
        image_link.text = f"{base_url}/podcast/{podcast_data['id']}"

        # 2. Tag iTunes image
        itunes_image = ET.SubElement(channel, "itunes:image")
        itunes_image.set("href", image_url)

        # 3. Tag googleplay:image
        googleplay_image = ET.SubElement(channel, "googleplay:image")
        googleplay_image.set("href", image_url)

        # Altre informazioni richieste
        language = ET.SubElement(channel, "language")
        language.text = "it"

        copyright_elem = ET.SubElement(channel, "copyright")
        copyright_elem.text = f"© {datetime.now().year} {author}"

        # Categoria iTunes e Google Play
        itunes_category = ET.SubElement(channel, "itunes:category")
        itunes_category.set("text", "News")

        googleplay_category = ET.SubElement(channel, "googleplay:category")
        googleplay_category.set("text", "News")

        # Informazioni aggiuntive iTunes
        itunes_explicit = ET.SubElement(channel, "itunes:explicit")
        itunes_explicit.text = "false"

        itunes_type = ET.SubElement(channel, "itunes:type")
        itunes_type.text = "episodic"

        itunes_owner = ET.SubElement(channel, "itunes:owner")
        itunes_name = ET.SubElement(itunes_owner, "itunes:name")
        itunes_name.text = author
        itunes_email = ET.SubElement(itunes_owner, "itunes:email")
        itunes_email.text = "podcast@ilpost.it"

        # Aggiungiamo gli episodi
        for episode in episodes["data"]:
            item = ET.SubElement(channel, "item")

            # GUID univoco (richiesto)
            guid = ET.SubElement(item, "guid")
            guid.text = episode["episode_raw_url"]
            guid.set("isPermaLink", "true")

            # Titolo e link
            episode_title = ET.SubElement(item, "title")
            episode_title.text = clean_text(episode["title"])

            episode_link = ET.SubElement(item, "link")
            episode_link.text = episode["episode_raw_url"]

            # Descrizione in vari formati
            description_text = clean_text(
                episode.get("content_html") or episode.get("description", "")
            )
            if description_text:
                item_description = ET.SubElement(item, "description")
                item_description.text = description_text

                itunes_summary = ET.SubElement(item, "itunes:summary")
                itunes_summary.text = description_text

                content_encoded = ET.SubElement(item, "content:encoded")
                content_encoded.text = f"<![CDATA[{description_text}]]>"

            # Autore dell'episodio
            episode_author = ET.SubElement(item, "author")
            episode_author.text = f"{author} (podcast@ilpost.it)"

            itunes_author_episode = ET.SubElement(item, "itunes:author")
            itunes_author_episode.text = author

            # Data di pubblicazione
            if "date" in episode:
                pubDate = ET.SubElement(item, "pubDate")
                try:
                    pub_date = datetime.fromisoformat(episode["date"])
                    pubDate.text = pub_date.strftime("%a, %d %b %Y %H:%M:%S %z")
                except (ValueError, TypeError) as e:
                    logger.error(f"Errore nel parsing della data: {e}")
                    pubDate.text = datetime.now(
                        tz=timezone(timedelta(hours=1))
                    ).strftime("%a, %d %b %Y %H:%M:%S %z")

            # Durata dell'episodio
            if "milliseconds" in episode and episode["milliseconds"] is not None:
                duration_secs = episode["milliseconds"] // 1000
                hours = duration_secs // 3600
                minutes = (duration_secs % 3600) // 60
                seconds = duration_secs % 60

                itunes_duration = ET.SubElement(item, "itunes:duration")
                if hours > 0:
                    itunes_duration.text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    itunes_duration.text = f"{minutes:02d}:{seconds:02d}"

            # Enclosure per il file audio
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", episode["episode_raw_url"])
            enclosure.set("type", "audio/mpeg")
            enclosure.set("length", str(episode.get("size", "0")))

        return ET.tostring(rss, encoding="unicode", method="xml", xml_declaration=True)


# Aggiungiamo l'istanza del generatore RSS
rss_generator = PodcastRSSGenerator()


class PodcastRDFGenerator:
    def __init__(self):
        self.base_url = None

    def generate_feed(self, podcast_data, episodes, request_base_url):
        def clean_text(text):
            # Riusiamo la stessa funzione di pulizia del testo
            char_map = {
                "'": "'",
                "'": "'",
                """: '"', """: '"',
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
                "&#8217;": "'",
                "&#8211;": "-",
                "&#8212;": "-",
            }
            for old, new in char_map.items():
                text = text.replace(old, new)
            return text.replace("&amp;", "e")

        base_url = os.getenv("BASE_URL") or request_base_url.rstrip("/")

        # Creazione dell'elemento root RDF
        rdf = ET.Element(
            "rdf:RDF",
            {
                "xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "xmlns": "http://purl.org/rss/1.0/",
                "xmlns:dc": "http://purl.org/dc/elements/1.1/",
                "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
                "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            },
        )

        # Creazione del channel
        channel = ET.SubElement(
            rdf,
            "channel",
            {"rdf:about": f"{base_url}/podcast/{podcast_data['id']}/rdf"},
        )

        # Metadati del canale
        title = ET.SubElement(channel, "title")
        title.text = clean_text(podcast_data["title"])

        link = ET.SubElement(channel, "link")
        link.text = f"{base_url}/podcast/{podcast_data['id']}"

        description = ET.SubElement(channel, "description")
        description.text = clean_text(podcast_data.get("description", ""))

        # Metadati Dublin Core
        dc_language = ET.SubElement(channel, "dc:language")
        dc_language.text = "it"

        dc_publisher = ET.SubElement(channel, "dc:publisher")
        dc_publisher.text = "Il Post"

        # Struttura completa dell'autore per RDF
        author = ET.SubElement(channel, "author")
        author_name = ET.SubElement(author, "name")
        author_name.text = clean_text(podcast_data.get("author", "Il Post"))
        author_uri = ET.SubElement(author, "uri")
        author_uri.text = "https://www.ilpost.it"

        dc_creator = ET.SubElement(channel, "dc:creator")
        dc_creator.text = clean_text(podcast_data.get("author", "Il Post"))

        # Lista degli item
        items = ET.SubElement(channel, "items")
        seq = ET.SubElement(items, "rdf:Seq")

        # Creazione degli item
        for episode in episodes["data"]:
            # Riferimento nella sequenza
            ET.SubElement(seq, "rdf:li", {"rdf:resource": episode["episode_raw_url"]})

            # Item completo
            item = ET.SubElement(rdf, "item", {"rdf:about": episode["episode_raw_url"]})

            item_title = ET.SubElement(item, "title")
            item_title.text = clean_text(episode["title"])

            item_link = ET.SubElement(item, "link")
            item_link.text = episode["episode_raw_url"]

            if "description" in episode:
                item_description = ET.SubElement(item, "description")
                item_description.text = clean_text(episode["description"])

            # Data di pubblicazione in formato Dublin Core
            if "date" in episode:
                dc_date = ET.SubElement(item, "dc:date")
                try:
                    pub_date = datetime.fromisoformat(episode["date"])
                    dc_date.text = pub_date.strftime("%Y-%m-%dT%H:%M:%S%z")
                except (ValueError, TypeError) as e:
                    print(f"Errore nel parsing della data RDF: {e}")
                    dc_date.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

            # Enclosure per il file audio
            enclosure = ET.SubElement(
                item,
                "enclosure",
                {"rdf:resource": episode["episode_raw_url"], "type": "audio/mpeg"},
            )

        return ET.tostring(rdf, encoding="unicode", method="xml", xml_declaration=True)


# Aggiungiamo l'istanza del generatore RDF
rdf_generator = PodcastRDFGenerator()

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
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Recuperiamo le informazioni del podcast
        podcasts = await fetch_podcasts()
        podcast_info = next(
            (p for p in podcasts["data"] if p["id"] == podcast_id), None
        )

        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")

        # Recuperiamo gli episodi dal database
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)

        # Se dobbiamo aggiornare o non abbiamo episodi, li recuperiamo dall'API
        if needs_update or not episodes:
            await api_rate_limiter.wait()
            api_episodes = await fetch_all_episodes(podcast_id)

            # Otteniamo o creiamo il podcast nel database
            db_podcast = await get_or_create_podcast(
                db, str(podcast_id), api_episodes["data"][0]
            )
            if not db_podcast:
                raise HTTPException(
                    status_code=404, detail="Impossibile creare o recuperare il podcast"
                )

            # Salviamo gli episodi nel database
            await save_episodes(db, db_podcast, api_episodes["data"])
            await update_podcast_check_time(db, db_podcast)

            # Rileggiamo gli episodi dal database
            episodes, _ = await get_podcast_episodes(db, podcast_id)

        # Verifichiamo e aggiorniamo le descrizioni mancanti usando fetch_episode_details
        episodes_to_update = [ep for ep in episodes if not ep.description_verified]
        if episodes_to_update:
            total_episodes = len(episodes_to_update)
            logger.info(
                f"Aggiornamento descrizioni per il podcast '{podcast_info['title']}' ({len(episodes_to_update)}/{len(episodes)} episodi da aggiornare)"
            )
            for idx, episode in enumerate(episodes_to_update, 1):
                try:
                    await api_rate_limiter.wait()
                    logger.info(
                        f"[{podcast_info['title']}] Recupero descrizione episodio {idx}/{total_episodes}: {episode.title}"
                    )
                    episode_details = await fetch_episode_details(
                        podcast_id, int(episode.ilpost_id), db
                    )
                    if episode_details and "data" in episode_details:
                        episode_data = episode_details["data"]
                        episode.description = episode_data.get(
                            "content_html", ""
                        ) or episode_data.get("description", "")
                        episode.description_verified = True
                        await db.commit()
                except Exception as e:
                    logger.error(
                        f"[{podcast_info['title']}] Errore nell'aggiornamento della descrizione per episodio {idx}/{total_episodes}: {str(e)}"
                    )
                    continue

        # Prepariamo i dati per il feed RSS
        episodes_data = {"data": []}
        for episode in episodes:
            episode_data = {
                "id": episode.id,
                "title": episode.title,
                "description": episode.description,
                "content_html": episode.description,
                "episode_raw_url": episode.audio_url,
                "date": (
                    episode.publication_date.isoformat()
                    if episode.publication_date
                    else None
                ),
                "milliseconds": episode.duration * 1000 if episode.duration else None,
            }
            episodes_data["data"].append(episode_data)

        # Creiamo l'oggetto podcast
        podcast_data = {
            "id": podcast_id,
            "title": podcast_info["title"],
            "description": podcast_info["description"],
            "author": podcast_info["author"],
            "image": podcast_info["image"],
        }

        # Otteniamo l'URL base dalla richiesta
        request_base_url = str(request.base_url).rstrip("/")

        # Generiamo il feed RSS
        rss_feed = rss_generator.generate_feed(
            podcast_data, episodes_data, request_base_url
        )

        return Response(content=rss_feed, media_type="application/rss+xml")
    except Exception as e:
        logger.error(f"Errore nella generazione del feed RSS: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def get_last_episode_info(podcast_id: int, db: AsyncSession = None) -> tuple:
    """Recupera le informazioni dell'ultimo episodio con caching."""
    current_time = datetime.now().timestamp()

    # Controlla se abbiamo una versione cached valida
    if podcast_id in EPISODE_CACHE:
        cached_data, cache_time = EPISODE_CACHE[podcast_id]
        if current_time - cache_time < CACHE_TTL:
            return cached_data

    # Se non c'è cache valida, prima controlliamo nel database
    if db:
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)
        if episodes and not needs_update:
            # Ordiniamo per data di pubblicazione (più recenti prima)
            episodes.sort(
                key=lambda x: x.publication_date or datetime.min, reverse=True
            )
            if episodes:
                latest = episodes[0]
                cached_info = (
                    (
                        latest.publication_date.isoformat()
                        if latest.publication_date
                        else None
                    ),
                    latest.title,
                    latest.duration * 1000 if latest.duration else None,
                )
                EPISODE_CACHE[podcast_id] = (cached_info, current_time)
                return cached_info

    # Se non troviamo nel database o serve un aggiornamento, chiamiamo l'API
    last_episode = await fetch_episodes(podcast_id, page=1, hits=1)
    last_episode_date = None
    last_episode_title = None
    last_episode_duration = None

    if last_episode and last_episode.get("data") and len(last_episode["data"]) > 0:
        episode = last_episode["data"][0]
        last_episode_date = episode.get("date")
        last_episode_title = episode.get("title")
        last_episode_duration = episode.get("milliseconds")

    # Salva nella cache
    cached_info = (last_episode_date, last_episode_title, last_episode_duration)
    EPISODE_CACHE[podcast_id] = (cached_info, current_time)

    return cached_info


async def get_last_episode_date(podcast_id: int) -> str:
    """Recupera la data dell'ultimo episodio."""
    last_episode_date, _, _ = await get_last_episode_info(podcast_id)
    return last_episode_date


@app.get("/", response_class=HTMLResponse)
@app.get("/podcasts/directory", response_class=HTMLResponse)
async def podcast_directory(request: Request, db: AsyncSession = Depends(get_db)):
    """Mostra la directory di tutti i podcast come pagina principale."""
    try:
        # Prima controlliamo la cache
        current_time = datetime.now().timestamp()
        needs_update = False

        if "directory" in PODCASTS_CACHE:
            cached_data, cache_time = PODCASTS_CACHE["directory"]
            if current_time - cache_time < CACHE_TTL:
                logger.info("🎯 Cache HIT - Directory podcast trovata in cache")
                podcast_list = cached_data
            else:
                needs_update = True
                podcast_list = cached_data  # Usiamo i dati cached mentre aggiorniamo
        else:
            # Se non c'è cache, facciamo un aggiornamento completo
            needs_update = True
            await update_podcast_directory_cache()
            cached_data, _ = PODCASTS_CACHE.get("directory", ([], current_time))
            podcast_list = cached_data

        return templates.TemplateResponse(
            "podcast_directory.html",
            {
                "request": request,
                "podcasts": podcast_list,
                "year": datetime.now().year,
                "needs_update": needs_update,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching podcast directory: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Error fetching podcast directory", "error": str(e)},
        )


@app.post("/api/podcasts/update", response_class=JSONResponse)
async def update_podcasts_directory(db: AsyncSession = Depends(get_db)):
    """Aggiorna la directory dei podcast in background."""
    try:
        success = await update_podcast_directory_cache()
        if not success:
            raise HTTPException(
                status_code=500, detail={"message": "Error updating podcast directory"}
            )

        cached_data, _ = PODCASTS_CACHE.get(
            "directory", ([], datetime.now().timestamp())
        )
        return JSONResponse({"success": True, "podcasts": cached_data})
    except Exception as e:
        logger.error(f"Error updating podcast directory: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Error updating podcast directory", "error": str(e)},
        )


@app.get("/podcast/{podcast_id}/episodes", response_class=HTMLResponse)
async def podcast_episodes(
    podcast_id: int = Path(...),
    request: Request = None,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Prima recuperiamo le informazioni del podcast
        podcasts = await fetch_podcasts()
        podcast_info = next(
            (p for p in podcasts["data"] if p["id"] == podcast_id), None
        )

        if not podcast_info:
            raise HTTPException(status_code=404, detail="Podcast non trovato")

        # Creiamo l'oggetto podcast per il template
        podcast = {
            "id": podcast_info["id"],
            "title": clean_html_text(podcast_info["title"]),
            "image": podcast_info["image"],
            "description": clean_html_text(podcast_info["description"]),
            "author": clean_html_text(podcast_info["author"]),
            "rss_url": f"/podcast/{podcast_info['id']}/rss",
            "slug": podcast_info["slug"],
        }

        # Controlliamo nel database
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)

        # Ordiniamo gli episodi per data di pubblicazione (più recenti prima)
        episodes.sort(key=lambda x: x.publication_date or datetime.min, reverse=True)

        # Calcoliamo i parametri di paginazione
        total_items = len(episodes)
        total_pages = (total_items + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1

        # Generiamo la lista delle pagine da mostrare
        max_visible_pages = 5
        if total_pages <= max_visible_pages:
            pages = list(range(1, total_pages + 1))
        else:
            # Mostriamo sempre la prima e l'ultima pagina
            pages = [1]
            # Aggiungiamo le pagine intorno a quella corrente
            start_page = max(2, page - 1)
            end_page = min(total_pages - 1, page + 1)
            if start_page > 2:
                pages.append("...")
            pages.extend(range(start_page, end_page + 1))
            if end_page < total_pages - 1:
                pages.append("...")
            pages.append(total_pages)

        # Paginazione
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_episodes = episodes[start_idx:end_idx]

        # Creiamo l'oggetto pagination
        pagination = {
            "current_page": page,
            "per_page": per_page,
            "total_items": total_items,  # Alias per il template
            "total_episodes": total_items,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "pages": pages,
            "needs_update": needs_update,  # Aggiungiamo questa informazione per il frontend
        }

        # Serializziamo gli episodi per il template
        serialized_episodes = []
        for episode in paginated_episodes:
            episode_dict = {
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
                "milliseconds": (episode.duration * 1000 if episode.duration else None),
                "duration": format_duration(
                    episode.duration * 1000 if episode.duration else None
                ),
            }
            serialized_episodes.append(episode_dict)

        return templates.TemplateResponse(
            "podcast_episodes.html",
            {
                "request": request,
                "podcast": podcast,
                "episodes": serialized_episodes,
                "pagination": pagination,
                "podcast_id": podcast_id,
            },
        )
    except Exception as e:
        logger.error(
            f"Error fetching episodes for podcast {podcast_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error fetching episodes for podcast {podcast_id}",
                "error": str(e),
            },
        )


def serialize_episode(episode):
    """Serializza un episodio del database in un dizionario."""
    return {
        "id": episode.id,
        "ilpost_id": episode.ilpost_id,
        "title": episode.title,
        "description": episode.description,
        "audio_url": episode.audio_url,
        "date": (
            episode.publication_date.isoformat() if episode.publication_date else None
        ),
        "duration": (
            episode.duration * 1000 if episode.duration else None
        ),  # Convertiamo in millisecondi
    }


@app.get("/api/podcast/{podcast_id}/episodes")
async def get_podcast_episodes_json(
    podcast_id: int = Path(...), per_page: int = 100, db: AsyncSession = Depends(get_db)
):
    try:
        episodes, needs_update = await get_podcast_episodes(db, podcast_id)

        if needs_update:
            await api_rate_limiter.wait()
            response = await fetch_episodes(
                podcast_id, hits=10000
            )  # Prendiamo tutti gli episodi disponibili
            podcast_data = response.get("data", [])

            if not podcast_data:
                raise HTTPException(
                    status_code=404, detail="Nessun episodio trovato per questo podcast"
                )

            # Otteniamo prima il podcast esistente o ne creiamo uno nuovo
            podcast = await get_or_create_podcast(db, str(podcast_id), podcast_data[0])
            if not podcast:
                raise HTTPException(
                    status_code=404, detail="Impossibile creare o recuperare il podcast"
                )

            # Ora possiamo salvare gli episodi
            await save_episodes(db, podcast, podcast_data)
            await update_podcast_check_time(db, podcast)

            # Rileggiamo gli episodi dal database
            episodes, _ = await get_podcast_episodes(db, podcast.id)

        if not episodes:
            return {"data": []}

        # Ordiniamo gli episodi per data di pubblicazione (più recenti prima)
        episodes.sort(key=lambda x: x.publication_date or datetime.min, reverse=True)

        # Serializziamo gli episodi
        serialized_episodes = [
            serialize_episode(episode) for episode in episodes[:per_page]
        ]

        return {"data": serialized_episodes}
    except Exception as e:
        logger.error(
            f"Error fetching episodes for podcast {podcast_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error fetching episodes for podcast {podcast_id}",
                "error": str(e),
            },
        )


@app.get("/podcast/{podcast_id}/rdf")
async def get_podcast_rdf(podcast_id: int = Path(...), request: Request = None):
    """Genera il feed RDF per un podcast specifico."""
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

        rdf_feed = rdf_generator.generate_feed(podcast_data, episodes, request_base_url)

        return Response(content=rdf_feed, media_type="application/rdf+xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clear-cache")
async def clear_cache():
    """Pulisce la cache degli episodi e dei token."""
    episode_cache.clear()
    token_cache.clear()
    return {"message": "Cache pulita con successo"}


async def fetch_episode_details(
    podcast_id: int, episode_id: int, db: AsyncSession = None
):
    """Recupera i dettagli di un singolo episodio."""
    try:
        # Se abbiamo una sessione DB, prima cerchiamo lì
        if db:
            stmt = select(Episode).where(Episode.ilpost_id == str(episode_id))
            result = await db.execute(stmt)
            episode = result.scalar_one_or_none()
            if episode and episode.description_verified:
                logger.info(
                    f"🎯 Cache HIT - Dettagli episodio {episode_id} trovati nel database"
                )
                return {
                    "data": {
                        "id": episode.id,
                        "title": episode.title,
                        "description": episode.description,
                        "content_html": episode.description,
                        "episode_raw_url": episode.audio_url,
                        "date": (
                            episode.publication_date.isoformat()
                            if episode.publication_date
                            else None
                        ),
                        "milliseconds": (
                            episode.duration * 1000 if episode.duration else None
                        ),
                    }
                }

        # Se non lo troviamo nel DB o la descrizione non è verificata, lo recuperiamo dall'API
        url = f"{PODCAST_API_BASE_URL}/{podcast_id}/{episode_id}/"
        logger.warning(
            f"📝 Recupero dettagli episodio {episode_id} del podcast {podcast_id}"
        )

        token = await get_token()
        headers = {"Apikey": "testapikey", "Token": token}
        await api_rate_limiter.wait()

        try:
            data = await make_api_request(url, headers)
            logger.debug(f"✨ Dettagli episodio recuperati: {data}")

            # Se abbiamo una sessione DB, salviamo i dati
            if db and data and "data" in data:
                episode_data = data["data"]
                description = episode_data.get("content_html", "") or episode_data.get(
                    "summary", ""
                )

                if not episode:
                    episode = Episode(
                        ilpost_id=str(episode_id),
                        podcast_id=podcast_id,
                        title=episode_data.get("title", ""),
                        description=description,
                        description_verified=True,
                        audio_url=episode_data.get("episode_raw_url", ""),
                        publication_date=(
                            datetime.fromisoformat(
                                episode_data.get("date", "").replace("Z", "+00:00")
                            )
                            if episode_data.get("date")
                            else None
                        ),
                        duration=(
                            episode_data.get("milliseconds", 0) // 1000
                            if episode_data.get("milliseconds")
                            else None
                        ),
                    )
                    db.add(episode)
                    logger.debug(f"✅ Creato nuovo episodio nel database: {episode_id}")
                else:
                    episode.title = episode_data.get("title", episode.title)
                    episode.description = description
                    episode.description_verified = True
                    episode.audio_url = episode_data.get(
                        "episode_raw_url", episode.audio_url
                    )
                    if episode_data.get("date"):
                        episode.publication_date = datetime.fromisoformat(
                            episode_data["date"].replace("Z", "+00:00")
                        )
                    if episode_data.get("milliseconds"):
                        episode.duration = episode_data["milliseconds"] // 1000
                    logger.debug(f"🔄 Aggiornato episodio nel database: {episode_id}")

                await db.commit()

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"⚠️ Endpoint dettagli episodio non disponibile: {url}")
                if db and episode:
                    episode.description_verified = True
                    await db.commit()
                return None
            raise

    except Exception as e:
        logger.error(f"❌ Errore nel recupero dettagli episodio {episode_id}: {str(e)}")
        if db and episode:
            episode.description_verified = True
            await db.commit()
        return None


@app.get("/api/podcast/{podcast_id}/episode/{episode_id}/description")
async def get_episode_description(
    podcast_id: int = Path(...),
    episode_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Recupera la descrizione di un singolo episodio."""
    try:
        # Prima cerchiamo nel database
        stmt = select(Episode).where(Episode.ilpost_id == episode_id)
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()

        if episode and episode.description:
            return {
                "description": clean_html_text(episode.description),
                "content_html": episode.description,
            }

        # Se non lo troviamo nel database o non ha descrizione, lo recuperiamo dall'API
        await api_rate_limiter.wait()
        if episode_details := await fetch_episode_details(
            podcast_id, int(episode_id), db=db
        ):
            # Estraiamo i dati secondo lo schema API_PODCAST_EPISODE
            episode_data = episode_details.get("data", {})
            description = episode_data.get("content_html", "") or episode_data.get(
                "summary", ""
            )

            return {
                "description": clean_html_text(description),
                "content_html": description,
            }

        # Se non abbiamo trovato nulla, restituiamo una descrizione vuota
        return {"description": "", "content_html": ""}

    except Exception as e:
        logger.error(
            f"Errore nel recupero descrizione episodio {episode_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Errore nel recupero descrizione episodio {episode_id}",
                "error": str(e),
            },
        )


@app.post("/api/podcast/{podcast_id}/episode/{episode_id}/refresh")
async def refresh_episode(
    podcast_id: int = Path(...),
    episode_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Forza il refresh delle informazioni di un episodio dal backend."""
    try:
        # Invalidiamo la cache per questo episodio
        stmt = select(Episode).where(Episode.ilpost_id == episode_id)
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()

        if episode:
            # Forziamo il refresh impostando description_verified a False
            episode.description_verified = False
            await db.commit()

        # Recuperiamo i nuovi dati dall'API
        await api_rate_limiter.wait()
        episode_details = await fetch_episode_details(
            podcast_id, int(episode_id), db=db
        )

        if not episode_details:
            raise HTTPException(status_code=404, detail="Episodio non trovato")

        return {"message": "Episodio aggiornato con successo"}

    except Exception as e:
        logger.error(
            f"Errore nell'aggiornamento dell'episodio {episode_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Errore nell'aggiornamento dell'episodio {episode_id}",
                "error": str(e),
            },
        )


@app.post("/api/podcast/{podcast_id}/update", response_class=JSONResponse)
async def update_podcast(
    podcast_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Forza l'aggiornamento di un podcast specifico."""
    try:
        # Invalidiamo la cache per questo podcast
        stmt = select(Podcast).where(Podcast.ilpost_id == str(podcast_id))
        result = await db.execute(stmt)
        podcast = result.scalar_one_or_none()

        if podcast:
            # Forziamo il refresh impostando last_checked a None
            podcast.last_checked = None
            await db.commit()

        # Recuperiamo i nuovi dati dall'API usando il metodo che recupera tutti gli episodi
        await api_rate_limiter.wait()
        response = await fetch_all_episodes(podcast_id, batch_size=500)

        if not response or "data" not in response:
            raise HTTPException(
                status_code=404, detail="Nessun episodio trovato per questo podcast"
            )

        podcast_data = response["data"]

        # Otteniamo o creiamo il podcast
        podcast = await get_or_create_podcast(db, str(podcast_id), podcast_data[0])
        if not podcast:
            raise HTTPException(
                status_code=404, detail="Impossibile creare o recuperare il podcast"
            )

        # Salviamo gli episodi
        await save_episodes(db, podcast, podcast_data)
        await update_podcast_check_time(db, podcast)

        # Rileggiamo gli episodi dal database
        episodes, _ = await get_podcast_episodes(db, podcast_id)

        # Ordiniamo gli episodi per data di pubblicazione (più recenti prima)
        episodes.sort(key=lambda x: x.publication_date or datetime.min, reverse=True)

        # Serializziamo gli episodi
        serialized_episodes = []
        for episode in episodes:
            episode_dict = {
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
                "milliseconds": (episode.duration * 1000 if episode.duration else None),
                "duration": format_duration(
                    episode.duration * 1000 if episode.duration else None
                ),
            }
            serialized_episodes.append(episode_dict)

        return JSONResponse({"success": True, "episodes": serialized_episodes})
    except Exception as e:
        logger.error(f"Error updating podcast {podcast_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error updating podcast {podcast_id}",
                "error": str(e),
            },
        )


# Aggiungiamo le funzioni ai filtri di Jinja2
templates.env.filters.update(
    {
        "formatDateMain": format_date_main,
        "formatDateYear": format_date_year,
        "formatDateTime": format_date_time,
        "escapejs": escapejs,
        "clean_text": clean_html_text,
        "format_duration": format_duration,
    }
)


async def check_updates_from_bff():
    """Controlla gli aggiornamenti usando l'endpoint BFF Homepage.
    Restituisce un dizionario con gli ID dei podcast e le date degli ultimi episodi."""
    token = get_cached_token()
    headers = {"Apikey": "testapikey", "Token": token}

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.get(
                "https://api-prod.ilpost.it/podcast/v1/bff/hp", headers=headers
            )
            response.raise_for_status()
            data = response.json()

            # Dizionario per tenere traccia dell'ultimo episodio per ogni podcast
            latest_episodes = {}

            if "data" in data:
                for component in data["data"]:
                    if "data" in component:
                        for episode in component["data"]:
                            if "parent" in episode and "id" in episode["parent"]:
                                podcast_id = episode["parent"]["id"]
                                episode_date = episode.get("date")

                                # Aggiorniamo solo se questa è la data più recente per questo podcast
                                if podcast_id not in latest_episodes or (
                                    episode_date
                                    and (
                                        not latest_episodes[podcast_id]
                                        or episode_date
                                        > latest_episodes[podcast_id]["date"]
                                    )
                                ):
                                    latest_episodes[podcast_id] = {
                                        "date": episode_date,
                                        "title": episode["parent"].get("title"),
                                        "last_episode_title": episode.get("title"),
                                        "last_episode_duration": episode.get(
                                            "milliseconds"
                                        ),
                                    }

            return latest_episodes
    except Exception as e:
        logger.error(f"Errore nel controllo degli aggiornamenti BFF: {str(e)}")
        return {}


async def update_podcast_directory_cache():
    """Aggiorna la cache della directory dei podcast usando le informazioni dal BFF."""
    try:
        # Otteniamo gli ultimi aggiornamenti dal BFF
        latest_updates = await check_updates_from_bff()

        if not latest_updates:
            logger.warning("Nessun aggiornamento trovato dal BFF")
            return False

        # Recuperiamo la cache corrente
        current_time = datetime.now().timestamp()
        needs_full_update = True

        if "directory" in PODCASTS_CACHE:
            cached_data, cache_time = PODCASTS_CACHE["directory"]
            podcast_list = cached_data
            needs_full_update = False

            # Aggiorniamo solo i podcast che hanno nuovi episodi
            for podcast in podcast_list:
                podcast_id = podcast["id"]
                if podcast_id in latest_updates:
                    latest = latest_updates[podcast_id]
                    current_date = podcast.get("last_episode_date")

                    if not current_date or latest["date"] > current_date:
                        logger.info(
                            f"Aggiornamento podcast {podcast['title']} con nuovo episodio"
                        )
                        podcast.update(
                            {
                                "last_episode_date": latest["date"],
                                "last_episode_title": clean_html_text(
                                    latest["last_episode_title"]
                                ),
                                "last_episode_duration": format_duration(
                                    latest["last_episode_duration"]
                                ),
                            }
                        )
        else:
            # Se non abbiamo cache, dobbiamo fare un aggiornamento completo
            podcasts = await fetch_podcasts(page=1, hits=100)
            podcast_list = []

            for podcast in podcasts["data"]:
                latest = latest_updates.get(podcast["id"], {})
                podcast_data = {
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
                podcast_list.append(podcast_data)

        # Ordiniamo i podcast per data dell'ultimo episodio
        podcast_list.sort(
            key=lambda x: (
                x["last_episode_date"]
                if x["last_episode_date"]
                else "1970-01-01T00:00:00+00:00"
            ),
            reverse=True,
        )

        # Aggiorniamo la cache
        PODCASTS_CACHE["directory"] = (podcast_list, current_time)

        return True
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento della directory: {str(e)}")
        return False
