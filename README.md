<h1 align="center">ilPost Podcasts</h1>

<p align="center">
  <a href="https://github.com/thekoma/ilpostapi/actions/workflows/ci.yml"><img src="https://github.com/thekoma/ilpostapi/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/thekoma/ilpostapi/releases"><img src="https://img.shields.io/github/v/release/thekoma/ilpostapi" alt="Release"></a>
  <a href="https://github.com/thekoma/ilpostapi/pkgs/container/ilpostapi"><img src="https://ghcr-badge.egpl.dev/thekoma/ilpostapi/latest_tag?trim=major&label=latest" alt="Latest Tag"></a>
  <a href="https://ghcr.io/thekoma/ilpostapi"><img src="https://ghcr-badge.egpl.dev/thekoma/ilpostapi/size" alt="Image Size"></a>
  <a href="https://github.com/thekoma/ilpostapi/commits"><img src="https://img.shields.io/github/last-commit/thekoma/ilpostapi" alt="Last Commit"></a>
  <img src="https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white" alt="Python 3.14">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20arm64-blueviolet" alt="Arch: amd64 | arm64">
  <img src="https://img.shields.io/badge/deploy-Docker%20%7C%20K8s-2496ED?logo=docker&logoColor=white" alt="Deploy: Docker | K8s">
  <img src="https://img.shields.io/badge/SSO-OIDC%20%2F%20OAuth2-purple?logo=openid" alt="SSO: OIDC / OAuth2">
  <img src="https://img.shields.io/badge/theme-Catppuccin-EBA0AC?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMCAyMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSIxMCIgY3k9IjEwIiByPSI4IiBmaWxsPSIjRUJBMEFDIi8+PC9zdmc+" alt="Theme: Catppuccin">
  <img src="https://img.shields.io/badge/self--hosted-Raspberry%20Pi%20ready-C51A4A?logo=raspberrypi&logoColor=white" alt="Self-hosted: Raspberry Pi ready">
</p>

Un'interfaccia web per accedere ai podcast de Il Post, con feed RSS e player audio integrato.

| Directory (Macchiato) | Directory (Latte) |
|---|---|
| ![Directory Macchiato](images/directory-macchiato.png) | ![Directory Latte](images/directory-latte.png) |

| Episodi (Macchiato) | Episodi (Latte) |
|---|---|
| ![Episodes Macchiato](images/episodes-macchiato.png) | ![Episodes Latte](images/episodes-latte.png) |

| Feed Popup |
|---|
| ![Feed Popup](images/feed-popup.png) |

## Funzionalita'

