import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import yaml
from pathlib import Path
import yt_dlp
import uuid

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from src.downloader import AudioDownloader
from src.tagger import AudioTagger
from src.navidrome_api import NavidromeClient
from src.queue_manager import DownloadQueue
from src.db import init_db, save_pending_choice, get_pending_choice, delete_pending_choice, get_all_pending_choices

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
config_path = Path("config.yaml")
if config_path.exists():
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
else:
    config = {}

TELEGRAM_TOKEN = config.get("telegram", {}).get("bot_token", "")
ALLOWED_USERS = config.get("telegram", {}).get("allowed_users", [])
WEBHOOK_URL = config.get("telegram", {}).get("webhook_url", "")
WEBHOOK_PATH = config.get("telegram", {}).get("webhook_path", "/webhook")

APP_CONFIG = config.get("app", {})
MUSIC_DIR = APP_CONFIG.get("music_dir", "./musica")
AUDIO_FORMAT = APP_CONFIG.get("audio_format", "mp3")
AUDIO_QUALITY = APP_CONFIG.get("audio_quality", "320")

DISCORD_TOKEN = config.get("discord", {}).get("bot_token", "")
from src.discord_bot import setup_discord_bot
discord_client = setup_discord_bot(DISCORD_TOKEN, MUSIC_DIR)
discord_task = None

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
download_queue = DownloadQueue(concurrency=2)

TEMP_DOWNLOAD_DIR = Path(MUSIC_DIR) / ".jukebox_temp"
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
downloader = AudioDownloader(output_dir=TEMP_DOWNLOAD_DIR, audio_format=AUDIO_FORMAT, audio_quality=AUDIO_QUALITY)
tagger = AudioTagger(music_dir=MUSIC_DIR, acoustid_key=config.get("acoustid", {}).get("api_key", ""))
navidrome_client = NavidromeClient(
    base_url=config.get("navidrome", {}).get("url", ""),
    username=config.get("navidrome", {}).get("username", ""),
    password=config.get("navidrome", {}).get("password", "")
)


async def process_download_job(job: dict):
    url = job.get('url')
    chat_id = job.get('chat_id', 0)
    is_local = job.get('is_local', False)
    local_path = job.get('local_path')
    
    # Invia messaggio di stato su Telegram se applicabile
    status_msg = None
    try:
        if chat_id != 0:
            title_hint = url.replace('ytsearch1:', '') if url and 'ytsearch1:' in url else 'link fornito'
            if is_local:
                title_hint = 'file locale'
            status_msg = await bot.send_message(chat_id, f"⬇️ Inizio elaborazione per: *{title_hint}*...", parse_mode="Markdown")
    except Exception:
        pass
    
    try:
        if is_local:
            logger.info(f"Elaborazione file locale: {local_path}")
            file_path = Path(local_path)
            video_title = file_path.stem
        else:
            logger.info(f"Downloading {url}")
            file_path, video_title = await downloader.download(url)
            
            # Aggiorna il messaggio
            if status_msg:
                try:
                    await status_msg.edit_text(f"🔍 Ricerca metadati per: *{video_title}*...", parse_mode="Markdown")
                except Exception:
                    pass
            
        logger.info(f"Ricerca metadati per: {video_title}")
        meta = await tagger.get_metadata(file_path, query=video_title)
        
        releases = meta['releases']
        if not releases:
            await tagger.apply_tag_and_move(file_path, meta['title'], meta['artist'], None)
            await navidrome_client.start_scan()
            if chat_id != 0:
                await bot.send_message(chat_id, f"✅ Brano disponibile! ({meta['title']} - metadati parziali)")
            return
            
        if len(releases) == 1:
            await tagger.apply_tag_and_move(file_path, meta['title'], meta['artist'], releases[0])
            await navidrome_client.start_scan()
            if chat_id != 0:
                rel_id = releases[0].get('id')
                kb = None
                if rel_id:
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💿 Scarica intero album", callback_data=f"alb_{rel_id}")]])
                await bot.send_message(chat_id, f"✅ Brano disponibile! ({meta['title']})", reply_markup=kb)
        else:
            task_id = str(uuid.uuid4())[:8]
            job_data = {
                "file_path": str(file_path),
                "title": meta['title'],
                "artist": meta['artist'],
                "releases": releases[:5],
                "chat_id": chat_id
            }
            await save_pending_choice(task_id, job_data)
            
            if chat_id != 0:
                buttons = []
                for i, rel in enumerate(releases[:5]):
                    album_title = rel.get('title', 'Unknown')
                    buttons.append([InlineKeyboardButton(text=album_title, callback_data=f"tag_{task_id}_{i}")])
                    
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await bot.send_message(chat_id, f"🎵 *{meta['title']}* di *{meta['artist']}*\nHo trovato più album. Scegli:", reply_markup=kb)

    except Exception as e:
        logger.error(f"Errore durante l'elaborazione di {url or local_path}: {e}")
        if chat_id != 0:
            await bot.send_message(chat_id, f"❌ Errore durante il download: {e}")

