from django.urls import path
from . import views

app_name = "league"

urlpatterns = [
    path("", views.home, name="home"),
    path("arcade/", views.arcade, name="arcade"),
    path("arcade/leaderboard/", views.arcade_leaderboard, name="arcade_leaderboard"),
    path("arcade/run/start/", views.arcade_run_start, name="arcade_run_start"),
    path("arcade/run/finish/", views.arcade_run_finish, name="arcade_run_finish"),
    path("arcade/wheel/spin/", views.arcade_wheel_spin, name="arcade_wheel_spin"),
    path("arcade/wheel/activate/", views.arcade_wheel_activate, name="arcade_wheel_activate"),
    path("participants/", views.participants, name="participants"),
    path("duel/", views.duel, name="duel"),
    path("season-predictions/", views.season_predictions, name="season_predictions"),
    path("register/", views.register, name="register"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/wildcard/draw/", views.draw_event_wildcard, name="draw_event_wildcard"),
    path("events/<int:event_id>/wildcard/answer/", views.answer_event_wildcard, name="answer_event_wildcard"),
    path("events/<int:event_id>/duels/create/", views.create_event_duel, name="create_event_duel"),
    path("duels/<int:duel_id>/cancel/", views.cancel_event_duel, name="cancel_event_duel"),
    path("duels/<int:duel_id>/<str:action>/", views.respond_event_duel, name="respond_event_duel"),
    path("players/<int:user_id>/", views.player_profile, name="player_profile"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]
