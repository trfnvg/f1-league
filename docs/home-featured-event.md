# Homepage GP retention

The featured hero uses `league.home_events.select_featured_event`, independently
from the personal dashboard's next open prediction event. A GP with a race in
the current Moscow calendar week stays featured until Monday 00:00 MSK, even if
predictions closed or results were scored. A missing race time uses the prediction
deadline's week. Once that week ends, choose the earliest future open deadline;
if there are none, show the selected season's latest round. Empty seasons stay empty.

Only the selected season's events are passed to the helper. Display retention
does not reopen predictions, change duel/wheel deadlines, or alter scores.

Verification: `python manage.py test league.test_home_featured_event` covers
closed deadlines, scored Sundays, the exact Moscow Monday boundary, missing race
dates, upcoming/archive/empty fallbacks and selected-season isolation.
