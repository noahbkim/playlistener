from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from core.models import *
from common.spotify import find_first_spotify_track_link
from common.errors import UsageError, InternalError

import requests
from twitchio.ext.commands import command, Bot, Context, Command
from dataclasses import dataclass
from typing import List, Callable, Coroutine, Iterable


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


def describe_track(track: dict, include_url: bool = False) -> str:
    """Join artists, append title."""

    artists = ", ".join(artist["name"] for artist in track["artists"])
    title = track["name"]

    if include_url:
        url = track["external_urls"]["spotify"].strip()
        return f"{artists} - {title} {url}"

    else:
        return f"{artists} - {title}"


def get_track_url(uri: str) -> str:
    """Generate a Spotify track link."""

    return f"https://open.spotify.com/playlist/{uri}"


def get_playlist_url(uri: str) -> str:
    """Generate a Spotify track link."""

    return f"https://open.spotify.com/playlist/{uri}"


Later = Callable[[Coroutine], None]
Callback = Callable[[Context, Later], None]


def django_command(
        *args,
        broadcaster_only: bool = False,
        mods_only: bool = False,
        **kwargs) -> Callable[[Callback], Command]:
    """A complicated wrapper to streamline database access."""

    def decorator(callback: Callback) -> Command:
        """Decorates a naive synchronous callback."""

        asynchronous = sync_to_async(callback)

        async def actual(context: Context):
            """Pass in a list for adding coroutines to execute outside."""

            if broadcaster_only and not context.author.is_broadcaster:
                await context.reply("sorry, you don't have permission to use this command!")
                return

            if mods_only and not context.author.is_broadcaster and not context.author.is_mod:
                await context.reply("sorry, you don't have permission to use this command!")
                return

            coroutines = []
            await asynchronous(context, coroutines.append)
            for coroutine in coroutines:
                await coroutine

        return command(*args, **kwargs)(actual)

    return decorator


def error_handling() -> Callable[[Callback], Callback]:
    """Adds a layer of exception handling for Spotify API access."""

    def decorator(callback: Callback) -> Callback:
        """Decorates a callback."""

        def actual(context: Context, later: Later):
            """Handle Spotify exceptions."""

            try:
                callback(context, later)
            except UsageError as error:
                later(context.reply(str(error)))
            except InternalError as error:
                print(f"{error}: {error.details}")
                later(context.send(f"error: {error}"))

        return actual

    return decorator


IntegrationCallback = Callable[[Context, Later, TwitchIntegration], None]


def with_integration(select_related: Iterable[str] = None) -> Callable[[IntegrationCallback], Callback]:
    """Look up the corresponding Twitch integration, fail silently."""

    def decorator(callback: IntegrationCallback) -> Callback:
        """Wrap the integration lookup."""

        def actual(context: Context, later: Later):
            """Only invoke if integration exists."""

            integration = TwitchIntegration.objects.filter(
                channel=context.channel.name).select_related(*select_related).first()
            if integration is not None:
                callback(context, later, integration)

        return actual

    return decorator


IntegrationUserCallback = Callable[[Context, Later, TwitchIntegration, TwitchIntegrationUser], None]


def with_user() -> Callable[[IntegrationUserCallback], IntegrationCallback]:
    """Look up the corresponding integration user model."""

    def decorator(callback: IntegrationUserCallback) -> IntegrationCallback:
        """Wrap the user access."""

        def actual(context: Context, later: Later, integration: TwitchIntegration):
            """Save the user if created."""

            user, created = TwitchIntegrationUser.objects.get_or_create(
                integration=integration,
                name=context.author.name)
            if created:
                user.save()

            callback(context, later, integration, user)

        return actual

    return decorator


