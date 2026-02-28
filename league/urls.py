from django.urls import path
from . import views

app_name = "league"

urlpatterns = [
    path("", views.home, name="home"),
    path("participants/", views.participants, name="participants"),
    path("season-predictions/", views.season_predictions, name="season_predictions"),
    path("register/", views.register, name="register"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("players/<int:user_id>/", views.player_profile, name="player_profile"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]
