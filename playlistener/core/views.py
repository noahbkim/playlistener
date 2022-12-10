from django.shortcuts import render, redirect, Http404
from django.urls.exceptions import Resolver404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.generic import TemplateView, FormView, UpdateView, DeleteView
from django.conf import settings
from django.contrib.auth import views, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

import logging

from common.oauth import get_view_url, OAuthStartView, OAuthReceiveView
from common.errors import InternalError
from common.flow import Flow, Step, FlowViewMixin, copy_query
from .models import SpotifyAuthorization, TwitchAuthorization, TwitchIntegration
from .forms import UserCreationForm, TwitchIntegrationForm

__all__ = (
    "LoginView",
    "LogoutView",
    "IndexView",
    "RegistrationView",
    "SpotifyAuthorizationView",
    "TwitchAuthorizationView",)


logger = logging.getLogger(__name__)


TWITCH_INTEGRATION_FLOW = Flow(name="twitch_integration", steps=(
    Step(
        name="register",
        title="register",
        description="register for an account with playlistener",
        view="core:register",
        theme="primary",
        done=lambda request: request.user.is_authenticated),
    Step(
        name="authorize_spotify",
        title="authorize spotify",
        description="give Playlistener limited access to your Spotify account",
        view="core:authorize_spotify",
        theme="spotify",
        done=lambda request: SpotifyAuthorization.objects.filter(user=request.user).exists()),
    Step(
        name="authorize_twitch",
        title="authorize twitch",
        description="allow Playlistener to verify to your Twitch account",
        view="core:authorize_twitch",
        theme="twitch",
        done=lambda request: TwitchAuthorization.objects.filter(user=request.user).exists()),
    Step(
        name="integrate_twitch",
        title="create twitch integration",
        description="create a Playlistener Twitch integration",
        view="core:twitch_integration",
        theme="primary",
        done=lambda request: TwitchIntegration.objects.filter(user=request.user).exists())))


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


class RegistrationView(FormView):
    """Start registration process by verifying username."""

    template_name = "core/register.html"
    form_class = UserCreationForm
    step = "register"

    def form_valid(self, form: UserCreationForm) -> HttpResponse:
        """Create user, verify they are invited."""

        form.save(commit=True)
        login(self.request, user=form.instance)

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
        twitch_integration = TwitchIntegration.objects.filter(user=self.request.user).first()
        context.update(
            twitch_integration=twitch_integration,
            twitch_integration_form=TwitchIntegrationForm(instance=twitch_integration))
        return context


class TwitchIntegrationFlowView(FlowViewMixin, LoginRequiredMixin, TemplateView):
    """Start integration goal."""

    template_name = "core/flow/twitch_integration.html"
    step = "register"

    def get_context_data(self, **kwargs):
        """Get static goal."""

        context = super().get_context_data(**kwargs)
        context.update(flow=TWITCH_INTEGRATION_FLOW, step=TWITCH_INTEGRATION_FLOW.steps["register"])
        return context


class SpotifyAuthorizationView(FlowViewMixin, LoginRequiredMixin, TemplateView):
    """Provide information about Spotify authorization step."""

    template_name = "core/authorize/spotify/index.html"
    step = "authorize_spotify"

    def get(self, request, *args, **kwargs):
        """Reset state."""

        flow = Flow.get(request.GET.get("flow"))
        if flow is not None:
            step = flow.steps.get(self.step)
            if step is not None and step.done(request):
                return redirect(reverse("core:authorize_spotify_finish") + copy_query(request, "flow"))

        request.session.pop("spotify_code", None)
        return super().get(request, *args, **kwargs)


