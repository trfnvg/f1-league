# Player arcade review — 2026-10-17

Shared player styles in `arcade-player.css` unify the library, both game pages,
play/login buttons and leaderboard columns. The canvas and fullscreen geometry
remain controlled by each game's stylesheet. Rank, name, score and attempts use
fixed column widths with a flexible, ellipsized name column on small screens.
Focus states and reduced-motion handling are included.

Fixed all-time rank calculation below the visible top ten, including the existing
score/time/user-ID tie order. The current event/global selection remains intact.

Hawks use one fixed source pose for drawing and collision. Descending feet can
bounce from their alpha contour, accounting for motion, screen wrap and mirrored
flight direction; side contact remains dangerous. Player input speed is 1.2 times
the previous target speed on both world widths.

Validation: 14 Django arcade-library tests; native Canvas regression suite with
new mobile/desktop movement and mirrored hawk landing cases; local headless
Chromium screenshots of populated leaderboards and library at 390 and 1440 CSS
pixels, including a long nickname, with no document horizontal overflow.
This is not an actual-device FPS benchmark or a confirmation of Render deployment.
