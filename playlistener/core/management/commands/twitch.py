from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from core.models import TwitchIntegrationUser, TwitchIntegration
from common.spotify import find_first_spotify_track_link, find_first_spotify_playlist_link
from common.errors import UsageError, InternalError

import requests
from twitchio import Channel
from twitchio.ext.commands import command, cooldown, Bot, Context, Command, CommandNotFound, CommandOnCooldown
from twitchio.ext.routines import routine, Routine
from math import ceil
from dataclasses import dataclass
from typing import List, Callable, Coroutine, Iterable, Optional, Any, Dict, Set


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
            "refresh_token": self.refresh_token})

        if response.status_code != 200:
            raise InternalError("failed to authorize with Twitch")

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.scope = data["scope"]
        self.token_type = data["token_type"]


def describe_queue_action(queued: bool, added: bool) -> str:
    """Describe the action of adding a track."""

    if queued:
        if added:
            return "queued and added"
        return "queued"
    return "added"


def describe_queue_destination(queued: bool, added: bool) -> str:
    """Describe the action of adding a track."""

    if queued:
        if added:
            return "queue and playlist"
        return "queue"
    return "playlist"


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


def try_float(value: str) -> Optional[float]:
    """Try to parse a float."""

    try:
        return float(value.strip())
    except ValueError:
        return None


def try_bool(value: str) -> Optional[bool]:
    """Try to parse a bool."""

    lower = value.lower()
    if lower in {"true", "on", "yes"}:
        return True
    elif lower in {"false", "off", "no"}:
        return False
    return None


Later = Callable[[Coroutine], None]
CommandCallback = Callable[[Any, Context, Later], None]
RoutineCallback = Callable[[Any, Later], None]


def django_routine(*args, **kwargs) -> Callable[[RoutineCallback], Routine]:
    """Same as below but more general."""

    def decorator(synchronous: RoutineCallback) -> Routine:
        """Just invoke."""

        asynchronous = sync_to_async(synchronous)

        async def actual(self):
            """Pass in a list for adding coroutines."""

            coroutines = []
            await asynchronous(self, coroutines.append)
            for coroutine in coroutines:
                await coroutine

        return routine(*args, **kwargs)(actual)

    return decorator


def django_command(
        *args,
        broadcaster_only: bool = False,
        mods_only: bool = False,
        **kwargs) -> Callable[[CommandCallback], Command]:
    """A complicated wrapper to streamline database access."""

    def decorator(synchronous: CommandCallback) -> Command:
        """Decorates a naive synchronous callback."""

        asynchronous = sync_to_async(synchronous)

        async def actual(self, context: Context):
            """Pass in a list for adding coroutines to execute outside."""

            if broadcaster_only and not context.author.is_broadcaster:
                await context.reply("sorry, you don't have permission to use this command!")
                return

            if mods_only and not context.author.is_broadcaster and not context.author.is_mod:
                await context.reply("sorry, you don't have permission to use this command!")
                return

            coroutines = []
            await asynchronous(self, context, coroutines.append)
            for coroutine in coroutines:
                await coroutine

        return command(*args, name=kwargs.get("name", synchronous.__name__), **kwargs)(actual)

    return decorator


def error_handling() -> Callable[[CommandCallback], CommandCallback]:
    """Adds a layer of exception handling for Spotify API access."""

    def decorator(callback: CommandCallback) -> CommandCallback:
        """Decorates a callback."""

        def actual(self, context: Context, later: Later):
            """Handle Spotify exceptions."""

            try:
                callback(self, context, later)
            except UsageError as error:
                later(context.reply(str(error)))
            except InternalError as error:
                print(f"{error}: {error.details}")
                later(context.send(f"error: {error}"))

        actual.__name__ = callback.__name__
        return actual

    return decorator


IntegrationCallback = Callable[[Any, Context, Later, TwitchIntegration], None]


def with_integration(select_related: Iterable[str] = ()) -> Callable[[IntegrationCallback], CommandCallback]:
    """Look up the corresponding Twitch integration, fail silently."""

    def decorator(callback: IntegrationCallback) -> CommandCallback:
        """Wrap the integration lookup."""

        def actual(self, context: Context, later: Later):
            """Only invoke if integration exists."""

            integration = TwitchIntegration.objects.filter(
                twitch_login=context.channel.name).select_related(*select_related).first()
            if integration is not None:
                callback(self, context, later, integration)

        actual.__name__ = callback.__name__
        return actual

    return decorator


