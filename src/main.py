from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi_mcp import FastApiMCP

from api_client import close_client
from config import logger
from database import init_db
from routes.api import router as api_router
from routes.web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce il ciclo di vita dell'applicazione."""
    logger.info("Inizializzazione dell'applicazione...")
    try:
        await init_db()
        logger.info("Database inizializzato con successo")
        yield
    except Exception as e:
        logger.error(f"Errore durante l'inizializzazione: {e}")
        raise
    finally:
        logger.info("Chiusura dell'applicazione...")
        await close_client()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

app.include_router(web_router)
app.include_router(api_router)

mcp = FastApiMCP(app)
mcp.mount_http()
mcp.mount_sse()