class SpotifyAuthorizationFinishView(FlowViewMixin, LoginRequiredMixin, TemplateView):
    """Provide error handling and next steps."""

    template_name = "core/authorize/spotify/finish.html"
    step = "authorize_spotify"

    def get(self, request, *args, **kwargs):
        """Check if spotify_code has been set."""

        context_data = {"step_state": "&#10007;"}

        authorization = SpotifyAuthorization.objects.filter(user=self.request.user).first()
        if authorization is None:
            # Code will be None if denied
            if SpotifyOAuthReceiveView.code_session_name not in self.request.session:
                return redirect("core:authorize_spotify")

            code = self.request.session[SpotifyOAuthReceiveView.code_session_name]
            if code is None:
                context_data["state"] = "unauthorized"
                return super().get(request, *args, **kwargs, **context_data)

            try:
                authorization = SpotifyAuthorization(user=self.request.user)
                authorization.authorize(self.request, code)
            except InternalError:
                context_data["state"] = "invalid"
                return super().get(request, *args, **kwargs, **context_data)

            authorization.save()

        try:
            spotify_user_data = authorization.get_me()
        except InternalError as error:
            logger.error("Error trying to access user data after authorizing Spotify: %s: %s", error, error.details)
            context_data["state"] = "error"
            context_data["error"] = "Error retrieving Spotify user data! Please try again later."
            return context_data

        context_data["step_state"] = "&#10003;"
        context_data["state"] = "authorized"
        context_data["spotify_user"] = spotify_user_data

        return super().get(request, *args, **kwargs, **context_data)


class TwitchAuthorizationView(FlowViewMixin, LoginRequiredMixin, TemplateView):
    """Provide information about Spotify authorization step."""

    template_name = "core/authorize/twitch/index.html"
    step = "authorize_twitch"

    def get(self, request, *args, **kwargs):
        flow = Flow.get(request.GET.get("flow"))
        if flow is not None:
            step = flow.steps.get(self.step)
            if step is not None and step.done(request):
                return redirect(reverse("core:authorize_twitch_finish") + copy_query(request, "flow"))

        request.session.pop("twitch_code", None)
        return super().get(request, *args, **kwargs)


class TwitchAuthorizationFinishView(FlowViewMixin, LoginRequiredMixin, TemplateView):
    template_name = "core/authorize/twitch/finish.html"
    step = "authorize_twitch"

    def get(self, request, *args, **kwargs):
        context_data = {"step_state": "&#10007;"}

        authorization = TwitchAuthorization.objects.filter(user=self.request.user).first()
        if authorization is None:
            code = self.request.session.get(TwitchOAuthReceiveView.code_session_name)
            if code is None:
                return redirect("core:authorize_twitch")

            if code is None:
                context_data["state"] = "unauthorized"
                return context_data

            try:
                authorization = TwitchAuthorization(user=self.request.user)
                authorization.authorize(self.request, code)
            except InternalError:
                context_data["state"] = "invalid"
                return context_data

            authorization.save()

        try:
            twitch_user_data = authorization.get_me()
        except InternalError as error:
            logger.error("Error trying to access user data after authorizing Twitch: %s: %s", error, error.details)
            context_data["state"] = "error"
            context_data["error"] = "Error retrieving Twitch user data! Please try again later."
            return context_data

        context_data["step_state"] = "&#10003;"
        context_data["state"] = "authorized"
        context_data["twitch_user"] = twitch_user_data

        return super().get(request, *args, **kwargs, **context_data)


class TwitchIntegrationView(FlowViewMixin, LoginRequiredMixin, FormView):
    """Create a new twitch integration."""

    template_name = "core/integrations/twitch/create.html"
    form_class = TwitchIntegrationForm
    step = "integrate_twitch"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Make sure we have requisite authorizations."""

        if not TwitchAuthorization.objects.filter(user=request.user).exists():
            return redirect("core:flow_twitch_integration")
        elif not SpotifyAuthorization.objects.filter(user=request.user).exists():
            return redirect("core:flow_twitch_integration")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Users should only have one integration."""

        return TwitchIntegration.objects.filter(user=self.request.user).first()

    def get_form_kwargs(self):
        """Add user to kwargs."""

        twitch_user = self.request.user.twitch.get_me()
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

    template_name = "core/integrations/twitch/create.html"
    form_class = TwitchIntegrationForm
    queryset = TwitchIntegration.objects

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


class TwitchIntegrationDeleteView(LoginRequiredMixin, DeleteView):
    """Allow modification and deletion."""

    queryset = TwitchIntegration.objects
    template_name = "core/integrations/delete/templates/core/integrations/twitch/twitch_confirm_delete.html"

    def get_success_url(self):
        """Go back to index."""

        return reverse("core:index")


def view_404(request: HttpRequest, exception: Resolver404) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/404.html")


def view_500(request: HttpRequest) -> HttpResponse:
    """Render the 404 template."""

    return render(request, "core/500.html")
