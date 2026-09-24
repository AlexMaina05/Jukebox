import asyncio
import shutil
import re
import logging
from pathlib import Path
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, error

logger = logging.getLogger(__name__)
import httpx
import acoustid

# Configurazione user-agent richiesta da MusicBrainz
musicbrainzngs.set_useragent(
    "MediaRequestPortal",
    "0.1",
    "https://github.com/example/media_portal"
)

def sanitize_filename(name: str) -> str:
    if not name:
        return "Unknown"
    return re.sub(r'[<>:"/\\|?*]', '_', name)

class AudioTagger:
    def __init__(self, music_dir: Path | str, acoustid_key: str = ""):
        self.music_dir = Path(music_dir)
        self.acoustid_key = acoustid_key

    async def get_metadata(self, file_path: Path | str, query: str) -> dict:
        file_path = Path(file_path)
        
        def _search():
            mb_query = query
            if self.acoustid_key:
                try:
                    results = acoustid.match(self.acoustid_key, str(file_path))
                    for score, record_id, title, artist in results:
                        if score > 0.5:
                            # Usa AcoustID per trovare il nome vero, poi cerca il brano canonico!
                            mb_query = f"{title} {artist}"
                            break
                except Exception:
                    pass
            return musicbrainzngs.search_recordings(query=mb_query, limit=3)
            
        result = await asyncio.to_thread(_search)
        
        title = file_path.stem
        artist = 'Unknown Artist'
        releases = []

        if result.get('recording-list'):
            recording = result['recording-list'][0]
            title = recording.get('title', title)
            if recording.get('artist-credit'):
                artist = recording['artist-credit'][0].get('artist', {}).get('name', 'Unknown Artist')
            
            # Combina gli album dei top 3 risultati per offrire più scelta
            for rec in result['recording-list']:
                rels = rec.get('release-list') or rec.get('releases') or []
                for r in rels:
                    if not any(existing['id'] == r['id'] for existing in releases):
                        releases.append(r)
        elif 'recording' in result:
            recording = result['recording']
            title = recording.get('title', title)
            if recording.get('artist-credit'):
                artist = recording['artist-credit'][0].get('artist', {}).get('name', 'Unknown Artist')
            releases = recording.get('release-list') or recording.get('releases') or []

        return {
            "title": title,
            "artist": artist,
            "releases": releases
        }
        
    async def get_album_tracks(self, release_id: str) -> list[str]:
        def _get():
            try:
                release = musicbrainzngs.get_release_by_id(release_id, includes=['recordings', 'artists'])
                tracks = []
                for medium in release.get('release', {}).get('medium-list', []):
                    for track in medium.get('track-list', []):
                        rec = track.get('recording', {})
                        t_title = rec.get('title')
                        if t_title:
                            # prendiamo il nome dell'artista della release
                            a_name = "Unknown"
                            acredit = release['release'].get('artist-credit')
                            if acredit:
                                a_name = acredit[0].get('artist', {}).get('name', 'Unknown')
                            tracks.append(f"{a_name} - {t_title}")
                return tracks
            except Exception:
                return []
        return await asyncio.to_thread(_get)

    async def apply_tag_and_move(self, file_path: Path | str, title: str, artist: str, release: dict = None) -> Path:
        file_path = Path(file_path)
        album = 'Unknown Album'
        release_id = None
        
        if release:
            album = release.get('title', 'Unknown Album')
            release_id = release.get('id')
            
        cover_data = None
        date = None
        if release:
            date = release.get('date')
            
        if release_id:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(f"https://coverartarchive.org/release/{release_id}/front", timeout=10.0)
                    if resp.status_code == 200:
                        cover_data = resp.content
            except Exception:
                pass
                
        lyrics = None
        synced_lyrics = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                l_resp = await client.get(
                    "https://lrclib.net/api/get",
                    params={"artist_name": artist, "track_name": title, "album_name": album}
                )
                if l_resp.status_code == 200:
                    data = l_resp.json()
                    lyrics = data.get('plainLyrics')
                    synced_lyrics = data.get('syncedLyrics')
        except Exception:
            pass

        def _tag_and_move():
            from mutagen import File
            audio = File(str(file_path), easy=True)
            if audio is None:
                raise Exception("Formato audio non supportato per i tag")
            if audio.tags is None:
                audio.add_tags()
                
            audio.tags['title'] = title
            audio.tags['artist'] = artist
            audio.tags['album'] = album
            if date:
                audio.tags['date'] = date
            audio.save()

            # Analisi Audio per DJ Mode (BPM e Chiave)
            bpm_str = None
            key_str = None
            try:
                import librosa
                import numpy as np
                import warnings
                warnings.filterwarnings('ignore')
                
                logger.info(f"Avvio analisi DJ (BPM/Key) per {file_path}...")
                y, sr = librosa.load(str(file_path), sr=None, duration=120) # Analizza primi 2 min
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm = round(tempo[0]) if isinstance(tempo, np.ndarray) else round(tempo)
                bpm_str = str(bpm)
                
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                chroma_sum = np.sum(chroma, axis=1)
                
                pitches = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                maj_p = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
                min_p = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
                
                best_corr = -2.0
                for i in range(12):
                    maj_c = np.corrcoef(chroma_sum, np.roll(maj_p, i))[0, 1]
                    if maj_c > best_corr:
                        best_corr = maj_c
                        key_str = pitches[i] + "m" if False else pitches[i] # Hack per non fare if-else
                    min_c = np.corrcoef(chroma_sum, np.roll(min_p, i))[0, 1]
                    if min_c > best_corr:
                        best_corr = min_c
                        key_str = pitches[i] + "m"
                
                # Sostituisci i nomi delle chiavi standard con notazione (es. C, Cm)
                if key_str.endswith('m'):
                    pass # già corretto
            except Exception as e:
                logger.error(f"Errore nell'analisi DJ: {e}")

            if file_path.suffix.lower() == '.mp3':
                try:
                    audio_tags = ID3(str(file_path))
                    if cover_data:
                        audio_tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
                    from mutagen.id3 import USLT, TBPM, TKEY
                    if lyrics:
                        audio_tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics))
                    if bpm_str:
                        audio_tags.add(TBPM(encoding=3, text=bpm_str))
                    if key_str:
                        audio_tags.add(TKEY(encoding=3, text=key_str))
                    audio_tags.save(v2_version=3)
                except error:
                    pass

            safe_artist = sanitize_filename(artist)
            safe_album = sanitize_filename(album)
            safe_title = sanitize_filename(title)
            
            target_dir = self.music_dir / safe_artist / safe_album
            target_dir.mkdir(parents=True, exist_ok=True)
            
            new_file_path = target_dir / f"{safe_title}{file_path.suffix}"
            shutil.move(str(file_path), str(new_file_path))
            
            # Salva i testi sincronizzati per il Karaoke (.lrc)
            if synced_lyrics:
                lrc_path = new_file_path.with_suffix('.lrc')
                try:
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(synced_lyrics)
                    logger.info(f"Testi sincronizzati (.lrc) salvati per {safe_title}")
                except Exception as e:
                    logger.error(f"Errore salvataggio .lrc: {e}")
                    
            return new_file_path

        return await asyncio.to_thread(_tag_and_move)
