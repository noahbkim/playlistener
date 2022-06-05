from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("register/", views.RegistrationView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("oauth/spotify/", views.view_spotify_oauth, name="oauth_spotify"),
    path("oauth/spotify/receive/", views.view_spotify_oauth_receive, name="oauth_spotify_receive"),
    path("oauth/spotify/update/", views.view_spotify_oauth_update, name="oauth_spotify_update"),
]
