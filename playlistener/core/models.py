from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings

import requests
import base64
from typing import Callable, Iterable, Optional

__all__ = (
    "Invitation",
    "SpotifyException",
    "SpotifySemanticError",
    "SpotifyRuntimeError",
    "NoQueueSpotifyException",
    "InvalidPlaylistSpotifyException",
    "SpotifyAuthorization",
    "TwitchIntegration",
    "TwitchIntegrationUser",)


class Invitation(models.Model):
    """Allow a user to create an account on the server."""

    username = models.CharField(max_length=150, unique=True)
    administrator = models.BooleanField(default=False)

    time_created = models.DateTimeField(default=timezone.now)


class SpotifyException(Exception):
    """Thrown on unrecoverable Spotify errors."""

    def __init__(self, reason: str, details: str = None):
        """Store details in addition to reason."""

        super().__init__(reason)
        self.details = details


class SpotifySemanticError(SpotifyException):
    """User-caused error."""


class SpotifyRuntimeError(SpotifyException):
    """Issue with API access."""


class NoQueueSpotifyException(SpotifyException):
    """Thrown when a track can't be added to queue."""


class InvalidPlaylistSpotifyException(SpotifyException):
    """Thrown specifically on 404 from accessing playlist."""


class SpotifyAuthorization(models.Model):
    """Contains API keys for Spotify use."""

    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="spotify")

    access_token = models.CharField(max_length=250)
    refresh_token = models.CharField(max_length=250)

    token_type = models.CharField(max_length=50)
    expires_in = models.PositiveSmallIntegerField()
    scope = models.CharField(max_length=250)

    time_created = models.DateTimeField(default=timezone.now)
    time_modified = models.DateTimeField(auto_now=True)
    time_refreshed = models.DateTimeField(default=timezone.now)

    CLIENT_TOKEN_DATA = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    CLIENT_TOKEN = base64.b64encode(CLIENT_TOKEN_DATA.encode()).decode()

    def request(self, code: str):
        """Create a Spotify authorization with an OAuth code."""

        headers = {
            "Authorization": f"Basic {self.CLIENT_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.SPOTIFY_REDIRECT_URI}

        self.time_refreshed = timezone.now()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=headers,
            data=data)

        self.update(response)

    def refresh(self):
        """Refresh the tokens."""

        headers = {
            "Authorization": f"Basic {self.CLIENT_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token}

        self.time_refreshed = timezone.now()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=headers,
            data=data)

        self.update(response)

    def update(self, response: requests.Response):
        """Update data based on authorization response."""

        if response.status_code != 200:
            print("failed to authorize with Spotify:", response.json())
            raise SpotifyException("failed to authorize with Spotify")

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.token_type = data["token_type"]
        self.expires_in = data["expires_in"]
        self.scope = data["scope"]
        self.save()

    def retry(self, request: Callable[[], requests.Response]) -> requests.Response:
        """Try to refresh if it doesn't work initially."""

        just_refreshed = False
        if self.is_token_expired():
            self.refresh()
            just_refreshed = True

        response = request()

        if not just_refreshed and response.status_code == 401:
            self.refresh()
            response = request()

        return response

    def make_headers(self, **extra) -> dict:
        """Reuse."""

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            **extra}

    def is_token_expired(self) -> bool:
        """Check if the cached token is past expiry."""

        return timezone.now() >= self.time_refreshed + timezone.timedelta(seconds=self.expires_in)

    def get_me(self) -> dict:
        """Get user info."""

        response = self.retry(lambda: requests.get(
            "https://api.spotify.com/v1/me",
            headers=self.make_headers()))

        if response.status_code != 200:
            print(f"failed to add items to playlist: {response.content}")
            raise SpotifyException("failed to access authorized user data")

        return response.json()

    def get_track(self, track_id: str) -> dict:
        """Get track info."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers=self.make_headers()))

        if response.status_code == 404:
            raise SpotifySemanticError("sorry, this track doesn't seem to exist!")
        elif response.status_code != 200:
            raise SpotifyRuntimeError(
                f"failed to retrieve track ID {track_id}",
                details=f"status {response.status_code}; {response.content}")

        return response.json()

    def get_current_track(self) -> Optional[dict]:
        """Get the currently playing track."""

        response = self.retry(lambda: requests.get(
            "https://api.spotify.com/v1/me/player/currently-playing",
            headers=self.make_headers()))

        if response.status_code == 204:
            return None

        if response.status_code != 200:
            print(f"failed to get current track: {response.content}")
            raise SpotifyException("failed to get current track")

        return response.json()

    def get_recently_played(self, limit: int = 3) -> Optional[dict]:
        """Get the recently played tracks of a user."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/me/player/recently-played?limit={limit}",
            headers=self.make_headers()))

        if response.status_code == 204:
            return None

        if response.status_code != 200:
            print(f"failed to get recently played: {response.content}")
            raise SpotifyException("failed to get recently played")

        return response.json()

    def get_playlist(self, playlist_id: str) -> dict:
        """Get track info."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}",
            headers=self.make_headers()))

        if response.status_code == 404:
            print(f"playlist does not exist: {response.content}")
            raise InvalidPlaylistSpotifyException("playlist does not exist")

        if response.status_code != 200:
            print(f"failed to get playlist: {response.content}")
            raise SpotifyException("failed to get playlist")

        return response.json()

    def add_items_to_playlist(self, playlist_id: str, uris: Iterable[str]):
        """Add a series of tracks to a playlist."""

        response = self.retry(lambda: requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=self.make_headers(),
            json={"uris": uris}))

        if response.status_code != 201:
            raise SpotifyRuntimeError(
                "failed to add items to playlist",
                details=f"status {response.status_code}; {response.content}")

    def add_item_to_queue(self, uri: str):
        """Add a track to a queue."""

        response = self.retry(lambda: requests.post(
            f"https://api.spotify.com/v1/me/player/queue?uri={uri}",
            headers=self.make_headers()))

        if response.status_code == 404 and response.headers.get("Content-Type") == "application/json":
            if error := response.json().get("error"):
                if error.get("reason") == "NO_ACTIVE_DEVICE":
                    raise SpotifySemanticError(f"{self.user.first_name} isn't listening to Spotify right now!")

        if response.status_code != 204:
            raise SpotifyRuntimeError(
                "failed to add item to queue",
                details=f"status {response.status_code}; {response.content}")


class Integration(models.Model):
    """Base fields."""

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)

    time_created = models.DateTimeField(default=timezone.now)
    time_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TwitchIntegration(Integration):
    """Adds hooks to the playlistener Twitch bot."""

    user = models.ForeignKey(to=User, on_delete=models.CASCADE, related_name="twitch_integrations")

    channel = models.CharField(max_length=100, unique=True)
    delay = models.FloatField(default=60)

    add_to_queue = models.BooleanField(default=False)
    add_to_playlist = models.BooleanField(default=True)
    playlist_id = models.CharField(max_length=50, null=True, blank=True)


class TwitchIntegrationUser(models.Model):
    """Used for bans and timeouts."""

    integration = models.ForeignKey(to=TwitchIntegration, on_delete=models.CASCADE, related_name="users")

    name = models.CharField(max_length=100)
    banned = models.BooleanField(default=False)

    time_created = models.DateTimeField(default=timezone.now)
    time_queued = models.DateTimeField(null=True, blank=True, default=None)

    def cooldown(self, delay: float) -> float:
        """Check if the user has queued a song within the delay period."""

        if self.time_queued is None:
            return 0
        return self.time_queued + timezone.timedelta(seconds=delay) - timezone.now()


class DiscordIntegration(Integration):
    """Add hooks to the Discord bot."""

    user = models.ForeignKey(to=User, on_delete=models.CASCADE, related_name="discord_integrations")

    guild = models.CharField(max_length=200)

    playlist_id = models.CharField(max_length=50)
