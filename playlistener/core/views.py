from django.shortcuts import render, redirect, Http404
from django.urls.exceptions import Resolver404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.generic import TemplateView, FormView, UpdateView, DeleteView
from django.conf import settings
from django.db import transaction
from django.contrib.auth import login, views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

import requests
import logging

from common.errors import InternalError
from common.oauth import generate_state, get_url, OAuthStartView, OAuthReceiveView
from .models import User, Invitation, SpotifyAuthorization, TwitchIntegration
from .forms import TwitchIntegrationForm

__all__ = (
    "LoginView",
    "LogoutView",
    "IndexView",
    "RegistrationView",
    "FinishRegistrationView")


logger = logging.getLogger(__name__)

SPOTIFY_SCOPE = " ".join((
    "playlist-modify-public",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-recently-played",))


def generate_spotify_authorization_url(state: str, scope: str = "") -> str:
    """Used to manually acquire the user code."""

    return (
        "https://accounts.spotify.com/authorize"
        "?response_type=code"
        f"&client_id={settings.SPOTIFY_CLIENT_ID}"
        f"&scope={scope}"
        f"&redirect_uri={settings.SPOTIFY_REDIRECT_URI}"
        f"&state={state}")


def generate_twitch_authorization_url(state: str, scope: str = "") -> str:
    """Used to get the channel name."""

    return (
        "https://id.twitch.tv/oauth2/authorize"
        "?response_type=code"
        f"&client_id={settings.TWITCH_CLIENT_ID}"
        f"&redirect_uri={settings.TWITCH_REDIRECT_URI}"
        f"&scope={scope}"
        f"&state={state}")


def get_twitch_token(code: str, redirect_uri: str) -> dict:
    """Go through final OAuth flow step to get access token."""

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "code": code,
        "client_id": settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri}

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        headers=headers,
        data=data)

    if response.status_code != 200:
        raise ValueError("TODO: fix this")

    return response.json()


def get_twitch_user(access_token: str) -> dict:
    """Access user endpoint for token-owner."""

    response = requests.get(
        "https://api.twitch.tv/helix/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Client-Id": settings.TWITCH_CLIENT_ID})

    if response.status_code != 200:
        raise ValueError("TODO: fix this")

    return response.json()["data"][0]


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

        try:
            context["spotify_user"] = self.request.user.spotify.get_me()
        except InternalError as exception:
            context["spotify_exception"] = exception

        context["twitch_integrations"] = twitch_integrations = []
        for twitch_integration in self.request.user.twitch_integrations.all():
            twitch_integrations.append(TwitchIntegrationForm(instance=twitch_integration))

        return context


class RegistrationView(TemplateView):
    """Start registration process by verifying username."""

    template_name = "core/register/index.html"

    @classmethod
    def post(cls, request: HttpRequest) -> HttpResponse:
        """Handle post username."""

        username = request.POST["username"]
        if User.objects.filter(username=username).exists():
            return redirect("core:login")

        invitation = Invitation.objects.filter(username=username).first()
        if invitation is None:
            return redirect(reverse("core:register") + "?error=uninvited")

        request.session["username"] = username

        return redirect(reverse("core:oauth_spotify") + "?next=" + reverse("core:register_finish"))


class FinishRegistrationView(TemplateView):
    """Finalize registration details."""

    template_name = "core/register/finish.html"

    @classmethod
    def post(cls, request: HttpRequest) -> HttpResponse:
        """Create the User and Spotify authorization."""

        if "username" not in request.session or "spotify_code" not in request.session:
            raise Http404

        username = request.session["username"]

        invitation = Invitation.objects.filter(username=username).first()
        if invitation is None:
            return redirect(reverse("core:register") + "?error=uninvited")

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
            authorization.request(request.session["spotify_code"])

        invitation.delete()

        login(request, user)
        return redirect("core:index")


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
            token_data = get_twitch_token(twitch_code, get_url(self.request, "core:oauth_twitch_receive"))
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


@login_required
def view_spotify_oauth(request: HttpRequest) -> HttpResponse:
    """Start OAuth process."""

    if "next" not in request.GET:
        raise Http404

    state = request.session["spotify_state"] = generate_state()
    request.session["spotify_next"] = request.GET["next"]
    return redirect(generate_spotify_authorization_url(state, scope=SPOTIFY_SCOPE))


@login_required
def view_spotify_oauth_receive(request: HttpRequest) -> HttpResponse:
    """Receive OAuth, store to session, redirect."""

    if "spotify_state" not in request.session:
        raise Http404

    if request.GET["state"] != request.session["spotify_state"]:
        raise Http404

    request.session["spotify_code"] = request.GET["code"]
    return redirect(request.session["spotify_next"])


@login_required
def view_spotify_oauth_update(request: HttpRequest) -> HttpResponse:
    """Update Spotify authorization."""

    if "spotify_code" not in request.session:
        raise Http404

    request.user.spotify.request(request.session["spotify_code"])
    return redirect("core:index")


class TwitchOAuthStartView(LoginRequiredMixin, OAuthStartView):
    """Start Twitch OAuth for accessing user information."""

    next_session_name = "twitch_next"
    state_session_name = "twitch_state"
    oauth_url = "https://id.twitch.tv/oauth2/authorize"
    oauth_client_id = settings.TWITCH_CLIENT_ID
    oauth_scope = ""
    oauth_receive_view = "core:oauth_twitch_receive"


class TwitchOAuthReceiveView(LoginRequiredMixin, OAuthReceiveView):
    """Receive Twitch OAuth and redirect."""

    next_session_name = "twitch_next"
    state_session_name = "twitch_state"
    code_session_name = "twitch_code"


def view_404(request: HttpRequest, exception: Resolver404) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/404.html")


def view_500(request: HttpRequest) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/500.html")
