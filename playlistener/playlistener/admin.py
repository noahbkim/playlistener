from django.contrib import admin
from django.contrib.admin import apps
from django.shortcuts import render
from django.urls import path
from django.http import HttpRequest, HttpResponse
from django.conf import settings

import requests


def view_oauth_twitch(request: HttpRequest) -> HttpResponse:
    """Show code from Twitch verification."""

    data = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
        "code": request.GET["code"],
        "grant_type": "authorization_code",
        "redirect_uri": settings.TWITCH_REDIRECT_URI}).json()

    return render(request, "admin/oauth/twitch.html", context=dict(data=data))


class AdminSite(admin.AdminSite):
    """Add custom URLs."""

    index_template = "admin/index.html"

    def get_urls(self):
        """Add Twitch OAuth endpoint for verification."""

        return [
            path("oauth/twitch/", view_oauth_twitch, name="oauth_twitch"),
        ] + super().get_urls()

    def index(self, request: HttpRequest, extra_context: dict = None) -> HttpResponse:
        """Add context of Twitch URL."""

        url = (
            "https://id.twitch.tv/oauth2/authorize"
            "?response_type=code"
            f"&client_id={settings.TWITCH_CLIENT_ID}"
            f"&redirect_uri={settings.TWITCH_REDIRECT_URI}"
            "&scope=chat%3Aedit+chat%3Aread"
            "&state=00000000000000000000000000000000")
        return super().index(request, extra_context=dict(twitch_oauth_url=url))


class AdminConfig(apps.AdminConfig):
    """Set default site."""

    default_site = "playlistener.admin.AdminSite"
