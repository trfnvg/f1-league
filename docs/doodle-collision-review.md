# Enemy landing review

Collision masks now use a 64×64 grid, generated once when artwork is decoded.
Transparent columns return no landing surface. The original artwork is unchanged.

Moving sprite landings sample the relative foot/sprite trajectory every two world
units, respecting horizontal mirroring and screen wrapping. Landing width covers
the player's damage ellipse, with a small 2–3 unit contact tolerance. Wheels,
hawks, falling tires, large carbon debris, summit drones/marmots and goats use
this contour test. Piranhas retain their stable body-only ellipse (wings remain
harmless); winter characters, Toto's open target and Sid's cans interpolate the
horizontal position at the crossing.

A successful enemy/debris stomp gives 0.12 seconds of protection so subsequent
collision passes cannot kill the player using the previous falling trajectory.
Within the enemy list, valid stomps take precedence over adjacent side contacts
regardless of spawn order. Ordinary platform jumps grant no extra protection.
Cones, small debris, projectiles and closed boss attack phases retain their rules.

Validation: native Canvas suite in mobile and desktop geometry, real artwork
contours and both facing directions, fast descents, transparent columns,
upward/side impacts, moving targets, all wheel variants, adjacent contacts,
existing winter/summit encounters and boss regressions. These are automated
simulations, not physical-device FPS measurements.
