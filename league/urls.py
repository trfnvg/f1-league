from django.urls import path
from . import views

app_name = "league"

urlpatterns = [
    path("", views.home, name="home"),
    path("activity-feed/", views.activity_feed_updates, name="activity_feed"),
    path("events/<int:event_id>/crazy-vote/", views.cast_crazy_vote, name="crazy_prediction_vote"),
    path("paddock-jury/", views.paddock_jury_admin, name="paddock_jury_admin"),
    path("paddock-jury/<int:event_id>/close/", views.close_crazy_vote, name="close_crazy_vote"),
    path("arcade/", views.arcade, name="arcade"),
    path("arcade/doodle-jump/", views.arcade_doodle_jump, name="arcade_doodle_jump"),
    path("arcade/doodle-jump/leaderboard/", views.doodle_leaderboard, name="doodle_leaderboard"),
    path("arcade/doodle-jump/attempt/start/", views.doodle_attempt_start, name="doodle_attempt_start"),
    path("arcade/doodle-jump/attempt/finish/", views.doodle_attempt_finish, name="doodle_attempt_finish"),
    path("arcade/leaderboard/", views.arcade_leaderboard, name="arcade_leaderboard"),
    path("arcade/minesweeper/leaderboard/", views.minesweeper_leaderboard, name="minesweeper_leaderboard"),
    path("arcade/minesweeper/attempt/start/", views.minesweeper_attempt_start, name="minesweeper_attempt_start"),
    path("arcade/minesweeper/attempt/finish/", views.minesweeper_attempt_finish, name="minesweeper_attempt_finish"),
    path("arcade/wheel/test/", views.arcade_wheel_test, name="arcade_wheel_test"),
    path("arcade/run/start/", views.arcade_run_start, name="arcade_run_start"),
    path("arcade/run/finish/", views.arcade_run_finish, name="arcade_run_finish"),
    path("arcade/wheel/spin/", views.arcade_wheel_spin, name="arcade_wheel_spin"),
    path("arcade/wheel/activate/", views.arcade_wheel_activate, name="arcade_wheel_activate"),
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