IntegrationUserCallback = Callable[[Any, Context, Later, TwitchIntegration, TwitchIntegrationUser], None]


def with_user() -> Callable[[IntegrationUserCallback], IntegrationCallback]:
    """Look up the corresponding integration user model."""

    def decorator(callback: IntegrationUserCallback) -> IntegrationCallback:
        """Wrap the user access."""

        def actual(self, context: Context, later: Later, integration: TwitchIntegration):
            """Save the user if created."""

            user, created = TwitchIntegrationUser.objects.get_or_create(
                integration=integration,
                name=context.author.name)
            if created:
                user.save()

            callback(self, context, later, integration, user)

        actual.__name__ = callback.__name__
        return actual

    return decorator


@sync_to_async
def get_twitch_integrations() -> Dict[str, TwitchIntegration]:
    return {
        integration.twitch_login: integration
        for integration in TwitchIntegration.objects.filter(enabled=True).all()}


class TwitchBot(Bot):
    """Listens for commands and handles Spotify integration."""

    authorization: TwitchAuthorization
    joined: Set[str]

    def __init__(self):
        """Initialize the bot and look for integrations."""

        self.authorization = TwitchAuthorization.request(settings.TWITCH_REFRESH_TOKEN)
        self.joined = set()

        super().__init__(token=self.authorization.access_token, prefix="?")

    async def event_ready(self):
        """Print locally for verification."""

        print(f"Logged in as {self.nick}")
        self.synchronize.start()
        self.notify.start()

    async def event_token_expired(self):
        """Print locally."""

        print(f"Token expired!")

        try:
            self.authorization.refresh()
        except InternalError as error:
            print(f"Failed to reauthorize: {error}")

    async def event_command_error(self, context: Context, error: Exception):
        """Handle command errors."""

        if isinstance(error, CommandNotFound):
            return
        elif isinstance(error, CommandOnCooldown):
            await context.reply(f"sorry, this command is on cooldown for {ceil(error.retry_after)} seconds!")
            return

        await super().event_command_error(context, error)

    async def event_channel_joined(self, channel: Channel):
        """Notify the channel!"""

        await channel.send(f"{channel.name}'s queue is active!")

    async def event_channel_join_failure(self, channel: str):
        """Remove from joined set."""

        self.joined.remove(channel)
        print(f"Failed to join channel {channel}")

    @routine(seconds=15)
    async def synchronize(self):
        """Check if streams are live, join or part channels."""

        integrations = await get_twitch_integrations()
        streams = await self.fetch_streams(user_logins=integrations.keys())

        join = []
        for stream in streams:
            integration = integrations.pop(stream.user.name)
            if integration.twitch_login not in self.joined:
                join.append(integration.twitch_login)
                self.joined.add(integration.twitch_login)

        part = []
        for integration in integrations.values():
            part.append(integration.twitch_login)
            self.joined.remove(integration.twitch_login)

        if join:
            print("joining", ", ".join(join))
            await self.join_channels(join)

        if part:
            print("leaving", ", ".join(part))
            await self.part_channels(part)

    @django_routine(minutes=15)
    def notify(self, later: Later):
        """Notify everyone about queueing."""

        for channel in self.connected_channels:
            integration = TwitchIntegration.objects.filter(channel=channel.name).first()
            if integration is None:
                continue

            if integration.enabled and (integration.add_to_queue or integration.add_to_playlist):
                later(channel.send(f"use ?queue to add Spotify songs to {integration.user.first_name}'s playlist"))

    @cooldown(rate=3, per=30)
    @django_command()
    @error_handling()
    @with_integration(select_related=("user", "user__spotify"))
    @with_user()
    def queue(self, context: Context, later: Later, integration: TwitchIntegration, user: TwitchIntegrationUser):
        """Add a song to the queue or playlist."""

        if not integration.enabled:
            later(context.reply(f"sorry, playlistener has been turned off!"))
            return

        if not integration.add_to_queue and not integration.add_to_playlist:
            later(context.send(f"neither the queue nor playlist are enabled right now!"))
            return

        is_subscriber = context.author.is_broadcaster or context.author.is_mod or context.author.is_subscriber
        if integration.subscribers_only and not is_subscriber:
            later(context.send("sorry, the queue is in sub mode right now!"))
            return

        if " " not in context.message.content.strip():
            first_name = integration.user.first_name
            destination = describe_queue_destination(integration.add_to_queue, integration.add_to_playlist)
            later(context.reply(f"use this command to add Spotify links to {first_name}'s {destination}"))
            return

        if user.banned:
            later(context.reply("sorry, you're banned from queueing songs!"))
            return

        if user.time_cooldown is not None and user.time_cooldown > timezone.now():
            difference = user.time_cooldown - timezone.now()
            message = f"sorry, you have to wait {ceil(difference.seconds)} seconds to queue again!"

            is_tiered = integration.queue_cooldown_subscriber < integration.queue_cooldown
            if not user.manual_cooldown and not is_subscriber and is_tiered:
                message += f" subscribe to only wait {ceil(integration.queue_cooldown_subscriber)} seconds per queue."

            later(context.reply(message))
            return

        else:
            user.manual_cooldown = False

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

        later(context.send(f"{describe_queue_action(added_to_queue, added_to_playlist)} {describe_track(track_info)}"))
        integration.queue_count += 1
        user.queue_count += 1
        integration.save()

        queue_cooldown = integration.queue_cooldown_subscriber if is_subscriber else integration.queue_cooldown
        user.time_cooldown = timezone.now() + timezone.timedelta(seconds=queue_cooldown)
        user.save()

    @django_command()
    @error_handling()
    @with_integration()
    def playlist(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get the link to the playlist."""

        if integration.playlist_id is None:
            later(context.reply("no playlist is configured for this channel"))
            return

        later(context.reply(get_playlist_url(integration.playlist_id)))

    @cooldown(rate=3, per=60)
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
    @with_integration()
    @with_user()
    def count(self, context: Context, later: Later, integration: TwitchIntegration, user: TwitchIntegrationUser):
        """Get the count of recommendations for a user."""

        later(context.reply(
            f"{user.name} has queued {user.queue_count} of {integration.queue_count} total songs"
            f" on {context.channel.name}'s channel"))

    @cooldown(rate=3, per=60)
    @django_command()
    @error_handling()
    @with_integration(select_related=("user", "user__spotify"))
    def recent(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get the last couple songs."""

        recent_tracks = integration.user.spotify.get_recently_played(limit=3)
        if recent_tracks is None:
            later(context.reply(f"{integration.user.first_name} isn't listening to anything on Spotify!"))
            return

        names = []
        for item in recent_tracks["items"]:
            if "track" in item:
                names.append(describe_track(item["track"], include_url=True))

        later(context.reply(", ".join(names)))

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

        if not user.banned:
            later(context.reply(f"{user.name} isn't banned!"))
            return

        user.banned = False
        user.save()
        later(context.reply(f"unbanned {user.name}"))

    @django_command(mods_only=True)
    @with_integration()
    def cooldown(self, context: Context, later: Later, integration: TwitchIntegration):
        """Apply a timeout to a user."""

        parts = context.message.content.split(maxsplit=2)

        if len(parts) == 1:
            later(context.reply(f"expected a username!"))
            return

        name = parts[1].strip()
        user = integration.users.filter(name=name).first()
        if user is None:
            later(context.reply(f"couldn't find user {name}"))
            return

        if len(parts) == 2:
            if user.time_cooldown is not None and user.time_cooldown > timezone.now():
                difference = user.time_cooldown - timezone.now()
                manual = " manual" if user.manual_cooldown else ""
                later(context.reply(f"{name} has a{manual} cooldown for {ceil(difference.seconds)} more seconds"))
            else:
                later(context.reply(f"{name} has no cooldown"))

        elif len(parts) == 3:
            queue_cooldown = 0 if parts[2] == "clear" else try_float(parts[2])
            if queue_cooldown is None:
                later(context.reply(f"expected numeric value or clear for cooldown!"))
                return

            if queue_cooldown <= 0:
                user.time_cooldown = None
                later(context.reply(f"{name}'s cooldown has been cleared"))
            else:
                user.time_cooldown = timezone.now() + timezone.timedelta(seconds=queue_cooldown)
                later(context.reply(f"{name} is on a {ceil(queue_cooldown)} second cooldown"))

            user.save()

    @django_command(mods_only=True)
    @with_integration()
    def config(self, context: Context, later: Later, integration: TwitchIntegration):
        """Get or set cooldown."""

        parts = context.message.content.split(maxsplit=3)
        handlers = {
            "submode": self.config_submode,
            "usequeue": self.config_usequeue,
            "useplaylist": self.config_useplaylist,
            "cooldown": self.config_cooldown,
            "subcooldown": self.config_subcooldown,
            "playlist": self.config_playlist}

        if len(parts) == 1:
            later(context.reply(f"variables available for configuration are " + ", ".join(handlers.keys())))
            return

        key = parts[1]
        handler = handlers.get(key)
        if handler is None:
            later(context.reply(f"invalid config variable {key}"))
            return

        if len(parts) == 2:
            handler(context, later, integration)
        elif len(parts) == 3:
            handler(context, later, integration, value=parts[2])

    @staticmethod
    def config_submode(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Toggle playlist adding."""

        if value is None:
            later(context.reply("sub mode is on" if integration.subscribers_only else "sub mode is off"))
            return

        subscribers_only = try_bool(value)
        if subscribers_only is None:
            later(context.reply("expected value to be on or off"))
            return

        integration.subscribers_only = subscribers_only
        integration.save()
        later(context.reply("sub mode is on" if integration.subscribers_only else "sub mode is off"))

    @staticmethod
    def config_cooldown(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Request or configure cooldown."""

        if value is None:
            later(context.reply(f"queue cooldown is {integration.queue_cooldown} seconds"))
            return

        queue_cooldown = try_float(value)
        if queue_cooldown is None:
            later(context.reply(f"expected numeric value for cooldown!"))
            return

        integration.queue_cooldown = queue_cooldown
        integration.save()
        later(context.reply(f"set queue cooldown to {queue_cooldown} seconds"))

    @staticmethod
    def config_subcooldown(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Request or configure subscriber cooldown."""

        if value is None:
            later(context.reply(f"subscriber queue cooldown is {integration.queue_cooldown_subscriber} seconds"))
            return

        subscriber_queue_cooldown = try_float(value)
        if subscriber_queue_cooldown is None:
            later(context.reply(f"expected numeric value for cooldown!"))
            return

        integration.queue_cooldown_subscriber = subscriber_queue_cooldown
        integration.save()
        later(context.reply(f"set subscriber queue cooldown to {subscriber_queue_cooldown} seconds"))

    @staticmethod
    def config_usequeue(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Toggle queueing."""

        if value is None:
            later(context.reply("queueing is on" if integration.add_to_queue else "queueing is off"))
            return

        add_to_queue = try_bool(value)
        if add_to_queue is None:
            later(context.reply("expected value to be on or off"))
            return

        integration.add_to_queue = add_to_queue
        integration.save()
        later(context.reply("queueing is enabled" if integration.add_to_queue else "queueing is off"))

    @staticmethod
    def config_useplaylist(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Toggle playlist adding."""

        if value is None:
            later(context.reply("add to playlist is on" if integration.add_to_playlist else "add to playlist is off"))
            return

        add_to_playlist = try_bool(value)
        if add_to_playlist is None:
            later(context.reply("expected value to be on or off"))
            return

        integration.add_to_playlist = add_to_playlist
        integration.save()
        later(context.reply("add to playlist is on" if integration.add_to_playlist else "add to playlist is off"))

    @staticmethod
    def config_playlist(context: Context, later: Later, integration: TwitchIntegration, value: str = None):
        """Validate and set new playlist ID."""

        if value is None:
            later(context.reply(f"current playlist is {get_playlist_url(integration.playlist_id)}"))
            return

        match = find_first_spotify_playlist_link(value)
        if match is None:
            later(context.reply(f"value must be a Spotify playlist URL!"))
            return

        playlist_url, playlist_id = match

        try:
            playlist = integration.user.spotify.get_playlist(playlist_id)
        except UsageError:
            later(context.reply(f"the provided playlist does not seem to exist!"))
            return
        except InternalError:
            later(context.reply("failed to verify playlist, please check Spotify authorization!"))
            return

        playlist_name = playlist["name"]
        later(context.reply(f"set playlist to {playlist_name} {playlist_url}"))
        return

    @django_command(mods_only=True)
    @with_integration()
    def on(self, context: Context, later: Later, integration: TwitchIntegration):
        """Turn integration on and off."""

        if integration.enabled:
            later(context.reply("already on!"))
            return

        integration.enabled = True
        integration.save()
        later(context.reply("queueing is now enabled!"))

    @django_command(mods_only=True)
    @with_integration()
    def off(self, context: Context, later: Later, integration: TwitchIntegration):
        """Turn integration on and off."""

        if not integration.enabled:
            later(context.reply("already off!"))
            return

        integration.enabled = False
        integration.save()
        later(context.reply("queueing is now unavailable!"))


class Command(BaseCommand):
    """Invite a user to setup integrations."""

    def handle(self, *args, **options):
        """Run the Twitch bot."""

        bot = TwitchBot()
        bot.run()
