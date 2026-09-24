import pytest
from pathlib import Path
from unittest.mock import MagicMock
from src.tagger import AudioTagger

@pytest.fixture
def mock_audio_file(tmp_path):
    # Crea un file mp3 fittizio
    file_path = tmp_path / "test.mp3"
    file_path.write_bytes(b"dummy audio content")
    return file_path

@pytest.mark.asyncio
async def test_tag_audio_success(mock_audio_file, mocker):
    # Mockiamo mutagen (EasyID3) per evitare di modificare un file fittizio
    mock_id3 = MagicMock()
    # Supporto dictionary assignment in MagicMock (mock_id3['title'] = ...)
    mock_id3.__setitem__ = MagicMock()
    mocker.patch('src.tagger.EasyID3', return_value=mock_id3)
    
    # Mockiamo musicbrainzngs
    mock_mb = mocker.patch('src.tagger.musicbrainzngs')
    # Simuliamo il ritorno di una ricerca API
    mock_mb.search_recordings.return_value = {
        'recording-list': [{
            'title': 'Bohemian Rhapsody',
            'artist-credit': [{'artist': {'name': 'Queen'}}],
            'release-list': [{'title': 'A Night at the Opera'}]
        }]
    }

    # Mockiamo shutil.move per evitare spostamenti reali
    mock_move = mocker.patch('src.tagger.shutil.move')

    tagger = AudioTagger(music_dir=mock_audio_file.parent)
    
    # Eseguiamo i nuovi metodi
    meta = await tagger.get_metadata(mock_audio_file, query="Queen Bohemian Rhapsody")
    final_path = await tagger.apply_tag_and_move(mock_audio_file, meta['title'], meta['artist'], meta['releases'][0])

    # Verifiche chiamata API
    mock_mb.search_recordings.assert_called_once_with(query="Queen Bohemian Rhapsody", limit=1)
    
    # Verifichiamo che i tag siano stati assegnati all'oggetto mutagen
    mock_id3.__setitem__.assert_any_call('title', 'Bohemian Rhapsody')
    mock_id3.__setitem__.assert_any_call('artist', 'Queen')
    mock_id3.__setitem__.assert_any_call('album', 'A Night at the Opera')
    
    # Verifica salvataggio file e spostamento
    mock_id3.save.assert_called_once()
    mock_move.assert_called_once()
    assert final_path.name == "Bohemian Rhapsody.mp3"
    assert "Queen" in str(final_path.parent.parent)
