import asyncio
from pathlib import Path
import yt_dlp

class AudioDownloader:
    def __init__(self, output_dir: Path | str, audio_format: str = 'mp3', audio_quality: str = '320'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audio_format = audio_format
        self.audio_quality = str(audio_quality)

    async def download(self, url: str) -> tuple[Path, str]:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(self.output_dir / '%(id)s.%(ext)s'),
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.audio_format,
                    'preferredquality': self.audio_quality,
                }
            ],
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'source_address': '0.0.0.0', # Forza IPv4 per evitare blocchi IPv6 di YouTube
            'quiet': True,
            'no_warnings': True
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        info = await asyncio.to_thread(_download)
        
        file_path = self.output_dir / f"{info['id']}.{self.audio_format}"
        
        # Normalizzazione EBU R128
        def _normalize():
            from ffmpeg_normalize import FFmpegNormalize
            import os
            # Mappa il formato per specificare l'encoder a ffmpeg
            ext_to_codec = {
                'mp3': 'libmp3lame',
                'm4a': 'aac',
                'flac': 'flac',
                'wav': 'pcm_s16le'
            }
            codec = ext_to_codec.get(self.audio_format, 'libmp3lame')
            
            # Impostiamo target_level -14 LUFS (standard Spotify)
            normalizer = FFmpegNormalize(
                target_level=-14.0,
                audio_codec=codec,
                audio_bitrate=f"{self.audio_quality}k" if self.audio_format in ['mp3', 'm4a'] else None
            )
            
            temp_norm = self.output_dir / f"norm_{info['id']}.{self.audio_format}"
            normalizer.add_media_file(str(file_path), str(temp_norm))
            normalizer.run_normalization()
            
            # Sostituisci il file originale con quello normalizzato
            os.replace(str(temp_norm), str(file_path))

        try:
            await asyncio.to_thread(_normalize)
        except Exception as e:
            # Se la normalizzazione fallisce (es. formato strano), continuiamo col file originale
            print(f"Normalizzazione fallita per {file_path}: {e}")

        return file_path, info.get('title', '')
