import json
import disnake

from . import *


with open("credentials.local.json") as file:
    credentials = json.load(file)


class PlayListener(disnake.Client):
    """Listens to user messages and looks for links."""

    async def on_ready(self):
        """Called when the bot is authenticated."""

        print(f"logged in as {self.user} (ID: {self.user.id})")

    async def on_message(self, message):
        """Invoked when you receive a message."""

        if message.author.id == self.user.id:
            return

        if message.content.startswith("?link"):
            await message.channel.send(f"""https://open.spotify.com/playlist/{credentials["spotify"]["playlist"]}""")
            return

        track_links = tuple(find_spotify_track_links(message.content))
        if len(track_links) == 0:
            requests.post("https://api.spotify.com/")

        await message.channel.send(f"found {len(track_links)} Spotify links o_o")


intents = disnake.Intents.default()
intents.members = True

# client = PlayListener(intents=intents)
# client.run(credentials["discord"]["token"])

token = request_access_token(
    credentials["spotify"]["id"],
    credentials["spotify"]["secret"],
    credentials["spotify"]["code"])
add_items_to_playlist(token, credentials["spotify"]["playlist"], ["spotify:track:4X9JAGRyJnnHN3KUjq1r9C"])
