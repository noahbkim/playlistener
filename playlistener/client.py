import disnake
import re

from .spotify import *
from .respond import Responder

NAMES = re.compile("|".join((
    "playlistener",
    "blintz",
    "blintzy"
    "bint",
    "blonz",
    "blonzo",
    "bibby",
    "blippy",
    "blizno",
    "binz",
    "binzy",
    "bintzy",
    "blinzy",
    "bunz",
    "bunzy",
    "binzybot",
    "bazinga",
    "bazooper")))

CONFIRMATION_MESSAGES = (
    "i love that song :smiley_cat:",
    "great pick :heart_eyes_cat:",
    "ain't no way :skull:",
    "if you insist :pouting_cat:",
    "not you actually listening to this :joy_cat:",
    "this isn't even music :scream_cat:",
    "adding now :smile_cat:",
    "got it :smile_cat:",
    "noted :smile_cat:",
    "fantastic taste :smiley_cat:",
    "ballsacke :joy_cat:",
    "good choice :smile_cat:",
    "on it :smile_cat:",
    "added :smile_cat:",
    "i'll add this right away :smile_cat:",
    "seek therapy :crying_cat_face:",
    "woah this is great :smiley_cat:",
    "do i actually have to add this :joy_cat:",
    "fire track :fire:",
    "mashallah :pray:",
    "kurwa :pouting_cat:",
    "cyka blyat :pouting_cat:",
    "cool song :smiley_cat:",
    "this is my new favorite song :smile_cat:")

MENTION_MESSAGES = (
    "hai :smile_cat:",
    "meow :smile_cat:",
    "hullo :smiley_cat:",
    "shut up :pouting_cat:",
    "i dunno :smiley_cat:",
    "sry :crying_cat_face:",
    "my bad :crying_cat_face:",
    "alhamdu lillahi rabbil 'alamin :pray:")

THANKS_MESSAGES = (
    "you're welcome :smile_cat:",
    "hehe :smiley_cat:",
    "no u :smiley_cat:",
    "of course :smile_cat:",
    "it's nothing :smile_cat:",
    "i love you :heart_eyes_cat:",
    "you're the best :heart_eyes_cat:",)


class PlayListener(disnake.Client):
    """Listens to user messages and looks for links."""

    playlist_id: str
    spotify_session: SpotifySession
    confirmation_messages: Responder
    mention_messages: Responder
    thanks_messages: Responder

    def __init__(self, playlist_id: str, spotify_session: SpotifySession, *args, **kwargs):
        """Initialize the client with its target playlist ID."""

        super().__init__(*args, **kwargs)
        self.playlist_id = playlist_id
        self.spotify_session = spotify_session
        self.confirmation_messages = Responder(CONFIRMATION_MESSAGES)
        self.mention_messages = Responder(MENTION_MESSAGES)
        self.thanks_messages = Responder(THANKS_MESSAGES)

    async def on_ready(self):
        """Called when the bot is authenticated."""

        print(f"logged in as {self.user} (ID: {self.user.id})")

    async def on_message(self, message):
        """Invoked when you receive a message."""

        if message.author.id == self.user.id:
            return

        if message.content.startswith("?link"):
            await message.channel.send(f"https://open.spotify.com/playlist/{self.playlist_id}")
            return

        if message.content.startswith("?ignore"):
            return

        uris = tuple(find_spotify_track_links(message.content))
        if len(uris) == 0:
            if message.author.name.lower().startswith("Arvid"):
                await message.channel.send("fuck you")
                return

            content = message.content.lower()
            if self.mentions_me(message):
                if "thank" in content or "love" in content:
                    await message.channel.send(self.thanks_messages.next())
                else:
                    await message.channel.send(self.mention_messages.next())
            return

        self.spotify_session.add_items_to_playlist(self.playlist_id, uris)
        await message.channel.send(self.confirmation_messages.next())

    def mentions_me(self, message) -> bool:
        """Check if we're mentioned"""

        named = NAMES.search(message.content.lower())
        return named or any(user.id == self.user.id for user in message.mentions)


def main(credentials: dict):
    """Run the client."""

    intents = disnake.Intents.default()
    intents.members = True
    spotify_session = SpotifySession(credentials["spotify"]["id"], credentials["spotify"]["secret"])
    client = PlayListener(
        spotify_session=spotify_session,
        playlist_id=credentials["spotify"]["playlist"],
        intents=intents)
    client.run(credentials["discord"]["token"])
