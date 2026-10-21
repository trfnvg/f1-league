# Mountain boss: readable snow attacks

Replaces the bubble curtain with four non-overlapping attacks. One attack per cycle in phase one; two in later phases; four-second medal opening follows only after all projectiles exit. Rotation avoids consecutive repeats. Eight boss HP, three player lives and 1.6-second damage grace remain.

- Snake: one six-segment horizontal chain at fixed height, 125 units/s, distinguishable head. Tail starts outside the arena and is retained until it enters and exits. A 1.5-second edge warning marks height/direction. Standing still after landing during the snake lets the hero wait on a platform; steering restarts the regular 720-unit jump. Waiting ends automatically when the snake is over. Low and upper ledges allow waiting below/above it.
- BAN: two fixed columns, marked at warning time. The nearest ledge's column stays clear. Plates fall at 180 units/s.
- Fan (phase two): three snowballs, 135 units/s, directions separated by 0.6 radians, aimed at the position captured before the 1.5-second warning. No tracking.
- Slam (phase three): distinct lift/drop animation, two low shock fronts after impact. The bathtub itself is cosmetic, so its drop cannot create an untelegraphed body hit. Upper ledges remain safe.

Snowballs/head are drawn as crisp code-native pixel shapes with small solid hitboxes, using relative swept collision. No additional image download. Attack preparation uses distinct existing boss poses. The alpine background, HUD offset below the scoreboard, cabin, medal reward, eagle finale and admin isolation remain. Resize maps warning/aim/shot coordinates and clears stale platform references.

Native Canvas suite checks mobile and desktop: actual ledge-to-medal jumps, eight hits and ending; all four forced attacks, 1.5-second warnings, fixed targets, one snake head and six segments, stationary waiting, bounded projectiles and full cleanup before counterattack. These are automated checks, not physical phone gameplay tests.
