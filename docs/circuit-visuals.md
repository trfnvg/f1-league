# Circuit selection and Nightshift graphics

In **Admin → Events → Add/change event**, choose **Гран-при / трасса**. The editor
shows a live SVG preview. An empty event name is filled from the selected GP;
an administrator's custom name is retained. The server also fills the name when
JavaScript is disabled. Race/prediction dates, round, season and sprint settings
remain explicitly entered: a circuit does not imply a calendar date.

The catalogue includes the 24 venues on the published 2026 calendar (including
Barcelona and Madrid separately), plus Imola, Portimão and Istanbul for reuse.
They are not tied to round numbers or to a particular season.

Each selection binds a distinct circuit outline to the hero, stage page, league
GP card and calendar thumbnails. Existing event cards resolve from Russian or
English names when `circuit` is blank. Explicit selection always wins. Unknown
custom races keep a neutral fallback rather than another circuit's geometry.
An ambiguous Spanish GP means Barcelona before 2026 and Madrid from 2026; an
explicit city/name or selected circuit takes priority.

The SVG is rendered on the server with complete local paths, without a drawing
intro. Animated previews show the season's DriverProfile roster (22 drivers in
2026) in the same team palette as the driver picker. The preview falls back to
2026 when the next season has no configured roster. Initial order is shuffled;
slightly different speeds and two offset racing lines produce decorative
overtakes, not live standings. Names and numbers are in each marker's SVG title.
Calendar miniatures remain static. Reduced motion freezes the markers in place.
One animation loop serves visible tracks only; it pauses in hidden tabs and
uses precomputed path samples rather than querying path geometry every frame.
Admin circuit changes invalidate those samples. There is no video, map SDK,
runtime network request or high-resolution bitmap.

## Geometry and attribution

Geographic geometry is adapted from [Tomislav Bacinger's f1-circuits](https://github.com/bacinger/f1-circuits),
MIT licensed, pinned at `8094e957b8d6aa8b9f4510c93968556cccd30e02`. The copyright
notice and full licence are in `league/data/CIRCUITS-LICENSE.txt`. The SVG paths
are geographic outlines projected to local coordinates, simplified at 0.65 SVG
units and fitted to a 620×370 canvas with padding. These are display graphics,
not FIA-homologated engineering maps. Source metadata supplies circuit lengths.
The calendar coverage was checked against [Formula 1's published calendar](https://www.formula1.com/en/latest/article/formula-1-reveals-calendar-for-2026-season.YctbMZWqBvrgyddrnauo8).

`tools/build_circuit_paths.py` prints an apply_patch patch to regenerate the
checked-in data from that pinned source. Production only reads local JSON.

## Verification

- `python manage.py test league.test_circuits league.test_home_featured_event`
- `python manage.py makemigrations --check --dry-run`
- `python tests/nightshift_browser.py --output-dir /tmp/fastlap-nightshift-ui`

The browser check renders real Django pages against an ephemeral in-memory DB;
it never migrates the user's database. It checks 320/390/768/1101/1440/1920-pixel
layouts, all 27 admin selections, custom-name preservation, SVG motion and
reduced motion, and saves screenshots including the full circuit gallery.
Playwright and Chromium are development-only requirements.
