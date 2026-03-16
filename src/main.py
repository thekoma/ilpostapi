from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi_mcp import FastApiMCP
from starlette.middleware.sessions import SessionMiddleware

from api_client import close_client
from auth_dependencies import AuthRedirect
from config import SECRET_KEY, logger
from database import init_db
from routes.api import router as api_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from routes.profile import router as profile_router
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

# Session middleware for cookie-based sessions
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")


@app.exception_handler(AuthRedirect)
async def auth_redirect_handler(request: Request, exc: AuthRedirect):
    return RedirectResponse(url=exc.url, status_code=302)


# Auth routes first (no auth required)
app.include_router(auth_router)
# Then protected routes
app.include_router(profile_router)
app.include_router(admin_router)
app.include_router(web_router)
app.include_router(api_router)

mcp = FastApiMCP(app)
mcp.mount_http()
mcp.mount_sse()
