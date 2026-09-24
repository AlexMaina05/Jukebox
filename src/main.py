import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
import shutil
import yaml

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from src.downloader import AudioDownloader
from src.queue_manager import DownloadQueue

# Load config
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Setup directories
MUSIC_DIR = Path(config['MUSIC_DIR'])
PICARD_DIR = MUSIC_DIR / "picard"
PICARD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = MUSIC_DIR / ".jukebox_temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config['TELEGRAM_TOKEN'], default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

downloader = AudioDownloader(output_dir=TEMP_DIR)
download_queue = DownloadQueue(concurrency=2)
templates = Jinja2Templates(directory="templates")

async def process_download_job(job: dict):
    url = job.get('url')
    chat_id = job.get('chat_id', 0)
    
    status_msg = None
    try:
        if chat_id != 0:
            title_hint = url.replace('ytsearch1:', '') if url and 'ytsearch1:' in url else 'link fornito'
            status_msg = await bot.send_message(chat_id, f"⬇️ Download di: <b>{title_hint}</b>...")
    except: pass
    
    try:
        logger.info(f"Downloading {url}")
        file_path, video_title = await downloader.download(url)
        
        # Pulisce il titolo dai caratteri non validi
        safe_title = "".join(c for c in video_title if c not in '<>:"/\\|?*')
        final_path = PICARD_DIR / f"{safe_title}{file_path.suffix}"
        
        shutil.move(str(file_path), str(final_path))
        logger.info(f"Salvato in {final_path}")
        
        if chat_id != 0:
            if status_msg:
                try: await status_msg.delete()
                except: pass
            await bot.send_message(chat_id, f"✅ Scaricato in Picard: <b>{safe_title}</b>")
            
    except Exception as e:
        logger.error(f"Errore: {e}")
        if chat_id != 0:
            if status_msg:
                try: await status_msg.edit_text(f"❌ Errore: {e}")
                except: pass
            else:
                await bot.send_message(chat_id, f"❌ Errore: {e}")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id not in config.get('ALLOWED_USERS', []):
        return
    await message.answer("Ciao! Invia un link YouTube per scaricarlo direttamente in /music/picard.")

@dp.message(F.text)
async def handle_text(message: Message):
    if message.from_user.id not in config.get('ALLOWED_USERS', []):
        return
    
    url = message.text.strip()
    if not url.startswith("http"):
        await download_queue.add_job({"url": f"ytsearch1:{url}", "chat_id": message.chat.id})
        return
        
    import yt_dlp
    opts = {'extract_flat': 'in_playlist', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                await message.reply(f"Accodate {len(info['entries'])} tracce dalla playlist.")
                for entry in info['entries']:
                    vu = entry.get('url')
                    if vu and not vu.startswith('http'):
                        vu = f"https://www.youtube.com/watch?v={entry.get('id')}"
                    if vu:
                        await download_queue.add_job({"url": vu, "chat_id": message.chat.id})
            else:
                await download_queue.add_job({"url": url, "chat_id": message.chat.id})
                await message.reply("Brano accodato per il download.")
    except Exception as e:
        await message.reply(f"Errore yt-dlp: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await download_queue.start(process_download_job)
    asyncio.create_task(dp.start_polling(bot))
    yield
    await download_queue.stop()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit")
async def submit_url(url: str = Form(...)):
    url = url.strip()
    if not url.startswith("http"):
        await download_queue.add_job({"url": f"ytsearch1:{url}", "chat_id": 0})
        return RedirectResponse(url="/", status_code=303)
        
    import yt_dlp
    opts = {'extract_flat': 'in_playlist', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    vu = entry.get('url')
                    if vu and not vu.startswith('http'):
                        vu = f"https://www.youtube.com/watch?v={entry.get('id')}"
                    if vu:
                        await download_queue.add_job({"url": vu, "chat_id": 0})
            else:
                await download_queue.add_job({"url": url, "chat_id": 0})
    except:
        pass
    return RedirectResponse(url="/", status_code=303)
