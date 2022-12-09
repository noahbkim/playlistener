from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.http.request import HttpRequest

import requests
import base64
from typing import Iterable, Optional

from common.oauth import OAuthAuthorization, get_view_url
from common.errors import UsageError, InternalError

__all__ = (
    "User",
    "Invitation",
    "SpotifyAuthorization",
    "TwitchAuthorization",
    "TwitchIntegration",
    "TwitchIntegrationUser",)


class Invitation(models.Model):
    """Allow a user to create an account on the server."""

    username = models.CharField(max_length=150, unique=True)
    administrator = models.BooleanField(default=False)

    time_created = models.DateTimeField(default=timezone.now)


class SpotifyAuthorization(OAuthAuthorization):
    """Contains API keys for Spotify use."""

    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="spotify")

    CLIENT_TOKEN_DATA = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    CLIENT_TOKEN = base64.b64encode(CLIENT_TOKEN_DATA.encode()).decode()

    def authorize(self, request: HttpRequest, code: str):
        """Create a Spotify authorization with an OAuth code."""

        headers = {
            "Authorization": f"Basic {self.CLIENT_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": get_view_url(request, "core:oauth_spotify_receive")}

        self.time_refreshed = timezone.now()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=headers,
            data=data)

        self.update(response)

    def refresh(self):
        """Refresh the Spotify authorization token."""

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
            raise InternalError(
                "failed to authorize with Spotify, please reauthorize",
                details=f"status {response.status_code}; {response.content}")

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.token_type = data["token_type"]
        self.expires_in = data["expires_in"]
        self.scope = data["scope"]

    def make_headers(self, **extra) -> dict:
        """Reuse."""

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            **extra}

    def get_me(self) -> dict:
        """Get user info."""

        response = self.retry(lambda: requests.get(
            "https://api.spotify.com/v1/me",
            headers=self.make_headers()))

        if response.status_code != 200:
            raise InternalError(
                "failed to access authorized user's data",
                details=f"status {response.status_code}; {response.content}")

        return response.json()

    def get_track(self, track_id: str) -> dict:
        """Get track info."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers=self.make_headers()))

        if response.status_code == 400:
            raise UsageError("sorry, this track doesn't seem to exist!")
        elif response.status_code != 200:
            raise InternalError(
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
            raise InternalError(
                f"failed to retrieve current track",
                details=f"status {response.status_code}; {response.content}")

        return response.json()

    def get_recently_played(self, limit: int = 3) -> Optional[dict]:
        """Get the recently played tracks of a user."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/me/player/recently-played?limit={limit}",
            headers=self.make_headers()))

        if response.status_code == 204:
            return None

        if response.status_code != 200:
            raise InternalError(
                f"failed to retrieve recently played tracks",
                details=f"status {response.status_code}; {response.content}")

        return response.json()

    def get_playlist(self, playlist_id: str) -> dict:
        """Get track info."""

        response = self.retry(lambda: requests.get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}",
            headers=self.make_headers()))

        if response.status_code == 404:
            raise UsageError("sorry, this playlist doesn't seem to exist!")

        if response.status_code != 200:
            raise InternalError(
                "failed to retrieve playlist",
                details=f"status {response.status_code}; {response.content}")

        return response.json()

    def add_items_to_playlist(self, playlist_id: str, uris: Iterable[str]):
        """Add a series of tracks to a playlist."""

        response = self.retry(lambda: requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=self.make_headers(),
            json={"uris": uris}))

        if response.status_code != 201:
            raise InternalError(
                "failed to add items to playlist",
                details=f"status {response.status_code}; {response.content}")

    def add_item_to_queue(self, uri: str):
        """Add a track to a queue."""

        response = self.retry(lambda: requests.post(
            f"https://api.spotify.com/v1/me/player/queue?uri={uri}",
            headers=self.make_headers()))

        if response.status_code == 404:
            if response.headers.get("Content-Type") == "application/json":
                if error := response.json().get("error"):
                    if error.get("reason") == "NO_ACTIVE_DEVICE":
                        raise UsageError(f"{self.user.first_name} isn't listening to Spotify right now!")
            else:
                print("got 404 with Content-Type", response.headers.get("Content-Type"))

        if response.status_code != 204:
            raise InternalError(
                "failed to add item to queue",
                details=f"status {response.status_code}; {response.content}")


class TwitchAuthorization(OAuthAuthorization):
    """Twitch authorization for single user."""

    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="twitch")

    def authorize(self, request: HttpRequest, code: str):
        """Create a Twitch authorization with an OAuth code."""

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": settings.TWITCH_CLIENT_ID,
            "client_secret": settings.TWITCH_CLIENT_SECRET,
            "redirect_uri": get_view_url(request, "core:oauth_twitch_receive")}

        self.time_refreshed = timezone.now()
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            headers=headers,
            data=data)

        self.update(response)

    def refresh(self):
        """Refresh the Twitch authorization token."""

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": settings.TWITCH_CLIENT_ID,
            "client_secret": settings.TWITCH_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token}

        self.time_refreshed = timezone.now()
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            headers=headers,
            data=data)

        self.update(response)

    def update(self, response: requests.Response):
        """Update based on authorization response."""

        if response.status_code != 200:
            raise InternalError(
                "failed to authorize with Twitch, please reauthorize",
                details=f"status {response.status_code}; {response.content}")

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.token_type = data["token_type"]
        self.expires_in = data["expires_in"]
        self.scope = " ".join(data.get("scope", ()))
        self.save()

    def make_headers(self, **extra) -> dict:
        """Reuse."""

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": settings.TWITCH_CLIENT_ID,
            "Content-Type": "application/json",
            **extra}

    def get_me(self) -> dict:
        """Get the authorized user."""

        response = self.retry(lambda: requests.get(
            "https://api.twitch.tv/helix/users",
            headers=self.make_headers()))

        if response.status_code != 200:
            raise InternalError(
                "failed to access authorized user",
                details=f"status {response.status_code}; {response.content}")

        return response.json()["data"][0]


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

    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="twitch_integration")

    twitch_id = models.CharField(max_length=100, unique=True)
    twitch_login = models.CharField(max_length=100, unique=True)

    queue_cooldown = models.FloatField(default=60)
    queue_cooldown_follower = models.FloatField(default=60)
    queue_cooldown_subscriber = models.FloatField(default=15)
    queue_count = models.PositiveIntegerField(default=0)

    followers_only = models.BooleanField(default=True)
    subscribers_only = models.BooleanField(default=False)

    add_to_queue = models.BooleanField(default=False)
    add_to_playlist = models.BooleanField(default=True)
    playlist_id = models.CharField(max_length=50, null=True, blank=True)


class TwitchIntegrationUser(models.Model):
    """Used for bans and timeouts."""

    integration = models.ForeignKey(to=TwitchIntegration, on_delete=models.CASCADE, related_name="users")

    name = models.CharField(max_length=100)
    banned = models.BooleanField(default=False)

    time_created = models.DateTimeField(default=timezone.now)
    time_cooldown = models.DateTimeField(null=True, blank=True, default=None)
    manual_cooldown = models.BooleanField(default=False)

    queue_count = models.PositiveIntegerField(default=0)
