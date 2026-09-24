import asyncio
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)

class SpotifyResolver:
    def __init__(self, client_id: str, client_secret: str):
        if client_id and client_secret:
            auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            self.enabled = True
        else:
            self.enabled = False

    def is_spotify_url(self, url: str) -> bool:
        return 'spotify.com' in url

    async def resolve(self, url: str) -> list[str]:
        """Restituisce una lista di query di ricerca (es. 'Artist - Title') dal link Spotify"""
        if not self.enabled:
            logger.warning("Spotify non configurato. Inserisci client_id e client_secret nel config.")
            return []

        def _fetch():
            queries = []
            try:
                if 'track' in url:
                    track = self.sp.track(url)
                    artist = track['artists'][0]['name']
                    queries.append(f"{artist} - {track['name']}")
                elif 'playlist' in url:
                    results = self.sp.playlist_tracks(url)
                    tracks = results['items']
                    while results['next']:
                        results = self.sp.next(results)
                        tracks.extend(results['items'])
                    for item in tracks:
                        track = item.get('track')
                        if track:
                            artist = track['artists'][0]['name']
                            queries.append(f"{artist} - {track['name']}")
                elif 'album' in url:
                    album = self.sp.album(url)
                    for track in album['tracks']['items']:
                        artist = track['artists'][0]['name']
                        queries.append(f"{artist} - {track['name']}")
            except Exception as e:
                logger.error(f"Errore nel parsing Spotify: {e}")
            return queries

        return await asyncio.to_thread(_fetch)
