from django.contrib import admin

from .models import Invitation, SpotifyAuthorization, TwitchIntegration, DiscordIntegration


admin.site.register(Invitation)
admin.site.register(SpotifyAuthorization)
admin.site.register(TwitchIntegration)
admin.site.register(DiscordIntegration)
