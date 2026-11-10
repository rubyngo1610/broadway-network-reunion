"""Wikidata IDs used by the pipeline, their verification, and SPARQL helpers.

Every ID below was found by label search against the live endpoint, and
verify_ids() re-checks the English label of each one at run time, aborting if
any has changed. Nothing downstream relies on an ID that has not passed this check.
"""
import logging
import sys

import pandas as pd
from tqdm import tqdm

import config
from src.common import chunks

log = logging.getLogger(__name__)

# key -> (ID, acceptable English labels, lowercase)
SHOW_PROPS = {
    "instance_of":          ("P31",   {"instance of"}),
    "subclass_of":          ("P279",  {"subclass of"}),
    "genre":                ("P136",  {"genre"}),
    "form_of_work":         ("P7937", {"form of creative work"}),
    "ibdb_show_id":         ("P1219", {"internet broadway database show id"}),
    "ibdb_venue_id":        ("P1217", {"internet broadway database venue id"}),
    "first_performance":    ("P1191", {"date of first performance"}),
    "first_perf_location":  ("P4647", {"location of first performance"}),
    "location":             ("P276",  {"location"}),
    "publication_date":     ("P577",  {"publication date"}),
    "inception":            ("P571",  {"inception"}),
}

# Creative-credit properties on the show item -> normalized role
ROLE_PROPS = {
    "composer":             ("P86",   {"composer"}),
    "lyricist":             ("P676",  {"lyricist"}),
    "librettist":           ("P87",   {"librettist"}),
    "director":             ("P57",   {"director"}),
    "choreographer":        ("P1809", {"choreographer"}),
    "orchestrator":         ("P10806", {"orchestrator"}),
    "musical_conductor":    ("P3300", {"musical conductor"}),
    "scenographer":         ("P4608", {"scenographer"}),
    "production_designer":  ("P2554", {"production designer"}),
    "costume_designer":     ("P2515", {"costume designer"}),
    "lighting_designer":    ("P5026", {"lighting designer"}),
    "sound_designer":       ("P5028", {"sound designer"}),
    "video_designer":       ("P5880", {"video designer"}),
    "projection_designer":  ("P5881", {"projection designer"}),
    "dramaturge":           ("P6086", {"dramaturge"}),
    "producer":             ("P162",  {"producer"}),
    "executive_producer":   ("P1431", {"executive producer"}),
    "production_company":   ("P272",  {"production company"}),
    "author":               ("P50",   {"author"}),
    "creator":              ("P170",  {"creator"}),
    "screenwriter":         ("P58",   {"screenwriter"}),
    "contributor":          ("P767",  {"contributor to the creative work or subject"}),
}

QUALIFIER_PROPS = {
    "object_has_role":      ("P3831", {"object of statement has role"}),
    "character_role":       ("P453",  {"character role"}),
}

CAST_PROPS = {
    "cast_member":          ("P161",  {"cast member"}),
}

PERSON_PROPS = {
    "place_of_birth":       ("P19",   {"place of birth"}),
    "citizenship":          ("P27",   {"country of citizenship"}),
    "date_of_birth":        ("P569",  {"date of birth"}),
    "date_of_death":        ("P570",  {"date of death"}), # added to support original flag 
    "coordinates":          ("P625",  {"coordinate location"}),
    "ibdb_person_id":       ("P1220", {"internet broadway database person id"}),
    
}

CLASSES = {
    "musical":                 ("Q2743",     {"musical", "musical play", "musical theatre"}),
    "dramatico_musical_work":  ("Q58483083", {"dramatico-musical work"}),
    "broadway_theatre":        ("Q235065",   {"broadway theatre", "broadway theater"}),
    "theatre_building":        ("Q24354",    {"theatre building", "theater building", "theatre"}),
    "human":                   ("Q5",        {"human"}),
}

# Venue properties (step 09)
VENUE_PROPS = {
    "demolished":              ("P576",  {"dissolved, abolished or demolished", "dissolved, abolished or demolished date"}),
    "official_opening":        ("P1619", {"date of official opening"}),
}

ALL_IDS = {**SHOW_PROPS, **ROLE_PROPS, **QUALIFIER_PROPS, **CAST_PROPS, **PERSON_PROPS, **CLASSES, **VENUE_PROPS}


def P(key: str) -> str:
    return ALL_IDS[key][0]


def verify_ids(client, keys=None) -> pd.DataFrame:
    """Check each ID's live English label; exit if any does not match."""
    keys = list(keys or ALL_IDS)
    ids = " ".join(f"wd:{ALL_IDS[k][0]}" for k in keys)
    res = client.sparql(
        f"SELECT ?x ?label WHERE {{ VALUES ?x {{ {ids} }} "
        f"OPTIONAL {{ ?x rdfs:label ?label FILTER(lang(?label)='en') }} }}",
        "verify_ids")
    live = {b["x"]["value"].rsplit("/", 1)[-1]: b.get("label", {}).get("value", "")
            for b in res["results"]["bindings"]}
    rows, bad = [], []
    for k in keys:
        wid, accepted = ALL_IDS[k]
        label = live.get(wid, "")
        ok = label.lower() in accepted
        rows.append({"key": k, "id": wid, "live_label": label, "ok": ok})
        if not ok:
            bad.append(f"{k}: {wid} has label {label!r}, expected one of {sorted(accepted)}")
    df = pd.DataFrame(rows)
    df.to_csv(config.DATA_INTERIM / "wikidata_ids_verified.csv", index=False)
    if bad:
        log.error("Wikidata ID verification failed:\n  %s", "\n  ".join(bad))
        sys.exit(1)
    log.info("Verified %d Wikidata IDs against live labels", len(df))
    return df


