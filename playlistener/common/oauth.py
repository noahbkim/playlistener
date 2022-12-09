from django.views import View
from django.db import models
from django.urls import reverse
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, Http404
from django.utils import timezone

import abc
import random
import string
from typing import Any, Callable

import requests


def generate_state() -> str:
    """Generate 16 characters of hexadecimal."""

    return "".join(random.choices(string.hexdigits, k=16))


def get_view_url(request: HttpRequest, view: str) -> str:
    """Generate a URL from a request and view."""

    return request.build_absolute_uri(reverse(view))


class OAuthAuthorization(models.Model):
    """Generic base class for OAuth authorization models."""

    access_token = models.CharField(max_length=250)
    refresh_token = models.CharField(max_length=250)

    token_type = models.CharField(max_length=50)
    expires_in = models.PositiveIntegerField()
    scope = models.TextField()

    time_created = models.DateTimeField(default=timezone.now)
    time_modified = models.DateTimeField(auto_now=True)
    time_refreshed = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True

    @abc.abstractmethod
    def authorize(self, request: HttpRequest, code: str):
        """Request authorization using an OAuth code."""

    @abc.abstractmethod
    def refresh(self):
        """Refresh the access token."""

    def expired(self) -> bool:
        """Check if the cached token is past expiry."""

        return timezone.now() >= self.time_refreshed + timezone.timedelta(seconds=self.expires_in)

    def retry(self, request: Callable[[], requests.Response]) -> requests.Response:
        """Refresh if expired or status code is 401."""

        just_refreshed = False
        if self.expired():
            self.refresh()
            just_refreshed = True

        response = request()

        if not just_refreshed and response.status_code == 401:
            self.refresh()
            response = request()

        return response

    def serialize(self) -> dict[str, Any]:
        """Serialize for storage in session."""

        return dict(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            token_type=self.token_type,
            expires_in=self.expires_in,
            scope=self.scope)

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "OAuthAuthorization":
        """Deserialize from session data."""

        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data["token_type"],
            expires_in=data["expires_in"],
            scope=data["scope"])


class OAuthStartView(View):
    """Generalized view for initiating OAuth token flow.

    Errors produced by this view are intentionally opaque in order to
    avoid leaking information about the API.
    """

    next_get_name: str = "next"
    next_session_name: str
    state_session_name: str

    oauth_url: str
    oauth_response_type: str = "code"
    oauth_client_id: str
    oauth_scope: str
    oauth_receive_view: str

    def get_state(self) -> str:
        """Generate a random state string for flow verification."""

        return generate_state()

    def get_oauth_url(self, state: str) -> str:
        """Generate the starting OAuth URL."""

        return (
            f"{self.oauth_url}"
            f"?response_type={self.oauth_response_type}"
            f"&client_id={self.oauth_client_id}"
            f"&scope={self.oauth_scope}"
            f"&redirect_uri={get_view_url(self.request, self.oauth_receive_view)}"
            f"&state={state}")

    def get(self, request: HttpRequest) -> HttpResponse:
        """Verify GET parameters and redirect."""

        next_url = request.GET.get(self.next_get_name)
        if next_url is None:
            raise Http404

        print("next url:", next_url)

        state = request.session[self.state_session_name] = self.get_state()
        request.session[self.next_session_name] = next_url
        return redirect(self.get_oauth_url(state))


class OAuthReceiveView(View):
    """Receive authorization token, verify state, etc."""

    next_session_name: str
    state_get_name: str = "next"
    state_session_name: str
    code_get_name: str = "code"
    code_session_name: str
    error_get_name: str = "error"
    error_session_name: str

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle response, clear session of relevant state."""

        state = request.session.pop(self.state_session_name, default=None)
        if state is None:
            raise Http404

        next_url = request.session.pop(self.next_session_name, default=None)
        if next_url is None:
            raise Http404

        if request.GET.get("state") != state:
            raise Http404

        code = request.GET.get(self.code_get_name)
        if code is not None:
            request.session[self.code_session_name] = code
            return redirect(next_url)

        # Always set code even if error
        error = request.GET.get(self.error_get_name)
        if error is not None:
            request.session[self.code_session_name] = code
            request.session[self.error_session_name] = error
            return redirect(next_url)

        # Should either be code or error
        raise Http404
