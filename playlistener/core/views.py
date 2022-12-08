from django.shortcuts import render, redirect, Http404
from django.urls.exceptions import Resolver404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.generic import TemplateView, FormView, UpdateView, DeleteView
from django.conf import settings
from django.db import transaction
from django.contrib.auth import login, views
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

import logging

from common.oauth import get_view_url, OAuthStartView, OAuthReceiveView
from common.errors import InternalError
from .models import User, Invitation, SpotifyAuthorization, TwitchAuthorization, TwitchIntegration
from .forms import TwitchIntegrationForm

__all__ = (
    "LoginView",
    "LogoutView",
    "IndexView",
    "RegistrationView",
    "SpotifyRegistrationView",
    "TwitchRegistrationView",
    "AccountRegistrationView",)


logger = logging.getLogger(__name__)


class SpotifyOAuthStartView(OAuthStartView):
    """Start Spotify OAuth for user authorization"""

    next_session_name = "spotify_next"
    state_session_name = "spotify_state"
    oauth_url = "https://accounts.spotify.com/authorize"
    oauth_client_id = settings.SPOTIFY_CLIENT_ID
    oauth_scope = (
        "playlist-modify-public"
        " user-read-playback-state"
        " user-modify-playback-state"
        " user-read-recently-played")
    oauth_receive_view = "core:oauth_spotify_receive"


class SpotifyOAuthReceiveView(OAuthReceiveView):
    """Receive Twitch OAuth and redirect."""

    next_session_name = "spotify_next"
    state_session_name = "spotify_state"
    code_session_name = "spotify_code"
    error_session_name = "spotify_error"


@login_required
def view_spotify_oauth_update(request: HttpRequest) -> HttpResponse:
    """Update Spotify authorization."""

    if "spotify_code" not in request.session:
        raise Http404

    request.user.spotify.request(request.session["spotify_code"])
    return redirect("core:index")


class TwitchOAuthStartView(OAuthStartView):
    """Start Twitch OAuth for accessing user information."""

    next_session_name = "twitch_next"
    state_session_name = "twitch_state"
    oauth_url = "https://id.twitch.tv/oauth2/authorize"
    oauth_client_id = settings.TWITCH_CLIENT_ID
    oauth_scope = ""
    oauth_receive_view = "core:oauth_twitch_receive"


class TwitchOAuthReceiveView(OAuthReceiveView):
    """Receive Twitch OAuth and redirect."""

    next_session_name = "twitch_next"
    state_session_name = "twitch_state"
    code_session_name = "twitch_code"
    error_session_name = "twitch_error"


class RegistrationView(TemplateView):
    """Start registration process by verifying username."""

    template_name = "core/register/index.html"
    username_session_name: str = "register_username"

    @classmethod
    def post(cls, request: HttpRequest) -> HttpResponse:
        """Handle post username."""

        username = request.POST["username"]
        if User.objects.filter(username=username).exists():
            return redirect("core:login")

        invitation = Invitation.objects.filter(username=username).first()
        if invitation is None:
            return redirect(reverse("core:register") + "?error=uninvited")

        request.session[cls.username_session_name] = username
        return redirect("core:register_spotify")


class SpotifyRegistrationView(TemplateView):
    """Provide information about Spotify authorization step."""

    template_name = "core/register/spotify/index.html"

    def get(self, request, *args, **kwargs):
        """Reset state."""

        request.session.pop("spotify_code", None)
        return super().get(request, *args, **kwargs)


class SpotifyRegistrationFinishView(TemplateView):
    """Provide error handling and next steps."""

    template_name = "core/register/spotify/finish.html"
    authorization_session_name: str = "spotify_registration_authorization"

    def get(self, request, *args, **kwargs):
        """Check if spotify_code has been set."""

        if SpotifyOAuthReceiveView.code_session_name not in request.session:
            return redirect("core:register_spotify")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """If we've received the Spotify code, get data."""

        context_data = super().get_context_data(**kwargs)

        code = self.request.session[SpotifyOAuthReceiveView.code_session_name]
        if code is None:
            context_data["state"] = "unauthorized"
            return context_data

        authorization_data = self.request.session.get(self.authorization_session_name)
        if authorization_data is not None:
            authorization = SpotifyAuthorization.deserialize(authorization_data)
        else:
            try:
                authorization = SpotifyAuthorization()
                authorization.authorize(self.request, code)
            except InternalError:
                context_data["state"] = "invalid"
                return context_data
            self.request.session[self.authorization_session_name] = authorization.serialize()

        try:
            spotify_user_data = authorization.get_me()
        except InternalError as error:
            logger.error("Error trying to access user data after authorizing Spotify: %s: %s", error, error.details)
            context_data["state"] = "error"
            context_data["error"] = "Error retrieving Spotify user data! Please try again later."
            return context_data

        context_data["state"] = "authorized"
        context_data["spotify_user"] = spotify_user_data
        return context_data


