# Guida al Deployment: Jukebox Portal

Questa guida illustra come effettuare il deploy dell'applicazione su un server Linux (es. Ubuntu Server) utilizzando Docker Compose.

L'architettura utilizza `python:3.11-slim` come immagine base, garantendo tempi di compilazione rapidissimi per librerie scientifiche complesse come `librosa` e `numpy` e una perfetta compatibilità con i requisiti hardware dell'analisi audio.

## 1. Struttura del Progetto sul Server
Crea una cartella sul server (es. `/opt/jukebox`) e inserisci i seguenti file:
- `docker-compose.yml`
- `config.yaml`
- L'intera repository del codice (incluso il `Dockerfile` e la cartella `src/`).

## 2. Il file `docker-compose.yml`
Assicurati di configurare correttamente i percorsi per i volumi:

```yaml
version: '3.8'

services:
  jukebox-bot:
    build: .
    container_name: jukebox-bot
    restart: unless-stopped
    ports:
      - "8020:8020"
    volumes:
      - ./config.yaml:/app/config.yaml
      - /percorso/alla/tua/musica:/musica
      - ./data:/app/data
      - ./temp_exports:/app/temp_exports
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8020/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## 3. Configurazione `config.yaml`
Crea un file chiamato `config.yaml` nella stessa cartella del `docker-compose.yml` e incollaci dentro questa struttura base, compilando i campi richiesti:

```yaml
telegram:
  bot_token: "IL_TUO_TOKEN_TELEGRAM" # Da ottenere tramite @BotFather su Telegram
  allowed_users: 
    - 123456789                      # Il tuo ID numerico Telegram (per bloccare gli sconosciuti)

discord:
  bot_token: "IL_TUO_TOKEN_DISCORD"  # (Opzionale) Dal Discord Developer Portal (seleziona intent "Message Content")

acoustid:
  api_key: "TUA_API_KEY"             # Da acoustid.org (serve per il de-duplicatore)

navidrome:
  url: "http://192.168.x.x:4533"     # Indirizzo del server Navidrome
  username: "admin"                  # Utente Navidrome
  password: "password123"            # Password Navidrome

app:
  music_dir: "/musica"               # Non toccare se usi Docker
  audio_format: "mp3"                # Formato preferito (mp3, flac, m4a)
  audio_quality: "320"               # Qualità (es. 320 per mp3, 0 per flac)
```
## 4. Requisiti Hardware & Networking
- **Porte**: L'unica porta necessaria in locale è la `8020` per la Web UI. **Non è necessario aprire alcuna porta sul router** né per Telegram (se in modalità Polling) né per Discord (che utilizza WebSockets in uscita).
- **CPU/RAM**: L'uso standard (FastAPI + Discord) consuma ~100MB di RAM. L'utilizzo di CPU ha dei picchi brevi quando vengono processati brani per l'estrazione BPM e Tonalità (tramite `librosa`) o durante la normalizzazione del volume (`ffmpeg-normalize`).

## 5. Avvio e Aggiornamento
Per avviare l'applicazione in background:
```bash
docker compose up --build -d
```

Per aggiornare l'applicazione (dopo aver git-pullato nuovi update o cambiato dipendenze in `requirements.txt`):
```bash
docker compose build --no-cache
docker compose up -d
```

## 6. Accesso alla Web UI (PWA)
Una volta avviato il container, apri il browser all'indirizzo `http://[IP-DEL-SERVER]:8020`. 
Dal tuo smartphone (iOS o Android), premi "Aggiungi alla schermata Home" dal menu di condivisione del browser per installare l'applicazione nativa (Progressive Web App).
