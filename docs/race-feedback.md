# Race feedback

The shared `race-feedback.css` and `race-feedback.js` add finite, silent effects
to the existing Nightshift interface. They do not alter scoring or navigation.

- Successful prediction POSTs in global and private-league views emit a tagged
  Django message. Only this server receipt triggers the checkmark, radio pulse
  and temporary confirmed button state. Invalid submissions never show success.
  The existing unsaved-change warning and normal POST/redirect workflow remain.
- Visible standings numbers count up over 650 ms using one shared animation
  frame. Their final width is reserved before counting. Table rows, pinned
  columns and scroll positions never animate. Accessible labels contain the
  final scores throughout, including zero and negative results.
- Live Paddock keeps three transmissions visible, with the other two available
  through its existing toggle. Long messages have a separate disclosure button;
  the message link still opens the event/profile. New message identities receive
  a short waveform and a static unread marker. Polling does not replace a focused
  link or an expanded message. Seen identities are bounded to 40 per feed in
  session storage.
- Signed-in players see a finish card for their latest scored round on Home,
  using their selected league's score and movement. Scored event pages show the
  global result. Each result's checker sweep plays once per browser, keyed by
  player, league/global context, event and points, with the last 40 identities
  kept in local storage. Storage failures leave the final card visible without
  replaying effects. Rank movement is only shown when supplied by the standings.

`prefers-reduced-motion` disables the effects; backgrounding the page completes
active counters immediately. Without JavaScript, final scores and full messages
remain visible. No new dependencies, images, database migrations or API calls
are required.

Checks:

```sh
DATABASE_URL=sqlite:///:memory: /tmp/fastlap-nightshift-venv/bin/python manage.py test league --noinput
/tmp/fastlap-nightshift-venv/bin/python tests/nightshift_browser.py --output-dir /tmp/fastlap-feedback-ui --widths 390 1440
/tmp/fastlap-nightshift-venv/bin/python tests/nightshift_browser.py --output-dir /tmp/fastlap-feedback-webkit --widths 320 --browser webkit
```
