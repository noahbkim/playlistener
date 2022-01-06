import disnake
import random

from .spotify import *

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
    "seek therapy :crying_cat_face:")


class PlayListener(disnake.Client):
    """Listens to user messages and looks for links."""

    playlist_id: str
    spotify_session: SpotifySession
    last_confirmation_message_index: int = -1

    def __init__(self, playlist_id: str, spotify_session: SpotifySession, *args, **kwargs):
        """Initialize the client with its target playlist ID."""

        super().__init__(*args, **kwargs)
        self.playlist_id = playlist_id
        self.spotify_session = spotify_session

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
            return

        self.spotify_session.add_items_to_playlist(self.playlist_id, uris)
        await message.channel.send(self._get_confirmation_message())

    def _get_confirmation_message(self) -> str:
        """Get a random confirmation message without repeating."""

        index = random.randint(0, len(CONFIRMATION_MESSAGES) - 1)
        if index == self.last_confirmation_message_index:
            index = (index + 1) % len(CONFIRMATION_MESSAGES)
        return CONFIRMATION_MESSAGES[index]


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
