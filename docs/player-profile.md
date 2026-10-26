# Player profile

`player_profile.html` uses a dedicated, scoped Nightshift layout in
`player-profile.css`. The previous inline styles, points chart and chart script,
wooden shelf, glow and hover-only trophy tooltips are removed.

The page shows identity and avatar editing, four compact season statistics,
recent scores, awards, event history, accuracy and season predictions. Rank
and event points refer to the global season standings; season-prediction points
remain visible on their own card. Trophy collection data retains its existing
all-time scope, award images, dates, attempts and staff preview handling.

Awards use responsive cards with visible metadata, including on touch screens.
Achievements keep their existing earned-state rules and assets. Event history
lists only events with a prediction (including a hidden one) or a score, newest
first. Native disclosure controls reveal individual answers without requiring JS.
Season prediction fields and factual comparisons use an extracted partial.

Privacy remains enforced in the view: other participants cannot see predictions
before deadlines; Crazy Prediction stays hidden during anonymous voting.
Only the owner gets avatar upload and logout controls. Avatar input, validation,
CSRF and POST permissions are unchanged; the avatar menu script is now cached as
`player-profile.js`.

Browser coverage includes real multiple-trophy content, owner upload controls,
Escape dismissal, event disclosures and mobile/desktop layout. Backend tests
cover privacy, award information and newest-first ordering without empty future
events.
