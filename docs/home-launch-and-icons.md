# Homepage start and browser icons

The homepage introduction includes a responsive inline SVG Formula-style car.
One 2.3-second sequence reveals its bodywork, lights five lamps sequentially,
switches all lamps off at 1.55 seconds, and accelerates the car off-screen.
A short trail resolves into the heading's underline. A faint stationary car
schematic remains, with a replay button. On subsequent page loads the full
static car appears immediately.

Autoplay runs once per tab session, recorded under `fastlap:home-launch:v1` in
session storage. It starts only when the scene enters the viewport. With storage
unavailable, unsupported observation, or reduced motion, the static illustration
remains. Hidden pages finish the sequence immediately. There is no ongoing
animation loop, audio, extra image download, or layout change.

Browser icons share `site_icons.html` across the public layout and the admin
layout. PNG variants at 32 and 48 px use content-hashed static URLs in production;
an ICO fallback is available at the public `/favicon.ico` route. Previously that
standard path returned 404, and admin pages had no explicit brand icon links.
The route supports GET/HEAD, returns `image/x-icon`, and caches publicly for one
hour. The existing centered SVG remains the source for generated assets; it is
no longer offered as a competing browser icon. Regenerate PNG/ICO/Apple assets
with `python scripts/build_brand_icons.py` in the development environment.

The admin template override is in the project-level `templates` directory and
extends Django's original admin template to preserve its branding and behavior.

Validation covers public and admin icon links, the binary root icon, mobile and
desktop start/replay behavior, stable layout, one-time autoplay, and reduced
motion. See `league/test_brand.py` and `tests/nightshift_browser.py`.