class TwitchRegistrationView(TemplateView):
    """Provide information about Spotify authorization step."""

    template_name = "core/register/twitch.html"


class AccountRegistrationView(FormView):
    """Finalize registration details."""

    template_name = "core/register/account.html"
    form_class = UserCreationForm

    def check_flow(self) -> tuple[str, str, str, Invitation]:
        """Verify preconditions for this view."""

        username = self.request.session.get(RegistrationView.username_session_name)
        if username is None:
            return redirect("core:register")

        spotify_code = self.request.session.get(SpotifyOAuthReceiveView.code_session_name)
        if spotify_code is None:
            return redirect("core:register_spotify")

        twitch_code = self.request.session.get(TwitchOAuthReceiveView.code_session_name)
        if twitch_code:
            return redirect("core:register_twitch")

        invitation = Invitation.objects.filter(username=username).first()
        if invitation is None:
            return redirect(reverse("core:register") + "?error=uninvited")

    def get(self, request, *args, **kwargs):
        """"""



    def form_valid(self, form: UserCreationForm):
        """On user valid."""

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=request.POST["email"],
                first_name=request.POST["first_name"],
                last_name=request.POST["last_name"],
                password=request.POST["password"])

            if invitation.administrator:
                user.is_staff = user.is_superuser = True
                user.save()

            authorization = SpotifyAuthorization(user=user)
            authorization.authorize(request, request.session["spotify_code"])
            authorization.save()

        invitation.delete()

        login(request, user)
        return redirect("core:index")



class LoginView(views.LoginView):
    """Override for template and redirect."""

    template_name = "core/login.html"
    redirect_authenticated_user = "core:index"


class LogoutView(views.LogoutView):
    """Override for redirect."""


class IndexView(LoginRequiredMixin, TemplateView):
    """View my integrations and account details."""

    template_name = "core/index.html"

    def get_context_data(self, **kwargs) -> dict:
        """Get authorization and integration."""

        context = super().get_context_data(**kwargs)
        context.update(
            spotify=SpotifyAuthorization.objects.filter(user=self.request.user).first(),
            twitch=TwitchAuthorization.objects.filter(user=self.request.user).first())
        return context


class TwitchIntegrationView(LoginRequiredMixin, FormView):
    """Create a new twitch integration."""

    template_name = "core/twitch.html"
    form_class = TwitchIntegrationForm

    def get_form_kwargs(self):
        """Add user to kwargs."""

        if "twitch_code" not in self.request.session:
            raise Http404

        # The twitch_user["twitch_code"] should correspond to our current
        # twitch_code; if it doesn't, we need to refresh.
        twitch_user = None
        if "twitch_user" in self.request.session:
            cache = self.request.session["twitch_user"]
            if cache["key"] == self.request.session["twitch_code"]:
                twitch_user = cache["data"]

        if twitch_user is None:
            twitch_code = self.request.session["twitch_code"]
            token_data = get_twitch_token(twitch_code, get_view_url(self.request, "core:oauth_twitch_receive"))
            twitch_user = get_twitch_user(token_data["access_token"])
            self.request.session["twitch_user"] = dict(
                key=twitch_code,
                data=twitch_user,)

        kwargs = super().get_form_kwargs()
        kwargs.update(
            user=self.request.user,
            twitch_id=twitch_user["id"],
            twitch_login=twitch_user["login"],)
        return kwargs

    def form_valid(self, form: TwitchIntegrationForm):
        """Save the instance."""

        form.save(commit=True)
        return super().form_valid(form)

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


class TwitchIntegrationUpdateView(LoginRequiredMixin, UpdateView):
    """Allow modification and deletion."""

    template_name = "core/twitch.html"
    form_class = TwitchIntegrationForm
    queryset = TwitchIntegration.objects

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


class TwitchIntegrationDeleteView(LoginRequiredMixin, DeleteView):
    """Allow modification and deletion."""

    queryset = TwitchIntegration.objects
    template_name = "core/twitch_confirm_delete.html"

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


def view_404(request: HttpRequest, exception: Resolver404) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/404.html")


def view_500(request: HttpRequest) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/500.html")
