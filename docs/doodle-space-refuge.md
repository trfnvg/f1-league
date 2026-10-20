# Space object continuity and Toto refuge — 2026-10-20

Space events and Toto no longer clear the enemies, hazards or hawks arrays at
spawn or each update. Existing events also keep updating, colliding and drawing
during Toto. Pit-stop landing no longer deletes world objects. New ordinary
enemy/hazard generation pauses during a space event or Toto; existing objects
remain live until normal collision or offscreen cleanup. Hawks crossing into
space now finish their flight instead of being abruptly cleared at the boundary.
Carbon showers finish only when all debris is hit or falls below the camera,
not after a fixed eleven seconds while debris may still be visible.

Each Toto warning chooses a nearby safe lane and creates or reuses a stationary
bridge 18 units below the player's feet, spanning the current position and the
lane's centre. Stationary normal platforms on fixed 150-world-unit rows fill
that lane above it; this is below the ~209-unit normal jump apex. The platform
width is at most one lane minus 12 units. The chain extends as the camera rises
through warning/volley, so the lane cannot run out of footholds mid-volley.
Existing platforms are preserved. Each three-wheel volley skips the chosen lane.
Repeated warnings reuse the same world rows and existing nearby stationary
footholds instead of adding duplicate ladders. Only the visible viewport plus
one extra row is filled. Nearby entry bridges are reused when they still cover
both the player and the safe lane.

Mobile camera tracking uses 38% of the visible height measured from the bottom
(hero at 62% from the top once settled), with faster follow during ascent. This
accounts for the top crop caused by browser chrome; desktop framing is unchanged.

This supplies a reachable route through Toto's volley; the player still needs
to move to it and avoid independent hazards already in flight. It does not grant
invulnerability or remove pre-existing threats. Toto and his lane-warning labels
now use the visible mobile canvas region rather than potentially clipped top
coordinates, matching the Sid viewport correction.

Native Canvas tests cover mobile/desktop preservation at event/boss spawn and
after full updates, live carbon movement/lifetime, pit-stop continuity, no new
stacked events, real bridge landing, lane-aligned stable platforms, volley
exclusion from the safe lane, and extending footholds after camera movement.
Additional checks cover twelve repeated warnings with stable platform count,
row spacing, and mobile camera framing at several full/cropped viewport sizes.
