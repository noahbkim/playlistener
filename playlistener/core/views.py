from django.shortcuts import redirect, reverse, Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.generic import TemplateView, FormView, UpdateView, DeleteView
from django.conf import settings
from django.db import transaction
from django.contrib.auth import login, views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

import random
import string
import requests

from common.errors import InternalError
from .models import User, Invitation, SpotifyAuthorization, TwitchIntegration
from .forms import TwitchIntegrationForm

__all__ = (
    "LoginView",
    "LogoutView",
    "IndexView",
    "RegistrationView",
    "FinishRegistrationView")

SPOTIFY_SCOPE = " ".join((
    "playlist-modify-public",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-recently-played",))


def generate_state() -> str:
    """Generate 16 characters of hexadecimal."""

    return "".join(random.choices(string.hexdigits, k=16))


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


def get_twitch_token(code: str) -> dict:
    """Go through final OAuth flow step to get access token."""

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "code": code,
        "client_id": settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": settings.TWITCH_REDIRECT_URI}

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
            twitch_integrations.append(
                TwitchIntegrationForm(
                    user=twitch_integration.user,
                    channel=twitch_integration.channel,
                    instance=twitch_integration))

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

        # If this cached twitch_login value doesn't correspond to our current
        # token, we need to retrieve it again from the API
        twitch_login = None
        if "twitch_login" in self.request.session:
            twitch_code, twitch_login = self.request.session["twitch_login"]
            if twitch_code != self.request.session["twitch_code"]:
                twitch_login = None

        if twitch_login is None:
            twitch_code = self.request.session["twitch_code"]
            token_data = get_twitch_token(twitch_code)
            access_token = token_data["access_token"]
            user_data = get_twitch_user(access_token)
            twitch_login = user_data["login"]
            self.request.session["twitch_login"] = (twitch_code, twitch_login)

        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, channel=twitch_login)
        return kwargs

    def form_valid(self, form: TwitchIntegrationForm):
        """Save the instance."""

        form.instance.user = self.request.user
        form.instance.channel = form.channel
        form.save(commit=True)
        return super().form_valid(form)

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


class TwitchIntegrationUpdateView(LoginRequiredMixin, UpdateView):
    """Allow modification and deletion."""

    template_name = "core/index.html"
    form_class = TwitchIntegrationForm
    queryset = TwitchIntegration.objects

    def get_form_kwargs(self):
        """Add user to kwargs."""

        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user)
        return kwargs

    def get(self, request, *args, **kwargs):
        """Redirect if trying to load directly."""

        return redirect("core:index")

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


def view_spotify_oauth(request: HttpRequest) -> HttpResponse:
    """Start OAuth process."""

    if "next" not in request.GET:
        raise Http404

    state = request.session["spotify_state"] = generate_state()
    request.session["spotify_next"] = request.GET["next"]
    return redirect(generate_spotify_authorization_url(state, scope=SPOTIFY_SCOPE))


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


def view_twitch_oauth(request: HttpRequest) -> HttpResponse:
    """Start OAuth process."""

    if "next" not in request.GET:
        raise Http404

    state = request.session["twitch_state"] = generate_state()
    request.session["twitch_next"] = request.GET["next"]
    return redirect(generate_twitch_authorization_url(state))


def view_twitch_oauth_receive(request: HttpRequest) -> HttpResponse:
    """Receive OAuth, store to session, redirect."""

    if "twitch_state" not in request.session:
        raise Http404

    if request.GET["state"] != request.session["twitch_state"]:
        raise Http404

    request.session["twitch_code"] = request.GET["code"]
    return redirect(request.session["twitch_next"])
