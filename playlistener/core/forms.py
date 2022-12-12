import django.contrib.auth.forms
from django import forms

from common.errors import InternalError, UsageError
from . import models


class UserCreationForm(django.contrib.auth.forms.UserCreationForm):
    """Only require email, name, passwords."""

    def clean_email(self):
        """Make sure the user has been invited."""

        email = self.cleaned_data["email"]
        invitation = models.Invitation.objects.filter(username=email).first()
        if invitation is None:
            raise forms.ValidationError(f"No invitation found for {email}")
        return email

    class Meta(django.contrib.auth.forms.UserCreationForm.Meta):
        fields = ("email", "first_name", "last_name")


class TwitchIntegrationForm(forms.ModelForm):
    """Form for creating or updating twitch integrations."""

    def __init__(
            self,
            user: models.User = None,
            twitch_id: str = None,
            twitch_login: str = None,
            *args,
            **kwargs):
        """Store user for Spotify playlist validation."""

        super().__init__(*args, **kwargs)
        if user is not None:
            self.instance.user = user
        if twitch_id is not None:
            self.instance.twitch_id = twitch_id
        if twitch_login is not None:
            self.instance.twitch_login = twitch_login

    def clean_playlist_id(self):
        """Validate that the playlist exists."""

        playlist_id = self.cleaned_data["playlist_id"]
        if playlist_id is None:
            return ""

        try:
            playlist_data = self.instance.user.spotify.get_playlist(playlist_id)
            user_data = self.instance.user.spotify.get_me()
            if playlist_data["owner"]["id"] != user_data["id"]:
                raise forms.ValidationError("Spotify playlist is not owned by authorized user!")
        except UsageError:
            raise forms.ValidationError("Playlist does not exist!")
        except (InternalError, KeyError):
            raise forms.ValidationError("Failed to verify playlist, please check Spotify authorization!")

        return playlist_id

    def clean(self) -> dict:
        """Also validate the twitch_login is unique."""

        cleaned_data = super().clean()
        if cleaned_data["add_to_playlist"] and cleaned_data["playlist_id"] == "":
            raise forms.ValidationError("A playlist must be specified if \"add to playlist\" is enabled!")

        return cleaned_data

    class Meta:
        model = models.TwitchIntegration
        fields = (
            "enabled",
            "queue_cooldown",
            # "queue_cooldown_follower",
            "queue_cooldown_subscriber",
            # "followers_only",
            "subscribers_only",
            "add_to_queue",
            "add_to_playlist",
            "playlist_id",)