### Interfaccia Web
- Design con temi [Catppuccin](https://github.com/catppuccin/catppuccin) (Latte, Frappe, Macchiato, Mocha)
- Player audio persistente con navigazione tra episodi (non si interrompe cambiando pagina)
- Ricerca fuzzy in tempo reale su titoli, descrizioni e autori
- Popup Feed con link RSS e copia negli appunti

### Autenticazione e Utenti
- **Login con username/password** — autenticazione locale con sessioni
- **Login con OIDC** (OpenID Connect) — supporto SSO tramite Authentik o altri provider compatibili
- **Mapping gruppi OIDC** — il ruolo (admin/user) viene assegnato in base ai gruppi del provider
- **Setup iniziale** — il primo utente creato diventa admin automaticamente
- **Protezione admin principale** — l'utente con id=1 non puo' essere cancellato
- **Tutte le pagine richiedono login** tranne healthcheck (`/healthz`, `/readyz`) e documentazione

### Gestione Utenti (Admin)
- Pannello admin per creare, modificare e cancellare utenti
- Cambio ruolo (admin/user) con un click
- Creazione utente senza password con invito via email
- Reset password da admin tramite email
- Cambio password personale (vecchia + nuova)
- Password dimenticata con link di reset via email (richiede SMTP)

### Profilo Utente
- Visualizzazione informazioni profilo e token RSS personale
- Rigenerazione del token RSS
- URL di esempio per configurare lettori RSS

### Feed RSS con Token
- Feed RSS accessibili tramite token nell'URL: `/podcast/{id}/rss/{token}`
- Ogni utente ha un token RSS unico, visibile nel profilo
- I lettori RSS "stupidi" possono accedere ai feed senza sessione
- Rigenerazione del token in caso di compromissione

### Podcast Preferiti
- Stella su ogni podcast per aggiungerlo/rimuoverlo dai preferiti
- Toggle "Solo preferiti" stile iOS per filtrare la homepage
- I preferiti sono per-utente

### Export OPML
- Download OPML con tutti i podcast: `/api/opml/{token}`
- Download OPML solo preferiti: `/api/opml/{token}?favorites_only=true`
- I link RSS nell'OPML includono il token dell'utente
- Pulsanti di download direttamente nella homepage

### Episodi
- Cover del podcast nell'header con sfondo dinamico blurrato
- Paginazione con numero personalizzabile di elementi per pagina
- Descrizioni espandibili con formattazione HTML
- Riproduzione diretta e download dei file audio

### Architettura
- **FastAPI** con moduli separati (routes, API client, feeds, auth)
- **SQLite** asincrono via SQLAlchemy per cache persistente e gestione utenti
- **Navigazione pjax** — il player audio sopravvive ai cambi di pagina
- **Rate limiting** per le chiamate all'API de Il Post
- **Health checks** reali (`/healthz`, `/readyz`) per Kubernetes
- **MCP** (Model Context Protocol) endpoint integrato
- **bcrypt** per l'hashing delle password
- **authlib** per l'integrazione OIDC
- **aiosmtplib** per l'invio email (reset password, inviti)
- **109 test** con pytest e pytest-asyncio

## Variabili d'Ambiente

### Obbligatorie

| Variabile | Descrizione | Esempio |
|---|---|---|
| `EMAIL` | Email per l'autenticazione all'API de Il Post | `user@example.com` |
| `PASSWORD` | Password per l'autenticazione all'API de Il Post | `mypassword` |

### Autenticazione App

| Variabile | Descrizione | Default |
|---|---|---|
| `SECRET_KEY` | Chiave segreta per le sessioni e i token di reset. **Cambiare in produzione!** | Generata casualmente |
| `BASE_URL` | URL base dell'applicazione (usato per link nelle email) | `http://localhost:5000` |

### OIDC (opzionale)

L'OIDC si attiva automaticamente quando `OIDC_ISSUER`, `OIDC_CLIENT_ID` e `OIDC_CLIENT_SECRET` sono tutti impostati.

| Variabile | Descrizione | Default |
|---|---|---|
| `OIDC_ISSUER` | URL dell'issuer OIDC (es. Authentik) | `""` (disabilitato) |
| `OIDC_CLIENT_ID` | Client ID dell'applicazione OIDC | `""` |
| `OIDC_CLIENT_SECRET` | Client Secret dell'applicazione OIDC | `""` |
| `OIDC_REDIRECT_URI` | URL di callback (es. `https://app.example.com/auth/callback`) | `""` (auto-detect) |
| `OIDC_ADMIN_GROUP` | Nome del gruppo OIDC che mappa al ruolo admin | `admin` |
| `OIDC_PROVIDER_NAME` | Nome del provider mostrato nel pulsante di login | `SSO` |

> **Nota Authentik**: lo scope `groups` non esiste di default. Va creato come Scope Mapping custom in Customization > Property Mappings con expression `return {"groups": [group.name for group in request.user.ak_groups.all()]}` e poi assegnato al provider OAuth2.

### SMTP (opzionale)

L'SMTP si attiva automaticamente quando `SMTP_HOST` e `SMTP_FROM` sono impostati. Senza SMTP: il reset password via email, gli inviti e la creazione utente senza password non sono disponibili.

| Variabile | Descrizione | Default |
|---|---|---|
| `SMTP_HOST` | Hostname del server SMTP | `""` (disabilitato) |
| `SMTP_PORT` | Porta del server SMTP | `587` |
| `SMTP_USER` | Username SMTP (opzionale per smarthost) | `""` |
| `SMTP_PASSWORD` | Password SMTP (opzionale per smarthost) | `""` |
| `SMTP_FROM` | Indirizzo email mittente | `""` |
| `SMTP_USE_TLS` | Usa TLS per la connessione SMTP | `true` |

### Altre

| Variabile | Descrizione | Default |
|---|---|---|
| `DB_DIR` | Directory per il database SQLite | `/data` |
| `TZ` | Timezone | `UTC` |

## Requisiti

### Storage
- Volume persistente montato su `/data` per il database SQLite
- Dimensione consigliata: minimo 1GB
- Permessi di scrittura necessari per UID 1000

## Deploy

### Helm (bjw-s app-template)

Il chart usa [bjw-s app-template](https://bjw-s-labs.github.io/helm-charts/docs/app-template/).

1. Creare il secret con le credenziali (vedi `deploy/helm/secret.yaml.example`):

```bash
cp deploy/helm/secret.yaml.example deploy/helm/secret.yaml
# Edita deploy/helm/secret.yaml con i tuoi valori
kubectl apply -f deploy/helm/secret.yaml
```

2. Installare:

```bash
helm repo add bjw-s https://bjw-s-labs.github.io/helm-charts
helm repo update

helm install ilpostapi bjw-s/app-template \
  --namespace ilpostapi \
  --create-namespace \
  -f deploy/helm/values.yaml
```

Per abilitare l'ingress o personalizzare, crea un file `my-values.yaml`:

```yaml
ingress:
  main:
    enabled: true
    className: nginx
    hosts:
      - host: ilpostapi.yourdomain.com
        paths:
          - path: /
            pathType: Prefix
            service:
              identifier: main
              port: http
    tls:
      - secretName: ilpostapi-tls
        hosts:
          - ilpostapi.yourdomain.com
```

```bash
helm install ilpostapi bjw-s/app-template \
  --namespace ilpostapi \
  --create-namespace \
  -f deploy/helm/values.yaml \
  -f my-values.yaml
```

### Docker Compose

```yaml
services:
  ilpostapi:
    image: ghcr.io/thekoma/ilpostapi:latest
    ports:
      - "5000:5000"
    environment:
      - TZ=Europe/Rome
      - EMAIL=your-email@domain.com
      - PASSWORD=your-password
      - SECRET_KEY=change-me-to-a-random-string
      # OIDC (opzionale)
      # - OIDC_ISSUER=https://auth.example.com/application/o/ilpostapi/
      # - OIDC_CLIENT_ID=your-client-id
      # - OIDC_CLIENT_SECRET=your-client-secret
      # - OIDC_REDIRECT_URI=http://localhost:5000/auth/callback
      # - OIDC_ADMIN_GROUP=admin
      # - OIDC_PROVIDER_NAME=Authentik
      # SMTP (opzionale)
      # - SMTP_HOST=smtp.example.com
      # - SMTP_PORT=587
      # - SMTP_USER=user
      # - SMTP_PASSWORD=password
      # - SMTP_FROM=noreply@example.com
      # - SMTP_USE_TLS=true
    volumes:
      - ./data:/data
    restart: unless-stopped
```

```bash
mkdir -p ./data
docker compose up -d
```

L'applicazione sara' disponibile su `http://localhost:5000`.

### Primo avvio

Al primo accesso l'applicazione mostra la pagina di setup per creare l'utente admin iniziale. Questo utente (id=1) non potra' essere cancellato.

## Sviluppo

```bash
# Copia e compila il secret
cp deploy/helm/secret.yaml.example deploy/helm/secret.yaml
# Edita deploy/helm/secret.yaml con le tue credenziali

# Avvia con skaffold (richiede minikube o cluster k8s)
skaffold dev --tail
```

Skaffold sincronizza automaticamente i file Python, HTML, CSS e JS nel pod senza rebuild.

### Test

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

La suite include 109 test che coprono: operazioni CRUD utenti, flusso di setup e login, cambio password, gestione admin, profilo, autenticazione token RSS, protezione route, preferiti e generazione OPML.

## Endpoints Principali

| Endpoint | Descrizione | Auth |
|---|---|---|
| `/` | Homepage con lista podcast | Sessione |
| `/podcast/{id}/episodes` | Episodi di un podcast | Sessione |
| `/podcast/{id}/rss/{token}` | Feed RSS (per lettori RSS) | Token |
| `/api/opml/{token}` | Export OPML tutti i podcast | Token |
| `/api/opml/{token}?favorites_only=true` | Export OPML solo preferiti | Token |
| `/api/favorites` | Lista preferiti utente | Sessione |
| `/api/favorites/{id}` | Toggle preferito (POST) | Sessione |
| `/auth/login` | Pagina di login | Nessuna |
| `/auth/login/oidc` | Redirect a provider OIDC | Nessuna |
| `/auth/setup` | Setup primo admin | Nessuna |
| `/auth/change-password` | Cambio password | Sessione |
| `/auth/forgot-password` | Reset password via email | Nessuna |
| `/profile` | Profilo utente e token RSS | Sessione |
| `/admin/users` | Gestione utenti | Admin |
| `/healthz` | Liveness probe | Nessuna |
| `/readyz` | Readiness probe | Nessuna |