@dp.callback_query(F.data.startswith("tag_"))
async def handle_tag_choice(callback: types.CallbackQuery):
    _, task_id, idx = callback.data.split("_")
    idx = int(idx)
    
    job = await get_pending_choice(task_id)
    if not job:
        await callback.answer("Richiesta scaduta o file non più disponibile.", show_alert=True)
        return
        
    release = job['releases'][idx]
    await callback.message.edit_text(f"⏳ Applicazione tag dall'album '{release.get('title')}' in corso...")
    
    try:
        final_title = release.get('rec_title', job['title'])
        final_artist = release.get('rec_artist', job['artist'])
        await tagger.apply_tag_and_move(job['file_path'], final_title, final_artist, release)
        await navidrome_client.start_scan()
        
        rel_id = release.get('id')
        kb = None
        if rel_id:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💿 Scarica intero album", callback_data=f"alb_{rel_id}")]])
            
        await callback.message.edit_text(f"✅ Brano disponibile in Navidrome!\n🎵 {job['title']} - {release.get('title')}", reply_markup=kb)
    except Exception as e:
        await callback.message.edit_text(f"❌ Errore durante il salvataggio: {e}")
        
    await delete_pending_choice(task_id)

@dp.callback_query(F.data.startswith("alb_"))
async def handle_album_download(callback: types.CallbackQuery):
    release_id = callback.data.split("_")[1]
    await callback.message.edit_text(f"{callback.message.text}\n\n⏳ Ricerca delle tracce dell'album in corso...")
    
    tracks = await tagger.get_album_tracks(release_id)
    if not tracks:
        await callback.message.edit_text(f"{callback.message.text}\n❌ Impossibile recuperare la tracklist dell'album.")
        return
        
    await callback.message.edit_text(f"{callback.message.text}\n✅ Trovate {len(tracks)} tracce. Accodamento in corso...")
    for track_query in tracks:
        await download_queue.add_job({"url": f"ytsearch1:{track_query}", "chat_id": callback.message.chat.id})

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    await message.answer("Ciao! Invia un link YouTube o Spotify per scaricare il brano su Navidrome.\nUsa /dedupe per scansionare e rimuovere i duplicati.")

from src.deduper import Deduplicator
deduper = Deduplicator(music_dir=MUSIC_DIR)

