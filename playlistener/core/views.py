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

from .models import User, Invitation, SpotifyAuthorization, SpotifyException, TwitchIntegration
from .forms import TwitchIntegrationForm

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
        f"&scope=playlist-modify-public user-read-playback-state user-modify-playback-state user-read-recently-played"
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

        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user)
        return kwargs

    def form_valid(self, form: TwitchIntegrationForm):
        """Save the instance."""

        form.instance.user = self.request.user
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
