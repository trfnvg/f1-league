"""Print an apply_patch patch for the checked-in circuit outlines and licence.

Run with Python 3; no Django or third-party geometry packages are required.
Source is pinned so regeneration never silently changes a circuit layout.
"""
import json
import math
import urllib.request

REVISION = "8094e957b8d6aa8b9f4510c93968556cccd30e02"
SOURCE = f"https://raw.githubusercontent.com/bacinger/f1-circuits/{REVISION}/"
KEYS = dict(zip(
    "au-1953 cn-2004 jp-1962 bh-2002 sa-2021 us-2022 ca-1978 mc-1929 es-1991 at-1969 gb-1948 be-1925 hu-1986 nl-1948 it-1922 es-2026 az-2016 sg-2008 us-2012 mx-1962 br-1940 us-2023 qa-2004 ae-2009 it-1953 pt-2008 tr-2005".split(),
    "melbourne shanghai suzuka bahrain jeddah miami montreal monaco barcelona spielberg silverstone spa hungaroring zandvoort monza madrid baku singapore austin mexico interlagos las-vegas lusail yas-marina imola portimao istanbul".split(),
))


def simplify(points, tolerance=0.65):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    size = dx * dx + dy * dy
    distances = []
    for x, y in points[1:-1]:
        t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / size)) if size else 0
        distances.append(math.hypot(x - a[0] - t * dx, y - a[1] - t * dy))
    distance = max(distances)
    index = distances.index(distance) + 1
    return simplify(points[:index + 1])[:-1] + simplify(points[index:]) if distance > tolerance else [a, b]


def render(feature):
    coords = feature["geometry"]["coordinates"]
    latitude = sum(p[1] for p in coords) / len(coords)
    points = [(p[0] * math.cos(math.radians(latitude)), -p[1]) for p in coords]
    xs, ys = zip(*points)
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    scale = min(520 / width, 280 / height)
    left, top = (620 - width * scale) / 2, (370 - height * scale) / 2
    points = simplify([((x - min(xs)) * scale + left, (y - min(ys)) * scale + top) for x, y in points])
    commands = [f"{x:.1f},{y:.1f}" for x, y in points]
    props = feature["properties"]
    return {"name": props["Name"], "length_km": f"{props['length'] / 1000:.3f}",
            "path": "M" + " L".join(commands) + " Z", "start_x": round(points[0][0], 1),
            "start_y": round(points[0][1], 1)}


if __name__ == "__main__":
    with urllib.request.urlopen(SOURCE + "f1-circuits.geojson", timeout=30) as response:
        features = json.load(response)["features"]
    data = {KEYS[f["properties"]["id"]]: render(f) for f in features if f["properties"]["id"] in KEYS}
    assert len(data) == len(KEYS)
    with urllib.request.urlopen(SOURCE + "LICENSE.md", timeout=30) as response:
        licence = response.read().decode()
    print("*** Begin Patch")
    for filename, content in (("league/data/circuits.json", json.dumps(data, ensure_ascii=False, indent=2)),
                              ("league/data/CIRCUITS-LICENSE.txt", licence)):
        print(f"*** Add File: {filename}")
        print("\n".join("+" + line for line in content.splitlines()))
    print("*** End Patch")
