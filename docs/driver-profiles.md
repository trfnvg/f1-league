# Season driver profiles

`DriverProfile` stores a season, prediction key, full name, surname, team,
race number, official portrait URL, optional uploaded portrait and source page.
The prediction key stays identical to `DRIVER_CHOICES`; old forecasts do not
change when a profile is edited. Profiles are unique by season and key.

Migration 0050 creates all 22 profiles for 2026 without network access. The
roster and every portrait path were checked against the official F1 directory
on 2026-10-26:

- https://www.formula1.com/en/drivers
- https://www.redbull.com/int-en/f1-driver-numbers-overview-max-verstappen

Official portraits are served from F1's media CDN in the browser. An uploaded
portrait takes precedence. If an image fails, the picker remains usable with
initials. The official source is a full driver portrait; the photo getter asks
the same CDN for a 440×440 face-centred crop. The original source URL is retained
in the database. Uploaded portraits use a square CSS crop. Picker, category and
profile images all use square frames.

Staff manage profiles under **Профили гонщиков** in Django admin. A new season
gets its own rows; missing historical portraits are not substituted with a
different season. The public directory is `/drivers/?season=2026`, and an
individual profile is `/drivers/2026/russell/`.

The GP form embeds only that event season's metadata with `json_script`.
Podium, pole, fastest lap, driver of the day and sprint driver fields share one
native modal dialog. Search matches name, team, number and prediction key.
Duplicate podium selections are disabled; other categories may reuse a driver.
Original named Django select fields receive the selection and the backend
remains authoritative. Without dialog/JS support the native form stays visible.

The dialog closes by its close button, Escape or a click on the backdrop; native
dialog focus management returns focus to the category button. On touch devices
search is not automatically focused, avoiding an unnecessary onscreen keyboard.

Deployment uses the existing `start.sh` migration step; it must run before the
new application starts serving requests.
