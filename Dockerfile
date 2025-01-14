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

WORKDIR /usr/app

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
    bind-tools \
    sqlite

RUN mkdir /data && chown nobody:nobody /data

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
COPY entrypoint.sh ./
COPY dev-tools/ ./dev-tools/
# Rendiamo eseguibile lo script di entrypoint
RUN chmod +x entrypoint.sh
# Rendi scrivibile i file per l'utente nobody
RUN  chown -R 1000:1000 /usr/app && chmod -R u+w /usr/app

# Create user ilpoastapi with uid 1000 and gid 1000 using adduser, and add group ilpoastapi
RUN  addgroup -g 1000 ilpoastapi && adduser -u 1000 -G ilpoastapi -s /bin/sh -D ilpoastapi && chown -R ilpoastapi:ilpoastapi /usr/app && chmod -R u+w /usr/app

EXPOSE 5000

# Imposta l'utente non-root
# USER nobody
USER ilpoastapi

ENTRYPOINT ["./entrypoint.sh"]
