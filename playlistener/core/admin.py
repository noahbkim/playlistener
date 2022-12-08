from django.contrib import admin

from .models import Invitation, SpotifyAuthorization, TwitchAuthorization, TwitchIntegration


admin.site.register(Invitation)
admin.site.register(SpotifyAuthorization)
admin.site.register(TwitchAuthorization)
admin.site.register(TwitchIntegration)
