FROM python:3.13-alpine3.19

# Set environment variables
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    # Usa i wheel pre-compilati quando disponibili
    PIP_PREFER_BINARY=1 \
    # Evita di compilare cryptography da sorgente
    CRYPTOGRAPHY_DONT_BUILD_RUST=1 \
    TZ='Europe/Rome'

WORKDIR /usr/app

# Installiamo solo le dipendenze necessarie
# Nota: gcc e python3-dev sono ancora necessari per alcuni pacchetti
RUN apk add --no-cache \
    curl \
    bash \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    bind-tools \
    sqlite \
    # Aggiungiamo rust solo durante la build
    cargo

# Installiamo poetry
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Copiamo solo i file necessari per l'installazione delle dipendenze
COPY poetry.lock pyproject.toml ./

# Installiamo le dipendenze e rimuoviamo i tool di build
RUN poetry install --only main --no-interaction --no-ansi && \
    apk del gcc python3-dev musl-dev libffi-dev openssl-dev cargo

# Copiamo il resto del codice
COPY src/ ./
COPY entrypoint.sh ./
COPY dev-tools/ ./dev-tools/

# Setup permissions
RUN chmod +x entrypoint.sh && \
    addgroup -g 1000 ilpoastapi && \
    adduser -u 1000 -G ilpoastapi -s /bin/sh -D ilpoastapi && \
    chown -R ilpoastapi:ilpoastapi /usr/app && \
    chmod -R u+w /usr/app

EXPOSE 5000

USER ilpoastapi

ENTRYPOINT ["./entrypoint.sh"]
