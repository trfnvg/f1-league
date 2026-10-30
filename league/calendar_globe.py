"""Local, read-only globe data; schedules/covers stay owned by the calendar."""
from django.templatetags.static import static
from django.urls import reverse
from .circuits import resolve_circuit

# Circuit centres from bacinger/f1-circuits/f1-locations.json (MIT).
# Same source/license as data/circuits.json; see data/CIRCUITS-LICENSE.txt.
COORDINATES = {
    'melbourne': (-37.846, 144.970), 'shanghai': (31.340, 121.221),
    'suzuka': (34.844, 136.534), 'bahrain': (26.031, 50.512),
    'jeddah': (21.632, 39.104), 'miami': (25.958, -80.239),
    'montreal': (45.506, -73.525), 'monaco': (43.737, 7.429),
    'barcelona': (41.569, 2.259), 'spielberg': (47.223, 14.761),
    'silverstone': (52.072, -1.017), 'spa': (50.436, 5.971),
    'hungaroring': (47.583, 19.250), 'zandvoort': (52.389, 4.541),
    'monza': (45.621, 9.290), 'madrid': (40.471, -3.620),
    'baku': (40.369, 49.842), 'sepang': (2.761, 101.738),
    'singapore': (1.291, 103.859), 'austin': (30.135, -97.633),
    'mexico': (19.402, -99.091), 'interlagos': (-23.702, -46.698),
    'las-vegas': (36.116, -115.168), 'lusail': (25.490, 51.454),
    'yas-marina': (24.471, 54.601), 'imola': (44.341, 11.713),
    'portimao': (37.232, -8.628), 'istanbul': (40.958, 29.412),
}


def globe_rounds(rounds):
    result = []
    for race in rounds:
        if race.circuit not in COORDINATES:
            continue
        circuit = resolve_circuit(race.circuit, race.title, race.season_year)
        lat, lon = COORDINATES[race.circuit]
        result.append({
            'key': race.circuit, 'round': race.round_number, 'title': race.title,
            'location': race.location, 'country': race.country,
            'circuit': race.circuit_name, 'lat': lat, 'lon': lon,
            'dates': f'{race.starts_on:%d.%m} — {race.ends_on:%d.%m.%Y}',
            'raceAt': race.race_at.isoformat() if race.race_at else None,
            'timezone': race.venue_timezone, 'finished': race.is_finished,
            'next': race.is_next, 'sprint': race.has_sprint,
            'cover': race.cover_url or (static(race.photo_static) if race.photo_static else ''),
            'url': reverse('league:event_detail', args=[race.linked_event.pk]) if race.linked_event else race.source_url,
            'external': not bool(race.linked_event),
            'track': circuit['path'] if circuit else '',
            'sessions': [{'code': row['code'], 'label': row['label'],
                'at': row['at'].isoformat() if row['at'] else None} for row in race.session_rows],
        })
    return result
