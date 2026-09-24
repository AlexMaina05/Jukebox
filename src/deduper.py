import os
import asyncio
import logging
from pathlib import Path
import acoustid
from mutagen import File

logger = logging.getLogger(__name__)

class Deduplicator:
    def __init__(self, music_dir: str | Path):
        self.music_dir = Path(music_dir)

    async def run_scan(self, progress_callback=None) -> dict:
        """
        Scandisce la directory musicale, calcola le impronte acustiche locali (senza API) 
        e rimuove i file duplicati mantenendo quello col bitrate maggiore.
        """
        def _scan():
            fingerprints = {}
            deleted = []
            failed = []
            
            audio_exts = {'.mp3', '.m4a', '.flac', '.wav', '.ogg'}
            files = []
            for root, _, filenames in os.walk(self.music_dir):
                for f in filenames:
                    p = Path(root) / f
                    if p.suffix.lower() in audio_exts:
                        files.append(p)
            
            total = len(files)
            for i, p in enumerate(files):
                # Chiama il callback ogni 10 file per aggiornare Telegram
                if progress_callback and i % 10 == 0:
                    # In thread separato non possiamo fare await, ma il callback passato
                    # potrebbe essere una funzione asincrona. Se lo è, meglio non chiamarlo da qui
                    # direttamente per evitare blocchi. Lasciamo stare il progress_callback in MVP sincrono
                    pass
                
                try:
                    duration, fp = acoustid.fingerprint_file(str(p))
                    # L'impronta base.
                    if fp not in fingerprints:
                        fingerprints[fp] = []
                    fingerprints[fp].append(p)
                except Exception as e:
                    logger.error(f"Errore fingerprint {p}: {e}")
                    failed.append(str(p))
            
            for fp, paths in fingerprints.items():
                if len(paths) > 1:
                    def get_bitrate(filepath):
                        try:
                            audio = File(filepath)
                            if audio and hasattr(audio.info, 'bitrate'):
                                return audio.info.bitrate
                            # Se non ha bitrate, usa la grandezza del file come fallback
                            return filepath.stat().st_size
                        except Exception:
                            return 0
                            
                    # Ordina dal migliore al peggiore
                    paths.sort(key=get_bitrate, reverse=True)
                    
                    best_file = paths[0]
                    for duplicate in paths[1:]:
                        try:
                            os.remove(duplicate)
                            deleted.append({
                                "kept": best_file.name,
                                "deleted": duplicate.name,
                                "deleted_path": str(duplicate)
                            })
                            logger.info(f"Deduplicator: Eliminato {duplicate} (Mantenuto {best_file})")
                        except Exception as e:
                            logger.error(f"Impossibile eliminare {duplicate}: {e}")
                            
            return {"scanned": total, "deleted": deleted, "failed": failed}

        return await asyncio.to_thread(_scan)