@dp.message(Command("dedupe"))
async def cmd_dedupe(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
        
    await message.answer("🔍 Avvio scansione anti-duplicati con AcoustID in corso...\nQuesto processo analizzerà l'impronta sonora di tutti i file e potrebbe richiedere diversi minuti.")
    
    try:
        results = await deduper.run_scan()
        deleted_count = len(results['deleted'])
        
        if deleted_count > 0:
            msg = f"🧹 **Scansione completata!**\nFile analizzati: {results['scanned']}\nDuplicati eliminati: {deleted_count}\n\n"
            for item in results['deleted'][:10]:
                msg += f"🗑️ Eliminato: {item['deleted']}\n(Mantenuto: {item['kept']})\n\n"
            if deleted_count > 10:
                msg += f"...e altri {deleted_count - 10} file."
            await navidrome_client.start_scan()
        else:
            msg = f"✨ **Scansione completata!**\nFile analizzati: {results['scanned']}\nNon è stato trovato alcun duplicato."
            
        await message.answer(msg)
    except Exception as e:
        await message.answer(f"❌ Errore durante la deduplicazione: {e}")

from src.pdf_generator import create_vinyl_pdf
from aiogram.types import FSInputFile

@dp.message(Command("printalbum"))
async def cmd_printalbum(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    query = message.text.replace("/printalbum", "").strip()
    if not query:
        await message.answer("❌ Usa: /printalbum Artista Album")
        return
        
    await message.answer(f"🖨️ Generazione Vinile Digitale per '{query}'...")
    try:
        # Trova metadati base (primo release)
        meta = await tagger.get_metadata("dummy", query=query)
        if not meta['releases']:
            await message.answer("❌ Impossibile trovare l'album su MusicBrainz.")
            return
        release = meta['releases'][0]
        tracks = await tagger.get_album_tracks(release['id'])
        
        import httpx
        cover_path = "temp_cover.jpg"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(f"https://coverartarchive.org/release/{release['id']}/front", timeout=10.0)
            if resp.status_code == 200:
                with open(cover_path, "wb") as f:
                    f.write(resp.content)
            else:
                cover_path = None
                
        output_pdf = f"Vinyl_{meta['artist']}_{meta['title']}.pdf".replace(" ", "_")
        nav_url = config.get("navidrome", {}).get("url", "")
        
        success = await asyncio.to_thread(
            create_vinyl_pdf, 
            meta['artist'], 
            release.get('title', meta['title']), 
            cover_path, 
            tracks, 
            nav_url, 
            output_pdf
        )
        
        if success:
            doc = FSInputFile(output_pdf)
            await message.answer_document(doc, caption="💽 Ecco il tuo Vinile Digitale! Stampa questo PDF su un foglio A4, ritaglia le due facciate e piegale a metà per inserirle nella custodia in plastica. Il QR code farà partire l'album.")
            os.remove(output_pdf)
        else:
            await message.answer("❌ Errore durante la creazione del PDF.")
            
        if cover_path and os.path.exists(cover_path):
            os.remove(cover_path)
            
    except Exception as e:
        await message.answer(f"❌ Errore: {e}")

@dp.message()
async def handle_url(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
        
    url = message.text.strip()
    if not url.startswith("http"):
        # Se non è un link, assumiamo sia una ricerca testuale
        await download_queue.add_job({"url": f"ytsearch1:{url}", "chat_id": message.chat.id})
        return

    def _extract_urls():
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
            
    try:
        info = await asyncio.to_thread(_extract_urls)
    except Exception:
        return

    if info and 'entries' in info:
        entries = list(info['entries'])
        await message.answer(f"⏳ Playlist rilevata! Accodo {len(entries)} brani...")
        for entry in entries:
            video_url = entry.get('url')
            if video_url and not video_url.startswith('http'):
                video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
            if video_url:
                await download_queue.add_job({"url": video_url, "chat_id": message.chat.id})
    else:
        await download_queue.add_job({"url": url, "chat_id": message.chat.id})

@asynccontextmanager
async def lifespan(app: FastAPI):
    global discord_task
    logger.info("Avvio code asincrone e database...")
    await init_db()
    await download_queue.start(process_download_job)
    
    # Websocket broadcaster
    ws_task = asyncio.create_task(broadcast_state())
    
    if discord_client:
        logger.info("Avvio demone Discord...")
        discord_task = asyncio.create_task(discord_client.start(DISCORD_TOKEN))
        
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
    else:
        asyncio.create_task(dp.start_polling(bot))
        
    yield
    
    if discord_task:
        await discord_client.close()
        discord_task.cancel()
        
    await download_queue.stop()
    if WEBHOOK_URL:
        await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

if WEBHOOK_URL:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiogram.types import Update

    @app.post(WEBHOOK_PATH)
    async def bot_webhook(request: Request):
        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}

from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi import Form, Query, UploadFile, File, WebSocket, WebSocketDisconnect
import shutil
import json

import os
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- WebSocket State ---
active_connections: list[WebSocket] = []

async def broadcast_state():
    while True:
        if active_connections:
            state = {
                "queue_size": download_queue.queue.qsize(),
                "pending_count": len(await get_all_pending_choices())
            }
            state_str = json.dumps(state)
            dead_connections = []
            for ws in active_connections:
                try:
                    await ws.send_text(state_str)
                except:
                    dead_connections.append(ws)
            for ws in dead_connections:
                active_connections.remove(ws)
        await asyncio.sleep(2)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.api_route("/health", methods=["GET", "HEAD"])
def healthcheck():
    return {"status": "healthy"}

@app.get("/stream/{task_id}")
async def stream_audio(task_id: str):
    job = await get_pending_choice(task_id)
    if not job or not Path(job['file_path']).exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(job['file_path'])

@app.get("/manifest.json")
async def get_manifest():
    manifest = {
        "name": "Jukebox Portal",
        "short_name": "Jukebox",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#121212",
        "theme_color": "#1DB954",
        "icons": [
            {
                "src": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Vinyl_record.svg/512px-Vinyl_record.svg.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return JSONResponse(manifest)

from fastapi.responses import Response

@app.get("/sw.js")
async def get_service_worker():
    sw_code = """
    const CACHE_NAME = 'jukebox-cache-v1';
    const urlsToCache = ['/'];
    
    self.addEventListener('install', event => {
        event.waitUntil(
            caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
        );
    });
    
    self.addEventListener('fetch', event => {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
    });
    """
    return Response(content=sw_code, media_type="application/javascript")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / file.filename
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    await download_queue.add_job({
        "is_local": True,
        "local_path": str(temp_path),
        "chat_id": 0
    })
    return RedirectResponse(url="/", status_code=303)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    pending_choices = await get_all_pending_choices()
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "request": request, 
            "queue_size": download_queue.queue.qsize(),
            "pending_choices": pending_choices
        }
    )

@app.post("/resolve_tag/{task_id}")
async def resolve_tag_web(task_id: str, release_idx: int = Form(...)):
    job = await get_pending_choice(task_id)
    if not job:
        return RedirectResponse(url="/", status_code=303)
    
    release = job['releases'][release_idx]
    try:
        final_title = release.get('rec_title', job['title'])
        final_artist = release.get('rec_artist', job['artist'])
        await tagger.apply_tag_and_move(job['file_path'], final_title, final_artist, release)
        await navidrome_client.start_scan()
        if job['chat_id'] != 0:
            await bot.send_message(job['chat_id'], f"✅ Brano disponibile in Navidrome!\n🎵 {job['title']} - {release.get('title')}")
    except Exception as e:
        logger.error(f"Errore durante tag web per {task_id}: {e}")
        
    await delete_pending_choice(task_id)
    return RedirectResponse(url="/", status_code=303)

from fastapi import Query
from fastapi.responses import JSONResponse

@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=2)):
    def _search():
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Ritorna i primi 5 risultati
            return ydl.extract_info(f"ytsearch5:{q}", download=False)
            
    try:
        info = await asyncio.to_thread(_search)
        results = []
        if info and 'entries' in info:
            for entry in info['entries']:
                url = entry.get('url')
                if not url.startswith('http'):
                    url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                results.append({
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                    "uploader": entry.get("uploader"),
                    "duration": entry.get("duration"),
                    "thumbnail": entry.get("thumbnails", [{}])[-1].get("url") if entry.get("thumbnails") else None,
                    "url": url
                })
        return JSONResponse({"results": results})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/submit")
async def submit_url(url: str = Form(...)):
    url = url.strip()
    if not url.startswith("http"):
        await download_queue.add_job({"url": f"ytsearch1:{url}", "chat_id": 0})
        return RedirectResponse(url="/", status_code=303)
        
    def _extract():
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'noplaylist': True}) as ydl:
            return ydl.extract_info(url, download=False)
    try:
        info = await asyncio.to_thread(_extract)
        if info and 'entries' in info:
            for entry in info['entries']:
                vu = entry.get('url')
                if vu and not vu.startswith('http'):
                    vu = f"https://www.youtube.com/watch?v={entry.get('id')}"
                if vu:
                    await download_queue.add_job({"url": vu, "chat_id": 0})
        else:
            await download_queue.add_job({"url": url, "chat_id": 0})
    except Exception:
        pass
    return RedirectResponse(url="/", status_code=303)

