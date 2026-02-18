from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]