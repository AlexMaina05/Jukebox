import os
import shutil
import asyncio
import logging
import unicodedata
import re
from pathlib import Path

logger = logging.getLogger(__name__)

def make_safe_filename(name: str) -> str:
    # Rimuove accenti
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    # Sostituisce spazi e caratteri strani con underscore
    name = re.sub(r'[^a-zA-Z0-9]', '_', name)
    # Rimuove underscore multipli
    name = re.sub(r'_+', '_', name)
    return name.strip('_')

async def create_usb_export(query: str, music_dir: str, export_id: str) -> str:
    """
    Cerca i brani, li converte in MP3 192k sicuri, li zippa e ritorna il path dello zip.
    """
    def _process():
        base_export_dir = Path("temp_exports")
        base_export_dir.mkdir(exist_ok=True)
        
        task_dir = base_export_dir / export_id
        task_dir.mkdir(exist_ok=True)
        
        search_terms = query.lower().split()
        matched_files = []
        
        # 1. Trova i file
        for root, _, files in os.walk(music_dir):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg')):
                    full_path = os.path.join(root, file)
                    if all(term in full_path.lower() for term in search_terms):
                        matched_files.append(Path(full_path))
                        
        if not matched_files:
            shutil.rmtree(task_dir, ignore_errors=True)
            return None
            
        # Limita a max 50 brani per evitare blocchi infiniti
        matched_files = matched_files[:50]
        
        # 2. Converti e rinomina
        for i, fpath in enumerate(matched_files):
            safe_name = make_safe_filename(fpath.stem)
            out_name = f"{i+1:02d}_{safe_name}.mp3"
            out_path = task_dir / out_name
            
            # Usa ffmpeg per convertire forzatamente in mp3 192k (ideale per vecchie autoradio)
            cmd = [
                "ffmpeg", "-y", "-i", str(fpath),
                "-c:a", "libmp3lame", "-b:a", "192k",
                "-map_metadata", "0", "-id3v2_version", "3",
                str(out_path)
            ]
            import subprocess
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        # 3. Zippa la cartella
        zip_path = base_export_dir / f"{export_id}.zip"
        shutil.make_archive(str(base_export_dir / export_id), 'zip', str(task_dir))
        
        # Pulisci la cartella non zippata
        shutil.rmtree(task_dir, ignore_errors=True)
        
        return str(zip_path)

    return await asyncio.to_thread(_process)
