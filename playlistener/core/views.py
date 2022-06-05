from django.shortcuts import redirect, reverse, Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.generic import TemplateView
from django.conf import settings
from django.db import transaction
from django.contrib.auth import login, views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

import random
import string

from .models import User, Invitation, SpotifyAuthorization, SpotifyException

__all__ = (
    "LoginView",
    "LogoutView",
    "IndexView",
    "RegistrationView",
    "FinishRegistrationView")


def generate_state() -> str:
    """Generate 16 characters of hexadecimal."""

    return "".join(random.choices(string.hexdigits, k=16))


def generate_spotify_authorization_url(state: str) -> str:
    """Used to manually acquire the user code."""

    return (
        f"https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={settings.SPOTIFY_CLIENT_ID}"
        f"&scope=playlist-modify-public user-modify-playback-state"
        f"&redirect_uri={settings.SPOTIFY_REDIRECT_URI}"
        f"&state={state}")


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
        except SpotifyException as exception:
            context["spotify_exception"] = exception

        return context


class RegistrationView(TemplateView):
    """Start registration process by verifying username."""

    template_name = "core/register/index.html"

    @classmethod
    def post(cls, request: HttpRequest) -> HttpResponse:
        """Handle post username."""

        username = request.POST["username"]
        invitation = Invitation.objects.filter(username=username).first()
        if invitation is None:
            return redirect(reverse("core:register") + "?error=uninvited")

        request.session["username"] = username

        return redirect("core:oauth_spotify")


class FinishRegistrationView(TemplateView):
    """Finalize registration details."""

    template_name = "core/register/finish.html"

    @classmethod
    def post(cls, request: HttpRequest) -> HttpResponse:
        """Create the User and Spotify authorization."""

        with transaction.atomic():
            user = User.objects.create_user(
                username=request.session["username"],
                email=request.POST["email"],
                first_name=request.POST["first_name"],
                last_name=request.POST["last_name"],
                password=request.POST["password"])
            authorization = SpotifyAuthorization(user=user)
            authorization.request(request.session["spotify_code"])

        login(request, user)
        return redirect("core:index")


def view_spotify_oauth(request: HttpRequest) -> HttpResponse:
    """Start OAuth process."""

    if "next" not in request.GET:
        raise Http404

    state = request.session["spotify_state"] = generate_state()
    request.session["spotify_next"] = request.GET["next"]
    return redirect(generate_spotify_authorization_url(state))


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
