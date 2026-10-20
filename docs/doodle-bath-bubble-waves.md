# Dynamic mountain arena encounter

Replaces the low-jump/single-spring encounter from v64. All arena platforms now give the regular 720-unit jump. Four alternating ledges, spaced at 11.5% of visible arena height (max 100 units), provide a reachable climb. The medal counterattack sits above the upper ledge; no friendly bubble springs remain.

The boss sends horizontal curtains of hostile pink-rimmed bubbles. Each curtain has a fixed vertical opening, telegraphed at its entry edge for one second. Opening height cycles across three elevations; entry sides alternate. All bubbles in a curtain move together, preserving the opening throughout its passage. Phase 1/2/3 sends 1/2/3 curtains per cycle at 120/135/150 units per second; phase 2 and 3 also apply temporary slippery foam. Each curtain crosses before another is released. A 4.5-second medal window follows the last curtain. Three player lives, eight boss HP, locked score and the eagle finale remain. Hostile bubbles use a reduced solid circular hitbox and relative swept movement, including horizontal projectile travel.

Boss HUD position now includes the actual HTML scoreboard height (including CSS safe-area padding), converted to world units using the canvas display scale. The HUD is below both the cropped canvas top and the score overlay, with compact scaling for short landscape viewports. The boss resting position reserves that space. Resize also maps the announced wave opening together with its projectiles.

Native Canvas checks cover mobile/desktop, an 84px top overlay, rotated/cropped screens, a real full-height ledge-to-medal jump, each wave's persistent opening and horizontal speed, three-hit damage, eight boss impacts, finale and admin isolation. Device FPS and physical iPhone rendering require device validation.
