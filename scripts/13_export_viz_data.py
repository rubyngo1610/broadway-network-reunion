"""Step 13: export small JSON files for the web views in viz/ (the views never read parquet).

Reads the outputs of steps 05, 08 and 09 and writes, to viz/data/:
  meta.json       generation date, counts, time-window settings, coverage notes
  theatres.json   one object per theatre: id, name, lat, lon, opened, demolished, first_show, last_show, n_shows
  shows.json      one object per core show: id, title, year, venue (theatre id or null), wiki
  people.json     one object per person in the network: id, name, born, died, birthplace, lat, lon, wiki
  credits.json    one object per person-show pair (core roles): person, show, year, roles, original, strict, loose
  reunions.json   per mode ("strict", "loose"): rows [cutoff, person_a, person_b, shows_together,
                  reunion_shows, first_reunion_year] for every pair who worked together in [T-10, T)

Step numbers 10-12 are reserved for the methods track (null model, BigCLAM, community tracking).
Rerun this step after any rerun of 05, 08 or 09.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import log, parse_args, read_parquet
from src.filters import show_exclusion_reason

OUT_DIR = config.ROOT / "viz" / "data"


def clean(v):
    """JSON-safe scalar: pandas NA/NaN -> None, numpy numbers -> Python numbers."""
    if v is None or (not isinstance(v, (list, dict, str)) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def write_json(obj, name: str):
    path = OUT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    log.info("Wrote viz/data/%s (%.0f KB)", name, len(text.encode("utf-8")) / 1024)


def wiki_url(title):
    return f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}" if isinstance(title, str) else None


def main():
    parse_args(__doc__.splitlines()[0])
    P = config.DATA_PROCESSED
    shows = read_parquet(P / "shows.parquet")
    shows["exclusion_reason"] = show_exclusion_reason(shows)
    core = shows[shows["exclusion_reason"].isna()]
    people = read_parquet(P / "people.parquet")
    ps = read_parquet(P / "network" / "person_show.parquet")
    labels = read_parquet(P / "network" / "reunion_labels.parquet")
    venues = read_parquet(P / "venues" / "show_venues.parquet")
    theatres = read_parquet(P / "venues" / "theatres.parquet")

    # theatres
    th = theatres.rename(columns={"venue_qid": "id", "venue_name": "name", "opened_year": "opened",
                                  "demolished_year": "demolished"})
    th["lat"], th["lon"] = th["lat"].round(5), th["lon"].round(5)
    # first and last show that opened there: first_show stands in for a missing opening date
    span = venues.dropna(subset=["venue_qid"]).groupby("venue_qid")["year"].agg(["min", "max"])
    th["first_show"] = th["id"].map(span["min"])
    th["last_show"] = th["id"].map(span["max"])
    th = th[["id", "name", "lat", "lon", "opened", "demolished", "first_show", "last_show", "n_shows"]]
    for c in ("opened", "demolished", "first_show", "last_show"):
        th[c] = th[c].astype("Int64")

    # shows (core set), with opening theatre
    sh = core[["show_id", "title", "year", "enwiki_title"]].merge(
        venues[["show_id", "venue_qid", "venue_basis"]], on="show_id", how="left")
    sh = pd.DataFrame({"id": sh["show_id"], "title": sh["title"], "year": sh["year"].astype("Int64"),
                       "venue": sh["venue_qid"], "venue_basis": sh["venue_basis"],
                       "wiki": sh["enwiki_title"].map(wiki_url)}).sort_values(["year", "title"])

    # credits: person-show pairs in the core roles
    cr = pd.DataFrame({"person": ps["person_id"], "show": ps["show_id"], "year": ps["show_year"],
                       "roles": ps["roles"].str.split("|"), "original": ps["is_original"],
                       "strict": ps["in_strict"], "loose": ps["in_loose"],
                       "posthumous": ps["is_posthumous"]})

    # people who appear in the network
    ids = set(ps["person_id"])
    pe = people[people["person_id"].isin(ids)]
    deaths = ps.groupby("person_id")["death_year"].first()
    names = ps.groupby("person_id")["person_name"].first()
    pe = pd.DataFrame({"id": pe["person_id"], "name": pe["name"], "born": pe["birth_year"].astype("Int64"),
                       "died": pe["person_id"].map(deaths).astype("Int64"), "birthplace": pe["birthplace"],
                       "lat": pe["lat"].round(4), "lon": pe["lon"].round(4),
                       "wiki": pe["enwiki_title"].map(wiki_url)})
    missing = sorted(ids - set(pe["id"]))
    if missing:  # people in credits but not in people.parquet: keep them with a name only
        pe = pd.concat([pe, pd.DataFrame({"id": missing, "name": [names[m] for m in missing]})], ignore_index=True)

    # reunion labels, compact rows per mode
    reunions = {}
    for mode, g in labels.groupby("mode"):
        g = g.sort_values(["cutoff", "person_a", "person_b"])
        reunions[mode] = [[int(r.cutoff), r.person_a, r.person_b, int(r.weight), int(r.n_reunion_shows),
                           None if pd.isna(r.first_reunion_year) else int(r.first_reunion_year)]
                          for r in g.itertuples()]

    n_venue = int(sh["venue"].notna().sum())
    n_bp = int(pe["lat"].notna().sum())
    meta = {
        "generated": date.today().isoformat(),
        "counts": {"shows": len(sh), "shows_with_venue": n_venue, "theatres": len(th), "people": len(pe),
                   "people_with_birthplace": n_bp, "credits": len(cr)},
        "network": {"roles": config.NETWORK_ROLES, "window_years": config.NETWORK_WINDOW_YEARS,
                    "horizon_years": config.NETWORK_HORIZON_YEARS, "cutoffs": config.NETWORK_CUTOFFS},
        "columns": {"reunions": ["cutoff", "person_a", "person_b", "shows_together", "reunion_shows",
                                 "first_reunion_year"]},
        "notes": [
            "Core show set: Broadway musicals opening 1900 or later (see README, 'Core show set').",
            f"Opening theatre known for {n_venue} of {len(sh)} shows; thinner before 1930.",
            f"Birthplace coordinates for {n_bp} of {len(pe)} people (people with a Wikidata entry).",
            "Theatre names are current names: renamed theatres are one building (the Alvin is 'Neil Simon Theatre').",
            "Shows have an opening year only, no closing date.",
        ],
    }

    write_json(meta, "meta.json")
    write_json(records(th), "theatres.json")
    write_json(records(sh), "shows.json")
    write_json(records(pe), "people.json")
    write_json(records(cr), "credits.json")
    write_json(reunions, "reunions.json")
    log.info("Shows %d (venue %d) | theatres %d | people %d (birthplace %d) | credits %d | reunion rows %s",
             len(sh), n_venue, len(th), len(pe), n_bp, len(cr), {k: len(v) for k, v in reunions.items()})


if __name__ == "__main__":
    main()