import glob

@app.get("/api/library")
async def get_local_library(limit: int = 50):
    try:
        files = []
        for ext in ('*.mp3', '*.flac', '*.m4a'):
            found = glob.glob(os.path.join(MUSIC_DIR, "**", ext), recursive=True)
            files.extend([f for f in found if ".jukebox_temp" not in f])
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        results = []
        for f in files[:limit]:
            rel_path = os.path.relpath(f, MUSIC_DIR)
            parts = rel_path.split(os.sep)
            
            artist = parts[0] if len(parts) > 1 else "Sconosciuto"
            title = os.path.splitext(os.path.basename(f))[0]
            
            results.append({
                "path": rel_path,
                "artist": artist,
                "title": title,
                "added_at": os.path.getmtime(f)
            })
        return {"status": "ok", "files": results}
    except Exception as e:
        logger.error(f"Errore lettura libreria: {e}")
        return {"status": "error", "files": []}

# --- USB EXPORTER ---
from src.exporter import create_usb_export
import uuid

export_jobs = {}

async def cleanup_export(export_id: str, zip_path: str, delay_seconds: int = 3600):
    await asyncio.sleep(delay_seconds)
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if export_id in export_jobs:
            del export_jobs[export_id]
        logger.info(f"Pulizia automatica completata per export: {export_id}")
    except Exception as e:
        logger.error(f"Errore durante pulizia export {export_id}: {e}")

