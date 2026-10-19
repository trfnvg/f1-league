# Arrival and mobile viewport fixes — 2026-10-19

- Increase falling wheel/cone world spacing from 430 to 560 before space;
  later biomes keep their existing spacing.
- Portal arrival clears old space objects and builds a broad normal landing
  platform plus a reachable ladder of normal platforms. The racer stays still
  during the 0.6-second arrival fade. New hazards/enemies wait until the arrival
  notice ends. Score history and the current world camera remain intact.
- Mobile world height derives from physical screen aspect, clamped to 1.4–2.5,
  rather than zoom-dependent CSS bounds. The canvas uniformly fits this stable
  view; changing browser zoom cannot reveal extra world above. Original artwork
  and high-density rendering are retained. Desktop sizing is unchanged.

Native Canvas regression coverage includes mobile bounds changes representing
zoom, the arrival platform and held fade, and continued play after arrival, in
addition to existing chapter, boss, collision and streaming tests. This addresses
viewport resizing, not arbitrary modification of client-side game code.
