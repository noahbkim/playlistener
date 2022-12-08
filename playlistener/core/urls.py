from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("register/", views.RegistrationView.as_view(), name="register"),
    path("register/spotify/", views.SpotifyRegistrationView.as_view(), name="register_spotify"),
    path("register/spotify/finish/", views.SpotifyRegistrationFinishView.as_view(), name="register_spotify_finish"),
    path("register/twitch/", views.TwitchRegistrationView.as_view(), name="register_twitch"),
    path("register/account/", views.AccountRegistrationView.as_view(), name="register_account"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("twitch/", views.TwitchIntegrationView.as_view(), name="twitch"),
    path("twitch/<int:pk>/update/", views.TwitchIntegrationUpdateView.as_view(), name="twitch_update"),
    path("twitch/<int:pk>/delete/", views.TwitchIntegrationDeleteView.as_view(), name="twitch_delete"),
    path("oauth/spotify/", views.SpotifyOAuthStartView.as_view(), name="oauth_spotify"),
    path("oauth/spotify/receive/", views.SpotifyOAuthReceiveView.as_view(), name="oauth_spotify_receive"),
    path("oauth/spotify/update/", views.view_spotify_oauth_update, name="oauth_spotify_update"),
    path("oauth/twitch/", views.TwitchOAuthStartView.as_view(), name="oauth_twitch"),
    path("oauth/twitch/receive/", views.TwitchOAuthReceiveView.as_view(), name="oauth_twitch_receive"),
]
