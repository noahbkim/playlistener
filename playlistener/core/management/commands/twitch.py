from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from core.models import TwitchIntegration, TwitchIntegrationUser, SpotifyException, NoQueueSpotifyException
from common.spotify import find_first_spotify_track_link

import requests
from twitchio.ext import commands
from dataclasses import dataclass
from typing import List


@dataclass
class TwitchAuthorization:
    """Holds onto tokens."""

    access_token: str
    refresh_token: str
    scope: List[str]
    token_type: str

    @classmethod
    def request(cls, refresh_token: str) -> "TwitchAuthorization":
        """Set refresh token and refresh."""

        self = TwitchAuthorization(
            access_token="",
            refresh_token=refresh_token,
            scope=[],
            token_type="")
        self.refresh()
        return self

    def refresh(self):
        """Refresh the authorization."""

        response = requests.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": settings.TWITCH_CLIENT_ID,
            "client_secret": settings.TWITCH_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token}).json()

        self.access_token = response["access_token"]
        self.refresh_token = response["refresh_token"]
        self.scope = response["scope"]
        self.token_type = response["token_type"]


def describe_queue(queued: bool, added: bool) -> str:
    """Describe the action of adding a track."""

    if queued:
        if added:
            return "queued and added"
        return "queued"
    return "added"


def describe_track(track: dict) -> str:
    """Join artists, append title."""

    artists = ", ".join(artist["name"] for artist in track["artists"])
    title = track["name"]
    return f"{artists} - {title}"


class TwitchBot(commands.Bot):
    """Listens for commands and handles Spotify integration."""

    authorization: TwitchAuthorization

    def __init__(self):
        """Initialize the bot and look for integrations."""

        self.authorization = TwitchAuthorization.request(settings.TWITCH_REFRESH_TOKEN)

        channels = []
        for integration in TwitchIntegration.objects.filter(enabled=True):
            channels.append(integration.channel)

        super().__init__(
            token=self.authorization.access_token,
            prefix="?",
            initial_channels=channels)

    async def event_ready(self):
        """Print locally for verification."""

        print(f"Logged in as {self.nick}")

    @sync_to_async
    def _queue(self, context: commands.Context) -> List[str]:
        """Must be called synchronously."""

        messages = []

        integration = TwitchIntegration.objects.filter(
            channel=context.channel.name).select_related("user", "user__spotify").get()
        user, created = TwitchIntegrationUser.objects.get_or_create(
            integration=integration,
            name=context.author.name)

        if created:
            user.save()

        if user.banned:
            messages.append("sorry, you're banned from queueing songs!")
            return messages
        if user.time_queued is not None:
            if timezone.now() < user.time_queued + timezone.timedelta(seconds=integration.delay):
                messages.append(f"sorry, you have to wait {integration.delay} seconds between recommendations!")
                return messages

        track_id = find_first_spotify_track_link(context.message.content)
        if track_id is None:
            messages.append("sorry, I couldn't find a Spotify track link in your message!")
            return messages

        uri = f"spotify:track:{track_id}"

        added_to_playlist = False
        added_to_queue = False

        if integration.add_to_queue:
            try:
                integration.user.spotify.add_item_to_queue(uri)
            except NoQueueSpotifyException as exception:
                messages.append(str(exception))
            except SpotifyException as exception:
                messages.append(str(exception))
            else:
                added_to_queue = True

        if integration.add_to_playlist and integration.playlist_id is not None:
            try:
                integration.user.spotify.add_items_to_playlist(integration.playlist_id, (uri,))
            except SpotifyException as exception:
                messages.append(str(exception))
            else:
                added_to_playlist = True

        if added_to_playlist or added_to_queue:
            info = integration.user.spotify.get_track(track_id)
            messages.append(f"{describe_queue(added_to_queue, added_to_playlist)} {describe_track(info)}")

        user.time_queued = timezone.now()
        user.save()

        return messages

    @commands.command()
    async def queue(self, context: commands.Context):
        """Queue a song."""

        messages = await self._queue(context)
        for message in messages:
            await context.reply(message)

    @sync_to_async
    def _song(self, context: commands.Context):
        """Get the current song."""

        integration = TwitchIntegration.objects.filter(
            channel=context.channel.name).select_related("user", "user__spotify").get()

        try:
            current = integration.user.spotify.get_current_track()
        except SpotifyException as exception:
            return [str(exception)]

        if current.get("item") is None or "name" not in current["item"]:
            return [f"{context.channel.name} isn't listening to anything on Spotify!"]

        track = current["item"]
        url = track["external_urls"]["spotify"]
        return [f"{describe_track(track)} {url.strip()}"]

    @commands.command()
    async def song(self, context: commands.Context):
        """Queue a song."""

        messages = await self._song(context)
        for message in messages:
            await context.reply(message)

    @sync_to_async
    def _ban(self, context: commands.Context) -> List[str]:
        """Ban a user from queueing songs."""

        integration = TwitchIntegration.objects.filter(
            channel=context.channel.name).select_related("user", "user__spotify").get()
        user, _ = TwitchIntegrationUser.objects.get_or_create(
            integration=integration,
            name=context.message.content.split(maxsplit=1)[1].strip())

        if user.banned:
            return [f"{user.name} is already banned!"]

        user.banned = True
        user.save()
        return [f"banned {user.name}"]

    @commands.command()
    async def ban(self, context: commands.Context):
        """Queue a song."""

        if not context.author.is_mod and not context.author.is_broadcaster:
            await context.reply("you do not have access to this command!")
            return

        messages = await self._ban(context)
        for message in messages:
            await context.reply(message)

    @sync_to_async
    def _unban(self, context: commands.Context) -> List[str]:
        """Ban a user from queueing songs."""

        integration = TwitchIntegration.objects.filter(
            channel=context.channel.name).select_related("user", "user__spotify").get()
        user, _ = TwitchIntegrationUser.objects.get_or_create(
            integration=integration,
            name=context.message.content.split(maxsplit=1)[1].strip())

        if not user.banned:
            return [f"{user.name} isn't banned!"]

        user.banned = False
        user.save()
        return [f"unbanned {user.name}"]

    @commands.command()
    async def unban(self, context: commands.Context):
        """Queue a song."""

        if not context.author.is_mod and not context.author.is_broadcaster:
            await context.reply("you do not have access to this command!")
            return

        messages = await self._unban(context)
        for message in messages:
            await context.reply(message)

    @sync_to_async
    def _delay(self, context: commands.Context) -> List[str]:
        """Get or set delay."""

        integration = TwitchIntegration.objects.filter(channel=context.channel.name).get()
        parts = context.message.content.split(maxsplit=1)

        if len(parts) == 1:
            return [f"current queue delay is {integration.delay} seconds"]
        elif len(parts) == 2:
            try:
                delay = float(parts[1])
            except ValueError:
                return [f"expected numeric value for delay!"]

            integration.delay = delay
            integration.save()
            return [f"set queue delay to {integration.delay} seconds"]

        # Shouldn't be possible
        return []

    @commands.command()
    async def delay(self, context: commands.Context):
        """Queue a song."""

        if not context.author.is_mod and not context.author.is_broadcaster:
            await context.reply("you do not have access to this command!")
            return

        messages = await self._delay(context)
        for message in messages:
            await context.reply(message)


class Command(BaseCommand):
    """Invite a user to setup integrations."""

    def handle(self, *args, **options):
        """Run the Twitch bot."""

        bot = TwitchBot()
        bot.run()