class TwitchBot(Bot):
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

    @django_command()
    @error_handling()
    @with_integration(select_related=("user", "user_spotify"))
    @with_user()
    def queue(self, context: Context, later: Later, integration: TwitchIntegration, user: TwitchIntegrationUser):
        """Add a song to the queue or playlist."""

        if " " not in context.message.content.strip():
            later(context.reply(f"use this command to add Spotify links to {integration.user.first_name}'s queue"))
            return

        if user.banned:
            later(context.reply("sorry, you're banned from queueing songs!"))
            return

        is_subscriber = context.author.is_broadcaster or context.author.is_mod or context.author.is_subscriber
        cooldown = user.cooldown(integration.queue_cooldown_subscriber if is_subscriber else integration.queue_cooldown)
        if cooldown > 0:
            message = f"sorry, you have to wait {round(cooldown)} seconds to queue again!"
            if not is_subscriber and integration.queue_cooldown_subscriber < integration.queue_cooldown:
                message += f" subscribe to only wait {round(integration.queue_cooldown_subscriber)} seconds per queue."
            later(context.reply(message))
            return

        match = find_first_spotify_track_link(context.message.content)
        if match is None:
            later(context.reply("sorry, I couldn't find a Spotify track link in your message!"))
            return

        track_url, track_id = match
        track_uri = f"spotify:track:{track_id}"
        track_info = integration.user.spotify.get_track(track_id)

        added_to_playlist = False
        added_to_queue = False

        if integration.add_to_queue:
            integration.user.spotify.add_item_to_queue(track_uri)
            added_to_queue = True

        if integration.add_to_playlist and integration.playlist_id is not None:
            integration.user.spotify.add_items_to_playlist(integration.playlist_id, (track_uri,))
            added_to_playlist = True

        if added_to_playlist or added_to_queue:
            later(context.send(f"{describe_queue(added_to_queue, added_to_playlist)} {describe_track(track_info)}"))

        user.time_queued = timezone.now()
        user.save()

    @django_command()
    @error_handling()
    @with_integration()
    def playlist(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get the link to the playlist."""

        later(context.reply(f"https://open.spotify.com/playlist/{integration.playlist_id}"))

    @django_command()
    @error_handling()
    @with_integration(select_related=("user", "user__spotify"))
    def song(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get the current song."""

        current_track = integration.user.spotify.get_current_track()
        if current_track is None:
            later(context.reply(f"{integration.user.first_name} isn't listening to anything on Spotify!"))
            return

        later(context.reply(describe_track(current_track["item"], include_url=True)))

    @django_command()
    @error_handling()
    @with_integration(select_related=("user", "user__spotify"))
    def recent(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get the last couple songs."""

        recent_tracks = integration.user.spotify.get_recently_played(limit=3)
        if recent_tracks is None:
            later(context.reply(f"{integration.user.first_name} isn't listening to anything on Spotify!"))
            return

        return [", ".join(describe_track(track, include_url=True) for track in recent_tracks["items"])]

    @django_command(mods_only=True)
    @with_integration()
    @with_user()
    def ban(self, context: Context, later: Later, _: TwitchIntegration, user: TwitchIntegrationUser):
        """Ban a user from queueing songs."""

        if user.banned:
            later(context.reply(f"{user.name} is already banned!"))
            return

        user.banned = True
        user.save()
        later(context.reply(f"banned {user.name}"))

    @django_command(mods_only=True)
    @with_integration()
    @with_user()
    def unban(self, context: Context, later: Later, _: TwitchIntegration, user: TwitchIntegrationUser):
        """Ban a user from queueing songs."""

        """Ban a user from queueing songs."""

        if not user.banned:
            later(context.reply(f"{user.name} isn't banned!"))
            return

        user.banned = False
        user.save()
        later(context.reply(f"unbanned {user.name}"))

    @django_command(mods_only=True)
    @with_integration()
    def cooldown(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get or set cooldown."""

        parts = context.message.content.split(maxsplit=1)

        if len(parts) == 1:
            later(context.reply(f"queue cooldown is {integration.queue_cooldown} seconds"))

        elif len(parts) == 2:
            try:
                queue_cooldown = float(parts[1].strip())
            except ValueError:
                later(context.reply(f"expected numeric value for cooldown!"))
                return

            integration.queue_cooldown = queue_cooldown
            integration.save()
            later(context.reply(f"set queue cooldown to {queue_cooldown} seconds"))

    @django_command(mods_only=True)
    @with_integration()
    def subcooldown(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get or set subscriber cooldown."""

        parts = context.message.content.split(maxsplit=1)

        if len(parts) == 1:
            later(context.reply(f"queue cooldown for subscribers is {integration.queue_cooldown_subscriber} seconds"))

        elif len(parts) == 2:
            try:
                queue_cooldown = float(parts[1].strip())
            except ValueError:
                later(context.reply(f"expected numeric value for cooldown!"))
                return

            integration.queue_cooldown_subscriber = queue_cooldown
            integration.save()
            later(context.reply(f"set subscriber queue cooldown to {queue_cooldown} seconds"))

    @django_command(mods_only=True)
    @with_integration()
    def mode(self, context: Context, later: Later, integration: TwitchIntegration):
        """Turn queueing/playlist on and off."""

        parts = context.message.content.split(maxsplit=1)

        if len(parts) == 1:
            later(context.reply(f"the current mode is {integration.get_mode()}"))
            return

        elif len(parts) == 2:
            mode = parts[1].strip()
            if mode not in TwitchIntegration.Mode.options:
                modes = ", ".join(TwitchIntegration.Mode.options)
                later(context.reply(f"{mode} is not a valid mode; options are {modes}"))
                return

            integration.set_mode(mode)
            integration.save()
            later(context.reply(f"set mode to {mode}"))


class Command(BaseCommand):
    """Invite a user to setup integrations."""

    def handle(self, *args, **options):
        """Run the Twitch bot."""

        bot = TwitchBot()
        bot.run()
