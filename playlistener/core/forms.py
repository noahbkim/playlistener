from django import forms

from common.errors import InternalError, UsageError
from . import models


class TwitchIntegrationForm(forms.ModelForm):
    """Form for creating or updating twitch integrations."""

    channel: str

    def __init__(self, user: models.User, channel: str = None, *args, **kwargs):
        """Store user for Spotify playlist validation."""

        super().__init__(*args, **kwargs)
        self.user = user
        if channel is None and self.instance is not None:
            channel = self.instance.channel
        self.channel = channel

    def clean_playlist_id(self):
        """Validate that the playlist exists."""

        playlist_id = self.cleaned_data["playlist_id"]

        try:
            self.user.spotify.get_playlist(playlist_id)
        except UsageError:
            raise forms.ValidationError("Playlist does not exist!")
        except InternalError:
            raise forms.ValidationError("Failed to verify playlist, please check Spotify authorization!")

        return playlist_id

    class Meta:
        model = models.TwitchIntegration
        fields = (
            "enabled",
            "queue_cooldown",
            "queue_cooldown_subscriber",
            "add_to_queue",
            "add_to_playlist",
            "playlist_id",)
