import disnake

from .spotify import *


class PlayListener(disnake.Client):
    """Listens to user messages and looks for links."""

    playlist_id: str
    spotify_session: SpotifySession

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

        uris = tuple(find_spotify_track_links(message.content))
        if len(uris) == 0:
            return

        self.spotify_session.add_items_to_playlist(self.playlist_id, uris)
        await message.channel.send(f"added {len(uris)} items to spotify:playlist:{self.playlist_id}")


def main(credentials: dict):
    """Run the client."""

    intents = disnake.Intents.default()
    intents.members = True
    client = PlayListener(
        spotify_session=SpotifySession(credentials["spotify"]["id"], credentials["spotify"]["secret"]),
        playlist_id=credentials["spotify"]["playlist"],
        intents=intents)
    client.run(credentials["discord"]["token"])
