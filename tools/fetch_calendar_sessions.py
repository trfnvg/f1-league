"""Development-only: inspect official visible F1 schedules and emit a frozen JSON.

Never imported by Django/startup. No guessed hours: a structured timestamp is
accepted only when its date/time appears in the visible schedule as well.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"Practice 1": "practice1_at", "Practice 2": "practice2_at",
         "Practice 3": "practice3_at", "Sprint Qualifying": "sprint_qualifying_at",
         "Sprint": "sprint_at", "Qualifying": "qualifying_at", "Race": "race_at"}


class ScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.script = False
        self.kind = None
        self.buffer = []
        self.structured = []
        self.visible = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.script = True
            self.kind = dict(attrs).get("type")
            self.buffer = []

    def handle_endtag(self, tag):
        if tag == "script":
            if self.kind == "application/ld+json":
                self.structured.append(json.loads("".join(self.buffer)))
            self.script = False

    def handle_data(self, text):
        (self.buffer if self.script else self.visible).append(text)


def subevents(item):
    if isinstance(item, dict):
        if "subEvent" in item:
            yield from item["subEvent"]
        else:
            for value in item.values():
                yield from subevents(value)
    elif isinstance(item, list):
        for value in item:
            yield from subevents(value)


def inspect_round(race):
    parser = ScheduleParser()
    with urlopen(Request(race["source_url"], headers={"User-Agent": "FastlapCalendar/1.1"}), timeout=35) as response:
        parser.feed(response.read().decode())
    text = " ".join(" ".join(parser.visible).split())
    visible = text.split(" Schedule ", 1)[1].split("Full Schedule", 1)[0].replace("Chequered Flag ", "")
    values = {}
    for entry in subevents(parser.structured):
        label = entry.get("name", "").split(" - ", 1)[0]
        if label not in KINDS:
            continue
        at = datetime.fromisoformat(entry["startDate"].replace("Z", "+00:00"))
        expected = at.strftime("%d %b ") + label + " " + at.strftime("%H:%M")
        if expected not in visible:
            raise ValueError(f"Visible schedule does not confirm {race['circuit']}: {expected}")
        values[KINDS[label]] = at.astimezone(timezone.utc).isoformat()
    expected_fields = ({"practice1_at", "sprint_qualifying_at", "sprint_at", "qualifying_at", "race_at"}
                       if race["has_sprint"] else {"practice1_at", "practice2_at", "practice3_at", "qualifying_at", "race_at"})
    if set(values) != expected_fields:
        raise ValueError(f"Unexpected session format for {race['circuit']}: {sorted(values)}")
    for field in ("practice1_at", "race_at"):
        if datetime.fromisoformat(values[field]) != datetime.fromisoformat(race[field]):
            raise ValueError(f"Previously seeded {field} changed for {race['circuit']}; review manually")
    print(f"Verified {race['circuit']}: {len(values)} sessions", file=sys.stderr, flush=True)
    return {"season_year": race["season_year"], "circuit": race["circuit"],
            "source_url": race["source_url"], **values}


if __name__ == "__main__":
    snapshot = json.loads((ROOT / "league/data/race_calendar_20261028.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(inspect_round, snapshot["rounds"]))
    print(json.dumps({"checked_on": "2026-10-29", "note": "Official visible F1 schedules, UTC starts; five sessions per weekend.",
                      "rounds": rows}, ensure_ascii=False, indent=2))