# --- result handling -------------------------------------------------------

def bindings_to_df(res: dict) -> pd.DataFrame:
    """SPARQL JSON -> DataFrame of strings; entity URIs shortened to QIDs."""
    cols = res["head"]["vars"]
    rows = []
    for b in res["results"]["bindings"]:
        row = {}
        for c in cols:
            v = b.get(c)
            if v is None:
                row[c] = None
            elif v["type"] == "uri" and v["value"].startswith("http://www.wikidata.org/entity/"):
                row[c] = v["value"].rsplit("/", 1)[-1]
            else:
                row[c] = v["value"]
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


def sparql_values_batches(client, template: str, qids, subdir: str, batch=None) -> pd.DataFrame:
    """Run `template` (containing the literal text {values}) once per batch of QIDs; concat results."""
    qids = sorted(set(q for q in qids if q))
    frames = []
    for b in tqdm(list(chunks(qids, batch or config.SPARQL_BATCH)), desc=subdir, leave=False):
        values = " ".join(f"wd:{q}" for q in b)
        frames.append(bindings_to_df(client.sparql(template.replace("{values}", values), subdir)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def year_from_date(s):
    """'1957-09-26T00:00:00Z' -> 1957; handles BCE '-0500-..'; None-safe."""
    if not isinstance(s, str) or not s:
        return None
    try:
        neg = s.startswith("-")
        y = int(s.lstrip("-+").split("-", 1)[0])
        return -y if neg else y
    except ValueError:
        return None


# --- people ----------------------------------------------------------------

PEOPLE_QUERY = """
SELECT ?person ?personLabel ?enwiki ?ibdb ?isHuman
       ?birthplace ?birthplaceLabel ?coord ?citizenship ?citizenshipLabel ?dob
WHERE {
  VALUES ?person { {values} }
  OPTIONAL { ?enwikiUrl schema:about ?person; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?enwiki. }
  OPTIONAL { ?person wdt:%(ibdb)s ?ibdb. }
  BIND(EXISTS { ?person wdt:%(p31)s wd:%(human)s } AS ?isHuman)
  OPTIONAL { ?person wdt:%(pob)s ?birthplace.
             OPTIONAL { ?birthplace wdt:%(coord)s ?coord. } }
  OPTIONAL { ?person wdt:%(cit)s ?citizenship. }
  OPTIONAL { ?person wdt:%(dob)s ?dob. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}"""


def fetch_people(client, qids, subdir="people") -> pd.DataFrame:
    """One row per person. Multi-valued fields are joined with ' | ' and the
    first value (sorted, for determinism) is kept in the scalar columns."""
    template = PEOPLE_QUERY % {
        "ibdb": P("ibdb_person_id"), "p31": P("instance_of"), "human": P("human"),
        "pob": P("place_of_birth"), "coord": P("coordinates"),
        "cit": P("citizenship"), "dob": P("date_of_birth"),
    }
    # People rows multiply (birthplaces x citizenships x dates), so use smaller batches
    raw = sparql_values_batches(client, template, qids, subdir, batch=100)
    if raw.empty:
        return pd.DataFrame()
    out = []
    for qid, g in raw.groupby("person", sort=True):
        def vals(col):
            return sorted({v for v in g[col].dropna() if v != ""})

        bp = vals("birthplace")
        # label and coordinates must describe the same (first) birthplace
        bp_rows = g[g["birthplace"] == bp[0]] if bp else g.iloc[0:0]
        bp_label = next(iter(bp_rows["birthplaceLabel"].dropna()), None)
        coord = next(iter(sorted(bp_rows["coord"].dropna())), None)
        lat = lon = None
        if coord:  # WKT 'Point(lon lat)'
            try:
                lon, lat = map(float, coord.replace("Point(", "").rstrip(")").split())
            except ValueError:
                pass
        dobs = vals("dob")
        cit = vals("citizenshipLabel")
        out.append({
            "person_qid": qid,
            "person_label": (vals("personLabel") or [None])[0],
            "enwiki_title": (vals("enwiki") or [None])[0],
            "ibdb_person_id": " | ".join(vals("ibdb")) or None,
            "is_human": bool((g["isHuman"] == "true").any()),
            "birthplace": bp_label,
            "birthplace_qid": bp[0] if bp else None,
            "n_birthplaces": len(bp),
            "lat": lat, "lon": lon,
            "citizenship": " | ".join(cit) or None,
            "citizenship_qids": " | ".join(vals("citizenship")) or None,
            "birth_date": dobs[0] if dobs else None,
            "birth_year": year_from_date(dobs[0]) if dobs else None,
            "n_birth_dates": len(dobs),
        })
    df = pd.DataFrame(out)
    df["birth_year"] = df["birth_year"].astype("Int64")
    return df
