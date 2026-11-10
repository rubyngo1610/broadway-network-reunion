"""Step 14: vector basemap of Manhattan (Battery to ~100th St) for the zoomable views in viz/.

Sources (downloaded once into data/raw/basemap/, then reused):
  boroughs.geojson   NYC Open Data, Borough Boundaries clipped to shoreline (dataset gthc-hcne)
  osm_midtown.json   OpenStreetMap via the Overpass API: streets and named parks in the bounding box

Writes viz/data/basemap.json:
  land      one entry per borough: {name, rings}, rings simplified; Manhattan first
  parks     named parks in Manhattan: {name, rings}
  streets   {major: [lines], minor: [lines]}; each line is a list of [lon, lat], Manhattan only
  labels    squares and landmarks for orientation: {name, lat, lon, kind}

Coordinates are rounded to 5 decimals (about 1 m) and simplified with Ramer-Douglas-Peucker.
Map data: OpenStreetMap contributors (ODbL); NYC Department of City Planning (NYC Open Data).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

import config
from src.common import log, parse_args

RAW = config.DATA_RAW / "basemap"
OUT = config.ROOT / "viz" / "data" / "basemap.json"
BBOX = (40.700, -74.025, 40.800, -73.925)   # south, west, north, east
UA = "NYU DS-GA 3001 class project basemap (python-requests)"

BOROUGHS_URL = "https://data.cityofnewyork.us/resource/gthc-hcne.geojson?$limit=10"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = f"""[out:json][timeout:120];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|pedestrian)$"]["area"!="yes"]{BBOX};
  way["leisure"="park"]["name"]{BBOX};
  relation["leisure"="park"]["name"]{BBOX};
);
out geom tags;"""

MAJOR = {"motorway", "trunk", "primary", "secondary"}

# Orientation labels (hand-placed). "kind" lets the page style squares and landmarks differently.
LABELS = [
    {"name": "Union Square", "lat": 40.7359, "lon": -73.9906, "kind": "square"},
    {"name": "Madison Square", "lat": 40.7420, "lon": -73.9878, "kind": "square"},
    {"name": "Herald Square", "lat": 40.7500, "lon": -73.9878, "kind": "square"},
    {"name": "Times Square", "lat": 40.7580, "lon": -73.9855, "kind": "square"},
    {"name": "Columbus Circle", "lat": 40.7681, "lon": -73.9819, "kind": "square"},
    {"name": "Lincoln Center", "lat": 40.7725, "lon": -73.9835, "kind": "landmark"},
    {"name": "Central Park", "lat": 40.7790, "lon": -73.9665, "kind": "park"},
    {"name": "Hudson River", "lat": 40.7600, "lon": -74.0100, "kind": "water"},
    {"name": "East River", "lat": 40.7450, "lon": -73.9640, "kind": "water"},
]


def fetch(path: Path, fn):
    if path.exists():
        return json.loads(path.read_text())
    log.info("Downloading %s", path.name)
    data = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def get_boroughs():
    r = requests.get(BOROUGHS_URL, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    return r.json()


def get_osm():
    r = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, headers={"User-Agent": UA}, timeout=200)
    r.raise_for_status()
    return r.json()


def get_relations(ids):
    """Park relations whose member geometry the bbox query left out: fetch them by id."""
    def fn():
        q = f"[out:json][timeout:120];rel(id:{','.join(map(str, ids))});out geom;"
        r = requests.post(OVERPASS_URL, data={"data": q}, headers={"User-Agent": UA}, timeout=200)
        r.raise_for_status()
        return r.json()
    return fn


def assemble_rings(ways):
    """Join open way segments end to end into closed rings (OSM multipolygon outers)."""
    segs = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if ring[0] == ring[-1] and len(ring) > 3:
            rings.append(ring)
    return rings


def rdp(points, eps):
    """Ramer-Douglas-Peucker simplification (iterative), points = [[x, y], ...]."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x0, y0 = points[i]
            if norm < 1e-12:   # closed ring: first and last point coincide, use distance to that point
                d = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
            else:
                d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, i
        if idx is not None and best > eps:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def rnd(points):
    return [[round(x, 5), round(y, 5)] for x, y in points]


def in_bbox(ring, pad=0.02):
    s, w, n, e = BBOX
    return any(s - pad <= y <= n + pad and w - pad <= x <= e + pad for x, y in ring)


def point_in_rings(x, y, rings):
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
                inside = not inside
            j = i
    return inside


def main():
    parse_args(__doc__.splitlines()[0])
    boroughs = fetch(RAW / "boroughs.geojson", get_boroughs)
    osm = fetch(RAW / "osm_midtown.json", get_osm)

    # land: every borough ring that reaches the box; Manhattan first so it draws on top
    land, manhattan_rings = [], []
    for f in sorted(boroughs["features"], key=lambda f: f["properties"]["boroname"] != "Manhattan"):
        name = f["properties"]["boroname"]
        rings = []
        for poly in f["geometry"]["coordinates"]:
            outer = poly[0]
            if in_bbox(outer):
                rings.append(rnd(rdp(outer, 0.00006)))
        if rings:
            land.append({"name": name, "rings": rings})
            if name == "Manhattan":
                manhattan_rings = rings

    def in_manhattan(coords):
        x, y = coords[len(coords) // 2]
        return point_in_rings(x, y, manhattan_rings)

    # relations returned without member geometry are fetched again by id (cached)
    missing = sorted(e["id"] for e in osm["elements"]
                     if e["type"] == "relation" and not any(m.get("geometry") for m in e.get("members", [])))
    if missing:
        full = {e["id"]: e for e in fetch(RAW / "osm_park_relations.json", get_relations(missing))["elements"]}
        osm["elements"] = [full.get(e["id"], e) if e["type"] == "relation" else e for e in osm["elements"]]

    streets = {"major": [], "minor": []}
    parks = []
    for el in osm["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "way" and "highway" in tags:
            coords = [[p["lon"], p["lat"]] for p in el.get("geometry", [])]
            if len(coords) < 2 or not in_manhattan(coords):
                continue
            cls = "major" if tags["highway"] in MAJOR else "minor"
            streets[cls].append(rnd(rdp(coords, 0.00002)))
        elif tags.get("leisure") == "park":
            if el["type"] == "way":
                rings = [[[p["lon"], p["lat"]] for p in el.get("geometry", [])]]
            else:  # relation: join its outer member ways into closed rings
                rings = assemble_rings([[[p["lon"], p["lat"]] for p in m.get("geometry", [])]
                                        for m in el.get("members", [])
                                        if m.get("role") in ("outer", "") and m.get("geometry")])
            rings = [rnd(rdp(r, 0.00003)) for r in rings if len(r) > 3 and in_manhattan(r)]
            if rings:
                parks.append({"name": tags.get("name"), "rings": rings})

    out = {"bbox": BBOX, "land": land, "parks": parks, "streets": streets, "labels": LABELS,
           "attribution": "Map data © OpenStreetMap contributors (ODbL); borough boundaries: NYC Department of City Planning."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, separators=(",", ":"))
    OUT.write_text(text)
    n_pts = sum(len(l) for v in streets.values() for l in v)
    log.info("Wrote viz/data/basemap.json (%.0f KB): %d land rings, %d parks, %d major + %d minor street lines (%d points)",
             len(text) / 1024, sum(len(l["rings"]) for l in land), len(parks),
             len(streets["major"]), len(streets["minor"]), n_pts)


if __name__ == "__main__":
    main()
