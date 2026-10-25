# Current GP on the Nightshift homepage

The featured circuit follows `league.home_events.select_featured_event`. It is
the nearest race whose `race_datetime + 2 hours` is still in the future. Closing
the prediction deadline, the race start or early publication of scores does not
switch the circuit to next week's GP. At start + 2 hours, it moves to the next
race. A missing race time uses prediction deadline + 2 hours as a display-only
fallback. The homepage, sidebar, mobile navigation and league card all use the
same `select_current_event` helper. This replaces Monday-based retention and the
previous immediate race-start switch.

If there are no future races, show the selected season's latest round as an
archive. An empty season shows an empty-state card. All comparisons use aware
timestamps and only events from the selected season. Neither display selection
nor the race countdown reopens predictions or changes scores, wheel or duels.

The main timer always counts down to the race start, with labelled days, hours,
minutes and seconds. It updates every second using timestamps rather than a
decrementing counter, and resumes correctly after a hidden tab. At the start it
shows “Гонка идёт”; the homepage reloads once at the two-hour boundary to display
the next GP. When a race time is missing, it says “Время уточняется”. Prediction
availability and the prediction deadline are separate text, not progress bars.
The position tile shows the league name and labelled points behind the leader.

The homepage uses the current user's remembered league (only if they are still
an active, enrolled member), otherwise their first league in the selected season.
Its ranking and metrics come from that league's existing score projection. Users
without a league see the existing overall standings. No demo scores or claims of
prediction accuracy are included. Live Paddock retains the five-item feed.

The navigation's overall ranking has its own `/ranking/` URL, accessible even to
league members. The old `/leaderboard/` redirects remain for existing links.

Verification: `python manage.py test league.test_home_featured_event league.test_circuits`.

## Forecast availability and profile navigation

An event card with status OPEN accepts forecasts immediately upon creation,
including far-future races. There is no seven-day opening gate. At the exact
prediction deadline it closes; LOCKED and SCORED cards stay closed. The shared
submission service still locks the event and enforces the deadline on the server.

Season forecasts are accessed from a player's profile, not a separate navigation
tab. Own forecasts remain editable before their season deadline through the
profile's action; other players' answers remain hidden until that deadline.
The sidebar profile button renders the stored avatar with the same centred
circular crop as elsewhere.

Stage heroes have an explicit grid, a cover that fits without cropping, a
circuit or round-number fallback, and no hidden/reveal animation dependency.
Failed cover requests reveal the fallback. Calendar covers use a 16:9 frame and
`object-fit: contain`, so the entire uploaded artwork remains visible.

## Desktop blank-page regression

Both the event template and base template used to contain UTF-8 byte-order marks.
Together these emitted two U+FEFF characters before the doctype. Browsers parsed
the second as body content, ignored the doctype and enabled quirks mode; desktop
WebKit expanded the live event page to approximately 27,000 pixels. All affected
templates now omit the marks. The regression test checks template prefixes and
rendered doctypes; browser tests assert standards mode and a real `head title`
on open and closed event pages, as well as other shared-layout pages.
