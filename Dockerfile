FROM python:3.13-slim

# Set environment variables
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    PIP_PREFER_BINARY=1 \
    TZ='Europe/Rome'

WORKDIR /usr/app

# Installiamo solo i pacchetti essenziali
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    dnsutils \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installiamo poetry
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Copiamo solo i file necessari per l'installazione delle dipendenze
COPY poetry.lock pyproject.toml ./

# Installiamo le dipendenze
RUN poetry install --only main --no-interaction --no-ansi

# Copiamo il resto del codice
COPY src/ ./
COPY entrypoint.sh ./
COPY dev-tools/ ./dev-tools/

# Setup permissions
RUN chmod +x entrypoint.sh && \
    groupadd -g 1000 ilpoastapi && \
    useradd -u 1000 -g ilpoastapi -s /bin/bash ilpoastapi && \
    chown -R ilpoastapi:ilpoastapi /usr/app && \
    chmod -R u+w /usr/app

EXPOSE 5000

USER ilpoastapi

ENTRYPOINT ["./entrypoint.sh"]
