import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError

from utils.logging import get_logger
from .models import Base, Podcast, Episode  # Importiamo Base da models

logger = get_logger(__name__)

# Configurazione del database
DB_DIR = os.getenv("DB_DIR", "/data")
DB_NAME = "podcasts.db"


def check_database_directory():
    """Controlla e prepara la directory del database."""
    db_path = Path(DB_DIR)

    # Controlla se la directory esiste
    if not db_path.exists():
        try:
            db_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory {DB_DIR} creata con successo")
        except Exception as e:
            logger.error(f"Impossibile creare la directory {DB_DIR}: {str(e)}")
            sys.exit(1)

    # Verifica i permessi di scrittura
    try:
        test_file = db_path / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.info(f"Permessi di scrittura verificati in {DB_DIR}")
    except Exception as e:
        logger.error(f"Permessi di scrittura insufficienti in {DB_DIR}: {str(e)}")
        sys.exit(1)


def get_database_url():
    """Costruisce l'URL del database."""
    db_path = Path(DB_DIR) / DB_NAME
    return f"sqlite+aiosqlite:///{db_path}"


# Verifica la directory del database all'importazione
check_database_directory()

# Crea l'engine asincrono
engine = create_async_engine(
    get_database_url(),
    echo=False,  # Disabilitiamo il logging SQL per debug
    poolclass=NullPool,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)

# Crea la sessione asincrona
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    """Crea le tabelle nel database."""
    try:
        async with engine.begin() as conn:
            logger.info("Creazione delle tabelle in corso...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Tabelle create con successo")
    except Exception as e:
        logger.error(f"Errore durante la creazione delle tabelle: {str(e)}")
        raise


async def check_tables_exist():
    """Verifica se le tabelle esistono."""
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute("SELECT 1 FROM podcasts LIMIT 1")
                await session.execute("SELECT 1 FROM episodes LIMIT 1")
        return True
    except Exception:
        return False


async def init_db():
    """Inizializza il database."""
    try:
        async with engine.begin() as conn:
            # Verifica se le tabelle esistono già
            result = await conn.run_sync(
                lambda sync_conn: sync_conn.dialect.has_table(sync_conn, "podcasts")
            )
            if not result:
                logger.info("🏗️ Database vuoto. Creazione tabelle in corso...")
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ Tabelle create con successo")
            else:
                logger.debug("🔍 Database esistente, tabelle già presenti")
    except Exception as e:
        logger.error(f"❌ Errore durante l'inizializzazione del database: {str(e)}")
        raise


async def get_db():
    """Dependency per ottenere una sessione del database."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
