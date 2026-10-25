# Current GP on the Nightshift homepage

The featured circuit follows `league.home_events.select_featured_event`. It is
the earliest unscored race whose `race_datetime` is still in the future. Closing
the prediction deadline does not switch the circuit to next week's GP. At the
race deadline the hero moves to the next race; a missing race time falls back to
the prediction deadline. This replaces the previous Monday-based retention rule.

If there are no future races, show the selected season's latest round as an
archive. An empty season shows an empty-state card. All comparisons use aware
timestamps and only events from the selected season. Neither display selection
nor the race countdown reopens predictions or changes scores, wheel or duels.

The timer counts down to the prediction deadline while predictions are open,
otherwise to the race start. The CTA reflects the real voting state.

The homepage uses the current user's remembered league (only if they are still
an active, enrolled member), otherwise their first league in the selected season.
Its ranking and metrics come from that league's existing score projection. Users
without a league see the existing overall standings. No demo scores or claims of
prediction accuracy are included. Live Paddock retains the five-item feed.

The navigation's overall ranking has its own `/ranking/` URL, accessible even to
league members. The old `/leaderboard/` redirects remain for existing links.

Verification: `python manage.py test league.test_home_featured_event league.test_circuits`.
