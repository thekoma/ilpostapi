import logging
import json
import sys
from typing import Any, Dict
from logging.config import dictConfig


class JSONFormatter(logging.Formatter):
    """Formattatore personalizzato per output JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Formatta il record di log in JSON."""
        # Crea un dizionario base con i campi standard
        log_object = {
            "asctime": self.formatTime(record),
            "name": record.name,
            "levelname": record.levelname,
            "message": record.getMessage(),
        }

        # Aggiungi il nome del task se presente
        if hasattr(record, "taskName"):
            log_object["taskName"] = record.taskName

        # Aggiungi eventuali eccezioni
        if record.exc_info:
            log_object["exc_info"] = self.formatException(record.exc_info)

        # Usiamo ensure_ascii=False per preservare gli emoji
        return json.dumps(log_object, ensure_ascii=False)


class LogConfig:
    """Configurazione base per il logging."""

    @staticmethod
    def get_config(level: str = "INFO") -> Dict[str, Any]:
        """Restituisce la configurazione del logging."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JSONFormatter}},
            "handlers": {
                "default": {
                    "formatter": "json",
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": level},  # Root logger
                "uvicorn": {  # Logger di uvicorn
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.access": {  # Logger di uvicorn.access
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.error": {  # Logger di uvicorn.error
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
            },
        }


def setup_logging(level: str = "INFO") -> None:
    """Configura il logging per l'applicazione."""
    config = LogConfig.get_config(level)
    dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Ottiene un logger configurato."""
    return logging.getLogger(name)
