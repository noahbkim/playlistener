import re
import requests
import base64
import json
import time
from pathlib import Path
from typing import Iterator, Iterable

__all__ = (
    "SpotifyException",
    "SpotifySession",
    "find_spotify_track_links",
    "generate_authentication_url")


SPOTIFY_TRACK_LINK_PATTERN = re.compile(r"https?://open\.spotify\.com/track/([0-9a-zA-Z]+)")
REDIRECT_URI = "http://localhost:8080/"

parent = Path(__file__).absolute().parent.parent


class SpotifyException(Exception):
    """Easily catch issues."""


class SpotifySession:
    """Wraps requests, caches authentication."""

    cache_path = parent.joinpath("spotify.json")
    client_id: str
    client_secret: str
    cache: dict

    def __init__(self, client_id: str, client_secret: str):
        """Do initial authentication."""

        self.client_id = client_id
        self.client_secret = client_secret

        try:
            with self.cache_path.open() as file:
                self.cache = json.load(file)
        except (FileNotFoundError, ValueError):
            raise SpotifyException("cannot find session file to bootstrap!")

        if "initial_code" in self.cache:
            self.authorization_code(self.cache["initial_code"])
        else:
            self.refresh_token()

    def handle_response(self, now: float, response: requests.Response):
        """Handle a response from a token request."""

        if response.status_code != 200:
            print(response.content)
            raise SpotifyException("failed to authorize with Spotify!")

        old_refresh_token = self.cache["refresh_token"]
        self.cache = json.loads(response.content.decode())
        self.cache["refresh_token"] = old_refresh_token
        self.cache["time"] = now
        with self.cache_path.open("w") as file:
            json.dump(self.cache, file, indent=2)

    def authorization_code(self, code: str):
        """Request an access token with user privileges."""

        authorization = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI}

        now = time.time()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=headers,
            data=data)

        self.handle_response(now, response)

    def refresh_token(self):
        """Use our existing refresh token to get a new one."""

        authorization = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.cache["refresh_token"]}

        now = time.time()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=headers,
            data=data)

        self.handle_response(now, response)

    def is_token_expired(self) -> bool:
        """Check if the cached token is past expiry."""

        return time.time() >= self.cache["time"] + self.cache["expires_in"]

    def add_items_to_playlist(self, playlist: str, uris: Iterable[str]):
        """Add a series of tracks to a playlist."""

        if self.is_token_expired():
            self.refresh_token()

        headers = {
            "Authorization": f"""Bearer {self.cache["access_token"]}""",
            "Content-Type": "application/json"}

        response = requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist}/tracks",
            headers=headers,
            json={"uris": uris})

        if response.status_code != 201:
            print(response.content)
            raise SpotifyException("failed to add items to playlist!")


def generate_authentication_url(client_id: str) -> str:
    """Used to manually acquire the user code."""

    return (
        f"https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&scope=playlist-modify-public"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state=abcdef0123456789")


def find_spotify_track_links(message: str) -> Iterator[str]:
    """Find all Spotify song links."""

    for match in SPOTIFY_TRACK_LINK_PATTERN.finditer(message):
        yield f"spotify:track:{match.group(1)}"