@app.post("/api/export")
async def start_export(q: str = Form(...)):
    export_id = str(uuid.uuid4())
    export_jobs[export_id] = {"status": "processing"}
    
    async def _run_export():
        try:
            zip_path = await create_usb_export(q, MUSIC_DIR, export_id)
            if zip_path:
                export_jobs[export_id] = {"status": "done", "file": zip_path}
                # Lancia la pulizia asincrona (1 ora = 3600 secondi)
                asyncio.create_task(cleanup_export(export_id, zip_path, 3600))
            else:
                export_jobs[export_id] = {"status": "error"}
        except Exception as e:
            export_jobs[export_id] = {"status": "error"}
            
    asyncio.create_task(_run_export())
    return JSONResponse({"export_id": export_id})

@app.get("/api/export/status/{export_id}")
async def check_export_status(export_id: str):
    job = export_jobs.get(export_id)
    if not job:
        return JSONResponse({"status": "not_found"})
    return JSONResponse(job)

@app.get("/download_export/{export_id}")
async def download_export(export_id: str):
    job = export_jobs.get(export_id)
    if not job or job['status'] != 'done':
        return JSONResponse({"error": "File non trovato o non pronto"}, status_code=404)
    return FileResponse(job['file'], media_type='application/zip', filename=f"Jukebox_Export_{export_id[:6]}.zip")
