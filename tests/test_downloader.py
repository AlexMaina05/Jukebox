import pytest
from pathlib import Path
from unittest.mock import MagicMock
from src.downloader import AudioDownloader
import yt_dlp

@pytest.mark.asyncio
async def test_download_audio_success(mocker, tmp_path):
    # Setup mock per yt-dlp
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {
        'id': 'test_video_id',
        'title': 'Test Song',
        'ext': 'mp3'
    }
    
    # Mockiamo la classe YoutubeDL in yt_dlp
    mock_ytdl_class = mocker.patch('src.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl)
    
    downloader = AudioDownloader(output_dir=tmp_path)
    
    # Eseguiamo la funzione da testare
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result_path, video_title = await downloader.download(url)
    
    # Asserts
    mock_ytdl_class.assert_called_once()
    mock_ydl.extract_info.assert_called_once_with(url, download=True)
    
    # Deve ritornare un oggetto Path per interoperabilità tra SO
    assert isinstance(result_path, Path)
    # Il nome del file deve derivare dall'ID del video 
    assert result_path.name == "test_video_id.mp3"
    assert video_title == "Test Song"
    
@pytest.mark.asyncio
async def test_download_audio_failure(mocker, tmp_path):
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    # Simuliamo un errore di download
    mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Video not found")
    mocker.patch('src.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl)
    
    downloader = AudioDownloader(output_dir=tmp_path)
    
    with pytest.raises(Exception) as exc_info:
        await downloader.download("invalid_url")
        
    assert "Video not found" in str(exc_info.value)
