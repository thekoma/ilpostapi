import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import inspect

from utils.logging import get_logger
from .models import Base, Podcast, Episode

logger = get_logger(__name__)

DB_DIR = os.getenv("DB_DIR", "/data")
DB_NAME = "podcasts.db"


def check_database_directory():
    """Controlla e prepara la directory del database."""
    db_path = Path(DB_DIR)

    if not db_path.exists():
        try:
            db_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory {DB_DIR} creata con successo")
        except Exception as e:
            logger.error(f"Impossibile creare la directory {DB_DIR}: {e}")
            sys.exit(1)

    try:
        test_file = db_path / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.info(f"Permessi di scrittura verificati in {DB_DIR}")
    except Exception as e:
        logger.error(f"Permessi di scrittura insufficienti in {DB_DIR}: {e}")
        sys.exit(1)


def get_database_url():
    """Costruisce l'URL del database."""
    db_path = Path(DB_DIR) / DB_NAME
    return f"sqlite+aiosqlite:///{db_path}"


check_database_directory()

engine = create_async_engine(
    get_database_url(),
    echo=False,
    poolclass=NullPool,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


def _check_schema_current(sync_conn):
    """Verifica che lo schema del DB abbia tutte le colonne necessarie."""
    inspector = inspect(sync_conn)
    if not sync_conn.dialect.has_table(sync_conn, "podcasts"):
        return False
    if not sync_conn.dialect.has_table(sync_conn, "users"):
        return False
    columns = {c["name"] for c in inspector.get_columns("episodes")}
    required = {"summary", "author", "image_url", "share_url", "slug", "episode_type"}
    if not required.issubset(columns):
        return False
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    user_required = {"username", "email", "password_hash", "role", "rss_token", "oauth_sub"}
    return user_required.issubset(user_columns)


async def init_db():
    """Inizializza il database, ricreando le tabelle se lo schema e' cambiato."""
    try:
        async with engine.begin() as conn:
            schema_ok = await conn.run_sync(_check_schema_current)
            if not schema_ok:
                logger.info("Schema non aggiornato, ricreazione tabelle...")
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Tabelle ricreate con successo")
            else:
                logger.debug("Database esistente, schema aggiornato")
    except Exception as e:
        logger.error(f"Errore inizializzazione database: {e}")
        raise


async def get_db():
    """Dependency per ottenere una sessione del database."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
