FROM python:alpine3.21

# Impostiamo prima tutte le variabili d'ambiente
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    CRYPTOGRAPHY_DONT_BUILD_RUST=1 \
    TZ='Europe/Rome'

WORKDIR /usr/src/app

# Installiamo le dipendenze di sistema necessarie per Alpine
RUN apk add --no-cache \
    curl \
    bash \
    gcc \
    g++ \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    make \
    bind-tools

# Installiamo poetry e configuriamolo
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Copiamo solo i file necessari per l'installazione delle dipendenze
COPY poetry.lock pyproject.toml ./

# Installiamo le dipendenze
RUN poetry install --only main --no-interaction --no-ansi

# Copiamo il resto del codice sorgente
COPY src/ ./

# Copiamo i file statici
COPY src/static /app/src/static

EXPOSE 5000

CMD ["uvicorn", "main:app", "--proxy-headers", "--port", "5000", "--host", "0.0.0.0", "--forwarded-allow-ips", "*"]