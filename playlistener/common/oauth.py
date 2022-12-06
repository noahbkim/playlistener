from django.views import View
from django.urls import reverse
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, Http404

import random
import string


def generate_state() -> str:
    """Generate 16 characters of hexadecimal."""

    return "".join(random.choices(string.hexdigits, k=16))


def get_url(request: HttpRequest, view: str) -> str:
    """Generate a URL from a request and view."""

    return request.build_absolute_uri(reverse(view))


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
            f"&redirect_uri={get_url(self.request, self.oauth_receive_view)}"
            f"&state={state}")

    def get(self, request: HttpRequest) -> HttpResponse:
        """Verify GET parameters and redirect."""

        next_url = request.GET.get(self.next_get_name)
        if next_url is None:
            raise Http404

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
        if code is None:
            raise Http404

        request.session[self.code_session_name] = code
        return redirect(next_url)
