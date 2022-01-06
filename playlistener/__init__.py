import re
import requests
import base64
import json
import time
from pathlib import Path
from typing import Iterator, Iterable, Tuple


SPOTIFY_TRACK_LINK_PATTERN = re.compile(r"https?://open\.spotify\.com/track/([0-9a-zA-Z]+)")
REDIRECT_URI = "http://localhost:8080/"

root = Path(__file__).absolute().parent


class SpotifyException(Exception):
    """Easily catch issues."""


class SpotifySession:
    """Wraps requests, caches authentication."""

    cache_path = root.joinpath("spotify.json")
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

        if "initial_token" in self.cache:
            self.handle_response(*self.authorization_code(self.cache["initial_token"]))
        else:
            self.handle_response(*self.refresh_token())

    def handle_response(self, now: float, response: requests.Response):
        """Handle a response from a token request."""

        if response.status_code != 200:
            print(response.content)
            raise SpotifyException("failed to authorize with Spotify!")

        self.cache = json.loads(response.content.decode())
        self.cache["time"] = now
        with self.cache_path.open("w") as file:
            json.dump(self.cache, file)

    def authorization_code(self, code: str) -> Tuple[float, requests.Response]:
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
        return now, response

    def refresh_token(self) -> Tuple[float, requests.Response]:
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

        return now, response

    @classmethod
    def generate_authentication_url(cls, client_id: str) -> str:
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
        yield f"spotify:track:{match.group()}"


def authorize_spotify(client_id: str, client_secret: str) -> str:
    """Synchronously authorize with the Spotify API."""

    authorization = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {authorization}",
        "Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers=headers,
        data={"grant_type": "client_credentials"})

    if response.status_code != 200:
        raise SpotifyException("failed to authorize with Spotify!")

    payload = json.loads(response.content.decode())
    return payload["access_token"]


def add_items_to_playlist(token: str, playlist: str, uris: Iterable[str]):
    """Add a series of tracks to a playlist."""

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"}

    response = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist}/tracks",
        headers=headers,
        json={"uris": uris})

    if response.status_code != 201:
        print(response.content)
        raise SpotifyException("failed to add items to playlist!")
