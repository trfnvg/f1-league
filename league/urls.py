from django.urls import path
from . import views
from . import arcade_library
from . import jury_admin
from . import league_views
from . import driver_profiles
from . import auth_views

app_name = "league"

urlpatterns = [
    path("drivers/", driver_profiles.directory, name="drivers"),
    path("drivers/<int:year>/<slug:key>/", driver_profiles.detail, name="driver_profile"),
    path("leagues/", league_views.index, name="friend_leagues"),
    path("leagues/new/", league_views.create, name="friend_league_create"),
    path("leagues/join/<str:token>/", league_views.join, name="friend_league_join"),
    path("leagues/<uuid:league_id>/", league_views.detail, name="friend_league"),
    path("leagues/<uuid:league_id>/settings/", league_views.settings, name="friend_league_settings"),
    path("leagues/<uuid:league_id>/delete/", league_views.delete, name="friend_league_delete"),
    path("leagues/<uuid:league_id>/events/<int:event_id>/day/", league_views.day_decision, name="friend_league_day"),
    path("leagues/<uuid:league_id>/invites/", league_views.invites, name="friend_league_invites"),
    path("leagues/<uuid:league_id>/invites/<int:invite_id>/revoke/", league_views.revoke, name="friend_league_revoke"),
    path("leagues/<uuid:league_id>/members/<int:membership_id>/role/", league_views.role, name="friend_league_role"),
    path("leagues/<uuid:league_id>/events/<int:event_id>/", league_views.event_detail, name="friend_league_event"),
    path("leagues/<uuid:league_id>/events/<int:event_id>/judge/<int:entry_id>/", league_views.judge, name="friend_league_judge"),
    path("leagues/<uuid:league_id>/events/<int:event_id>/recalculate/", league_views.recalculate, name="friend_league_recalculate"),
    path("", views.home, name="home"),
    path("activity-feed/", views.activity_feed_updates, name="activity_feed"),
    path("events/<int:event_id>/crazy-vote/", views.cast_crazy_vote, name="crazy_prediction_vote"),
    path("paddock-jury/", views.paddock_jury_admin, name="paddock_jury_admin"),
    path("paddock-jury/<int:event_id>/cancel/", jury_admin.cancel_exclusion, name="cancel_crazy_exclusion"),
    path("paddock-jury/<int:event_id>/close/", views.close_crazy_vote, name="close_crazy_vote"),
    path("arcade/", arcade_library.library, name="arcade"),
    path("arcade/control/", arcade_library.control, name="arcade_control"),
    path("arcade/lab/minesweeper/", arcade_library.minesweeper_preview, name="arcade_minesweeper_preview"),
    path("arcade/play/<str:game_key>/", arcade_library.game, name="arcade_game"),
    path("arcade/doodle-jump/", arcade_library.doodle_page, name="arcade_doodle_jump"),
    path("arcade/doodle-jump/leaderboard/", arcade_library.leaderboard, {"game_key": "doodle_jump"}, name="doodle_leaderboard"),
    path("arcade/doodle-jump/attempt/start/", arcade_library.attempt_start, {"game_key": "doodle_jump"}, name="doodle_attempt_start"),
    path("arcade/doodle-jump/attempt/finish/", arcade_library.attempt_finish, {"game_key": "doodle_jump"}, name="doodle_attempt_finish"),
    path("arcade/leaderboard/", arcade_library.leaderboard, name="arcade_leaderboard"),
    path("arcade/minesweeper/leaderboard/", views.minesweeper_leaderboard, name="minesweeper_leaderboard"),
    path("arcade/minesweeper/attempt/start/", views.minesweeper_attempt_start, name="minesweeper_attempt_start"),
    path("arcade/minesweeper/attempt/finish/", views.minesweeper_attempt_finish, name="minesweeper_attempt_finish"),
    path("arcade/wheel/test/", views.arcade_wheel_test, name="arcade_wheel_test"),
    path("arcade/run/start/", arcade_library.attempt_start, name="arcade_run_start"),
    path("arcade/run/finish/", arcade_library.attempt_finish, name="arcade_run_finish"),
    path("arcade/wheel/spin/", views.arcade_wheel_spin, name="arcade_wheel_spin"),
    path("arcade/wheel/activate/", views.arcade_wheel_activate, name="arcade_wheel_activate"),
    path("duel/", views.duel, name="duel"),
    path("season-predictions/", views.season_predictions, name="season_predictions"),
    path("register/", views.register, name="register"),
    path("account/settings/", auth_views.account_settings, name="account_settings"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/wildcard/draw/", views.draw_event_wildcard, name="draw_event_wildcard"),
    path("events/<int:event_id>/wildcard/answer/", views.answer_event_wildcard, name="answer_event_wildcard"),
    path("events/<int:event_id>/duels/create/", views.create_event_duel, name="create_event_duel"),
    path("duels/<int:duel_id>/cancel/", views.cancel_event_duel, name="cancel_event_duel"),
    path("duels/<int:duel_id>/<str:action>/", views.respond_event_duel, name="respond_event_duel"),
    path("players/<int:user_id>/", views.player_profile, name="player_profile"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("ranking/", views.leaderboard, {"force_global": True}, name="global_leaderboard"),
]
