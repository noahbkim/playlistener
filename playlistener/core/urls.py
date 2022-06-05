from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("register/", views.RegistrationView.as_view(), name="register"),
    path("register/finish/", views.FinishRegistrationView.as_view(), name="register_finish"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("twitch/", views.TwitchIntegrationView.as_view(), name="twitch"),
    path("twitch/<int:pk>/update/", views.TwitchIntegrationUpdateView.as_view(), name="twitch_update"),
    path("twitch/<int:pk>/delete/", views.TwitchIntegrationDeleteView.as_view(), name="twitch_delete"),
    path("oauth/spotify/", views.view_spotify_oauth, name="oauth_spotify"),
    path("oauth/spotify/receive/", views.view_spotify_oauth_receive, name="oauth_spotify_receive"),
    path("oauth/spotify/update/", views.view_spotify_oauth_update, name="oauth_spotify_update"),
]
