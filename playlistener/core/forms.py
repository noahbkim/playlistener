from django.forms import ModelForm, ValidationError

from . import models


class TwitchIntegrationForm(ModelForm):
    """Form for creating or updating twitch integrations."""

    def __init__(self, user, *args, **kwargs):
        """Store user for Spotify playlist validation."""

        super().__init__(*args, **kwargs)
        self.user = user

    def clean_playlist_id(self):
        """Validate that the playlist exists."""

        playlist_id = self.cleaned_data["playlist_id"]

        try:
            self.user.spotify.get_playlist(playlist_id)
        except models.InvalidPlaylistSpotifyException:
            raise ValidationError("Playlist does not exist!")
        except models.SpotifyException:
            raise ValidationError("Failed to verify playlist, please check Spotify authorization")

        return playlist_id

    class Meta:
        model = models.TwitchIntegration
        fields = ("channel", "delay", "add_to_queue", "add_to_playlist", "playlist_id")
