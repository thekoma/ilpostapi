# Il Post Podcast API

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/thekoma/ilpostapi/on_tag.yaml?style=flat-square)](https://github.com/thekoma/ilpostapi/actions)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/thekoma/ilpostapi?style=flat-square)](https://github.com/thekoma/ilpostapi/releases)
[![GitHub last commit](https://img.shields.io/github/last-commit/thekoma/ilpostapi?style=flat-square)](https://github.com/thekoma/ilpostapi/commits)
[![Docker Image Version](https://img.shields.io/github/v/tag/thekoma/ilpostapi?label=docker%20tag&style=flat-square)](https://github.com/thekoma/ilpostapi/pkgs/container/ilpostapi)
[![Container Registry](https://img.shields.io/badge/container-ghcr.io-blue?style=flat-square)](https://github.com/thekoma/ilpostapi/pkgs/container/ilpostapi)

Un'interfaccia web elegante per accedere ai podcast de Il Post.

![Screenshot dell'interfaccia](images/image.png)

## Funzionalità

### 🎧 Interfaccia Web
- Design moderno con temi Catppuccin (Latte, Frappé, Macchiato, Mocha)
- Player audio integrato con controlli di navigazione e stato persistente
- Visualizzazione dettagliata degli episodi con data, durata e descrizione
- Sfondo dinamico basato sulla copertina del podcast
- Ricerca fuzzy in tempo reale su titoli, descrizioni e autori
- Refresh individuale degli episodi
- Cache intelligente con persistenza su database SQLite
- Player minimizzabile con animazioni fluide
- Mantenimento dello stato di riproduzione durante la navigazione
- Sincronizzazione del player tra diverse schede del browser

### 📅 Gestione Episodi
- Visualizzazione ordinata per data di pubblicazione
- Informazioni dettagliate sull'ultimo episodio (titolo, data e ora di rilascio)
- Paginazione degli episodi con numero personalizzabile di elementi per pagina
- Riproduzione diretta degli episodi con player integrato
- Download diretto dei file audio
- Gestione della cache con possibilità di refresh manuale
- Descrizioni espandibili con formattazione HTML preservata

### 🔄 Feed RSS e RDF
- Feed RSS compatibile con tutti i principali aggregatori
- Feed RDF per integrazione con sistemi semantici
- Metadati completi per ogni episodio
- Supporto per iTunes/Apple Podcasts
- URL persistenti per ogni episodio

### ⚡ Performance
- Caching intelligente delle richieste API (15 minuti)
- Database SQLite per persistenza dei dati
- Caricamento asincrono dei dati
- Rate limiting intelligente per le chiamate API
- Interfaccia reattiva e fluida
- Ottimizzazione delle immagini e dei contenuti

### 🎨 Design
- Font serif per i titoli (Crimson Pro)
- Font sans-serif per il testo (Inter)
- Icone Font Awesome per una migliore UX
- Animazioni fluide e feedback visivo
- Tema adattivo chiaro/scuro

## Requisiti

### Storage
- L'applicazione richiede un volume persistente montato su `/data` per il database SQLite
- Dimensione consigliata: minimo 1GB per una cache completa
- Permessi di scrittura necessari per l'utente dell'applicazione

## Utilizzo

### 🚀 Deploy con Helm

Prima di deployare l'applicazione, è necessario:

1. Creare un PersistentVolume e PersistentVolumeClaim per il database:

```yaml
# pv.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ilpostapi-data
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: standard
  hostPath:
    path: /data/ilpostapi
---
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ilpostapi-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: standard
```

2. Creare un secret con le credenziali de Il Post:

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: ilpostapi
  labels:
    group: ilpostapi
stringData:
  EMAIL: your-email@domain.com
  PASSWORD: your-password
```

In alternativa, puoi creare il secret direttamente da linea di comando:

```bash
kubectl create secret generic ilpostapi \
  --namespace ilpostapi \
  --from-literal=EMAIL='your-email@domain.com' \
  --from-literal=PASSWORD='your-password'
```

Dopo aver creato le risorse necessarie, puoi procedere con l'installazione usando Helm:

```bash
helm repo add onechart https://chart.onechart.dev
helm repo update

helm install ilpostapi onechart/onechart \
  --version 0.73.0 \
  --namespace ilpostapi \
  --create-namespace \
  --set image.repository=ghcr.io/thekoma/ilpostapi \
  --set image.tag=latest \
  --set containerPort=5000 \
  --set resources.limits.cpu=200m \
  --set resources.limits.memory=256Mi \
  --set resources.requests.cpu=100m \
  --set resources.requests.memory=128Mi \
  --set container.imagePullPolicy=Always \
  --set secretName=ilpostapi \
  --set 'volumes[0].name=data' \
  --set 'volumes[0].path=/data' \
  --set 'volumes[0].size=1Gi' \
  --set 'volumes[0].storageClass=standard'
```

Per una configurazione più avanzata, usa un file `values.yaml`:

```yaml
resources:
  limits:
    cpu: "200m"
    memory: "256Mi"
  requests:
    cpu: "100m"
    memory: "128Mi"
containerPort: 5000
container:
  imagePullPolicy: Always
imagePullSecrets:
  - regcred
image:
  repository: ghcr.io/thekoma/ilpostapi
  tag: latest
secretName: ilpostapi
volumes:
  - name: data
    path: /data
    size: 1Gi
    storageClass: standard
ingresses:
  - host: ilpostapi.yourdomain
    tlsEnabled: true
    tlsSecretName: ilpostapi-ingress-cloudflare-tls
```

### 🐳 Deploy con Docker Compose

Per un deploy locale o di sviluppo, usa Docker Compose. Crea un file `docker-compose.yaml`:

```yaml
version: '3.8'
services:
  ilpostapi:
    image: ghcr.io/thekoma/ilpostapi:latest
    ports:
      - "5000:5000"
    environment:
      - TZ=Europe/Rome
      - EMAIL=your-email@domain.com
      - PASSWORD=your-password
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
    volumes:
      - ./data:/data
    restart: unless-stopped
```

Prima di avviare l'applicazione, crea la directory per i dati:

```bash
mkdir -p ./data
```

> [!IMPORTANT]
> Per impostazione predefinita, il container userà UID:GID 1000:1000. Se hai bisogno di usare un utente diverso, puoi specificarlo in due modi:
> 1. Tramite variabili d'ambiente prima del lancio:
>    ```bash
>    export PUID=1001
>    export PGID=1001
>    docker-compose up -d
>    ```
> 2. Creando un file `.env` nella stessa directory del docker-compose:
>    ```bash
>    echo "PUID=$(id -u)" > .env
>    echo "PGID=$(id -g)" >> .env
>    ```
>
> In entrambi i casi, non è necessario eseguire manualmente il chown della directory.

Poi avvia l'applicazione:

```bash
docker-compose up -d
```

L'applicazione sarà disponibile all'indirizzo `http://localhost:5000`