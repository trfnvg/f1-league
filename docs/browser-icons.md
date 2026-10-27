# Browser icons

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

Validation covers public and admin icon links and the binary root icon.
See `league/test_brand.py` and `tests/nightshift_browser.py`.
