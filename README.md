# Jukebox - Media Request Portal & Navidrome Ingestor

Un potentissimo sistema All-In-One per la gestione, l'ingestione e la fruizione della tua libreria musicale su server Linux. Nasce per interfacciarsi con **Navidrome**, ma funge da coltellino svizzero per l'audiofilo e il data hoarder.

## 🚀 Caratteristiche Principali (Core)
* **Download Intelligente**: Scarica audio alla massima qualità configurabile da YouTube e Spotify.
* **Volume Normalization**: Usa `ffmpeg-normalize` (standard EBU R128 a -14 LUFS) per eliminare gli sbalzi di volume.
* **SponsorBlock**: Rimuove automaticamente introduzioni e parti non musicali dai video musicali YouTube.
* **Metadati & Tagging**: Integrazione profonda con **MusicBrainz** e **AcoustID** (tramite impronta acustica locale) per taggare automaticamente Titolo, Artista, Album e Anno.
* **Copertine HD**: Recupera e inietta nel file MP3/FLAC le copertine originali da *Cover Art Archive*.
* **Modalità DJ (Analisi Audio)**: Estrae il **BPM** e la **Chiave Musicale** elaborando localmente il segnale audio (tramite *librosa*).
* **Testi Karaoke (.lrc)**: Scarica testi sia statici (ID3) sia sincronizzati (.lrc) in stile Spotify/Apple Music tramite *LRCLIB*.
* **Disambiguazione Interattiva**: Quando un brano appartiene a più album, l'ingestione si ferma e chiede all'utente di selezionare l'album corretto via Web o Telegram (con anteprima audio!).
* **Auto-Deduplicatore (AcoustID)**: Il comando `/dedupe` scansiona l'intera libreria, calcola le impronte acustiche, identifica i brani doppi e cancella le versioni con qualità audio inferiore.
* **Supporto Intero Album**: Un comodo bottone ti permette di scaricare l'intero disco di un singolo brano con un click.

## 📱 Interfacce di Controllo

### 1. Web UI Progressiva (PWA)
Una dashboard mozzafiato in stile TailwindCSS (Glassmorphism + Dark Mode), installabile come App Nativa su smartphone (iOS/Android) grazie a Service Worker e Manifest.
* **Ricerca Live**: Digita il titolo e seleziona il risultato da una griglia a comparsa senza ricaricare la pagina.
* **WebSockets**: Barra in tempo reale che indica lo stato della coda e si aggiorna automaticamente.
* **Drag & Drop**: Trascina file MP3 locali sulla pagina web per farli elaborare, taggare automaticamente e inserire in Navidrome.
* **Audio Player Integrato**: Ascolta un frammento del file prima di taggarlo.
* **Esportatore USB (Old School)**: Cerca un artista nella libreria e il server creerà al volo un archivio `.zip` con i brani convertiti in MP3 192kbps (sicuri per le vecchie autoradio). I file temporanei si **auto-distruggono dopo 1 ora** per non intasare lo spazio sul disco. Il limite di sicurezza è impostato a 50 brani per esportazione.

### 2. Bot Telegram
Ideale per quando sei in giro. Invia link YouTube o Spotify e il server farà tutto da solo.
* Gestione di query testuali dirette.
* Notifiche di completamento.
* Generazione Vinili (vedi sotto).

### 3. Bot Discord Integrato (Streaming Diretto)
I tuoi amici possono entrare in un canale vocale Discord e usare i comandi (`!play`, `!stop`) per far suonare la *tua libreria privata Navidrome* in streaming ad altissima qualità direttamente dal tuo disco fisso, senza lag e senza pubblicità. Nessuna porta da aprire sul router!

### 4. Il "Vinile Digitale" (Printable PDF)
Con il comando `/printalbum Artista Album`, il server genera un PDF formattato per custodie di CD, con copertina in HD, tracklist e un **QR Code**. Stampa il PDF, inquadra il QR Code col telefono e la musica partirà istantaneamente.

## 🛠️ Stack Tecnologico
* **Backend**: Python 3.11, FastAPI (Asincrono), Uvicorn.
* **Code & State**: `asyncio.Queue` e Database SQLite (`aiosqlite`).
* **Frontend**: HTML5, TailwindCSS, Alpine.js, WebSockets.
* **Media Handling**: `yt-dlp`, `ffmpeg`, `mutagen`, `librosa`, `acoustid`, `qrcode`, `fpdf2`.
* **Container**: Immagine Docker ultraleggera basata su Debian (`python:3.11-slim`), che garantisce compatibilità immediata con le librerie scientifiche e i binari C precompilati (niente lunghissime build alpine!).

## 📖 Deployment
Per le istruzioni di installazione e deploy tramite Docker, fare riferimento al file `deployment_guide.md`.
