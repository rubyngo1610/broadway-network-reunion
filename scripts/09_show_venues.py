"""Step 09: opening Broadway theatre and its coordinates for every core show (for the NYC show map).

Method
  1. Candidates. For each core show, read its cached article (step 03) and collect every wikilink
     in sentences about an opening (opened, premiered, debuted, began, transferred, moved), plus the
     links in the infobox premiere/venue/place/productions fields.
  2. Resolve. Look up each linked page's Wikidata item through the MediaWiki API (redirects followed,
     so old theatre names such as "Alvin Theatre" land on today's article), then fetch its
     coordinates, types and opening and demolition dates from Wikidata.
  3. Keep NYC theatres only. A candidate counts as a venue if its item has coordinates in Manhattan
     and is a theatre-like place (instance of Broadway theatre, theatre building, or a label such as
     hall, playhouse, opera house). Generic links such as [[Broadway theatre]] are dropped.
  4. Choose one per show. Each candidate is scored: section ("Original Broadway production" best),
     the show's opening year in the sentence, "Broadway" just before the link, "revival", "tour",
     "Off-Broadway" or "London" nearby (penalty), a section heading or sentence that names only years
     well after the opening (penalty: a later production), and whether Wikidata types the item as a
     Broadway theatre. Theatres that had not opened yet, or were already demolished, in the show's
     year are dropped first (they name a revival). Known Off-Broadway and non-Broadway Manhattan
     venues (NON_BROADWAY_QIDS) are never chosen. The highest score wins; ties go to the earliest mention.
  5. VENUE_OVERRIDES below fixes individual shows by hand (show_id -> theatre QID, or None), and
     VENUE_COORD_OVERRIDES fixes theatres whose Wikidata coordinates are wrong.

Only the opening theatre is recorded; later transfers during a run are ignored.

Outputs
  data/processed/venues/show_venues.parquet   one row per core show: venue, coordinates, how it was found
  data/processed/venues/theatres.parquet      one row per theatre: coordinates, opened, demolished, n_shows
  outputs/tables/show_venues_review.csv       every core show with the chosen venue and evidence, for hand checks
  outputs/tables/venue_coverage.csv           share of core shows with a venue, by decade
"""
import re
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.filters import show_exclusion_reason
from src.http_client import CachedClient
from src.names import wiki_title
from src.wikidata import P, sparql_values_batches, verify_ids, year_from_date
from src.wikipedia import resolve_titles
from src.wikitext import sections

load_wikitext = import_module("03_fetch_wikitext").load_wikitext

OUT_DIR = config.DATA_PROCESSED / "venues"

# Manhattan bounding box (generous; the Theater District is around 40.755-40.765, -73.99)
LAT_MIN, LAT_MAX = 40.68, 40.88
LON_MIN, LON_MAX = -74.03, -73.90

# Wikidata types that count as a performance venue (matched against English labels)
VENUE_TYPE_RE = re.compile(
    r"theat|playhouse|opera house|music hall|concert hall|hall\b|auditorium|venue|cinema|movie palace|"
    r"hippodrome|casino|roof garden|nightclub|cabaret|vaudeville|arena|building", re.I)
# Items that pass the box but are not a venue for one show
NON_VENUE_QIDS = {
    "Q235065",   # Broadway theatre (the concept)
}
# Manhattan venues that are not Broadway houses: Off-Broadway, Harlem, clubs, concert halls.
# Checked by hand 2026-11-09. Shows that started here and transferred fall back to their Broadway theatre.
NON_BROADWAY_QIDS = {
    "Q164980": "Playwrights Horizons", "Q12063942": "New York Theatre Workshop", "Q8055572": "York Theatre",
    "Q6697298": "Lucille Lortel Theatre", "Q4796315": "Ars Nova", "Q1060845": "Delacorte Theater",
    "Q113100967": "Grove Street Playhouse", "Q1983008": "New World Stages", "Q7103965": "Orpheum Theatre (East Village)",
    "Q619124": "Apollo Theater (Harlem)", "Q49263": "Harlem Alhambra", "Q5089451": "Cheetah (nightclub)",
    "Q96406036": "Sony Hall", "Q753437": "Radio City Music Hall",
    "Q39046798": "47th Street Theatre (Off-Broadway)", "Q7989720": "Westside Theatre (Off-Broadway)",
    # Not excluded: the Latin Quarter (Q11983435), 200 W. 48th St, was a Broadway house 1979-1989
    # (22 Steps / Princess Theatre / Latin Quarter): Pump Boys and Dinettes, Mayor, My Old Friends.
}

# Coordinates that are wrong in Wikidata: venue QID -> (lat, lon). Checked 2026-11-10.
VENUE_COORD_OVERRIDES = {
    # Bijou Theatre (1917-1982), 209 W. 45th St: Wikidata gives the 1878 Bijou's point at Broadway and
    # 30th St (Q45103687). Placed on 45th St just east of the Morosco; the Marquis is on the site today.
    "Q4907254": (40.7584, -73.9862),
}

# A candidate needs at least this score to be chosen; below it, the show gets no venue rather than
# a likely revival theatre.
MIN_SCORE = 1

# Hand fixes: show_id -> theatre QID (or None to record "no venue"). Add rows after reviewing
# outputs/tables/show_venues_review.csv.
VENUE_OVERRIDES: dict[str, str | None] = {
    # 2026-11-09: the article does not link the original theatre in an opening sentence
    "Q740920": "Q1974872",    # Porgy and Bess (1935): Alvin Theatre, now the Neil Simon
    "Q656082": "Q1974872",    # Anything Goes (1934): Alvin Theatre
    "Q8000992": "Q1974872",   # Wildcat (1960): Alvin Theatre
    "Q16981116": "Q1974872",  # The Last Ship (2014): Neil Simon Theatre
    "Q4968327": "Q4741073",   # Bring in 'da Noise, Bring in 'da Funk (1996): Ambassador Theatre
    "Q19876779": "Q1797756",  # Love o' Mike (1917): opened at the Shubert, then Maxine Elliott's and the Casino
    # 2026-11-10: the article's first theatre is Off-Broadway (Westside Theatre)
    "Q7259797": "Q11983435",  # Pump Boys and Dinettes (1982): Princess Theatre, the Latin Quarter building
    "Q7749362": "Q11983435",  # The Madwoman of Central Park West (1979): transferred to Broadway at 22 Steps (Latin Quarter)
    "Q16981029": "Q2973328",  # Lady Day at Emerson's Bar and Grill: Broadway 2014 at Circle in the Square
                              # (year set to 2014 in src/filters.py; the 1986 run was Off-Broadway)
}

OPEN_VERB = re.compile(r"\b(opened|premiered|premièred|debuted|began|transferred|moved|played|ran)\b", re.I)
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"'])|\n+")
BAD_CONTEXT = re.compile(r"revival|revived|\btour|London|West End|Off-Broadway|off-Broadway|Encores|concert|"
                         r"tryout|try-out|out of town|out-of-town|workshop|regional|film|Chicago|Boston|"
                         r"Philadelphia|Washington|New Haven|Toronto", re.I)
INFOBOX_FIELDS = re.compile(r"^(premiere|premiere_location|venue|place|productions|location)$", re.I)

VENUE_QUERY = """
SELECT ?item ?itemLabel ?coord ?type ?typeLabel ?opened ?demolished ?isBroadway WHERE {
  VALUES ?item { {values} }
  OPTIONAL { ?item wdt:%(coord)s ?coord. }
  OPTIONAL { ?item wdt:%(p31)s ?type. }
  OPTIONAL { ?item wdt:%(opening)s ?opened. }
  OPTIONAL { ?item wdt:%(demolished)s ?demolished. }
  BIND(EXISTS { ?item wdt:%(p31)s/wdt:%(p279)s* wd:%(bway)s } AS ?isBroadway)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}"""


REF_RE = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>|<!--.*?-->", re.S | re.I)
SFN_RE = re.compile(r"\{\{\s*(sfn|efn|r|refn|cite|citation|webarchive)[^{}]*\}\}", re.I)


def clean(text: str) -> str:
    """Drop citations and comments, whose URLs, titles and periods break sentence splitting."""
    return SFN_RE.sub("", REF_RE.sub("", text))


def display_name(title) -> str | None:
    """'Imperial Theatre (Broadway)' -> 'Imperial Theatre'."""
    return re.sub(r"\s*\([^)]*\)$", "", title) if isinstance(title, str) else None


def section_score(heading: str) -> int:
    h = heading.lower()
    if h == "(lead)":
        return 2
    if re.search(r"revival|tour|london|west end|film|recording|adaptation|international|australia|"
                 r"other production|subsequent|regional|concert|television", h):
        return -2
    if "broadway" in h and re.search(r"original|premiere|production", h):
        return 4
    if "broadway" in h:
        return 3
    if re.search(r"production|history|premiere|background|original", h):
        return 1
    return 0


ABBREV_RE = re.compile(r"\b(St|Mr|Mrs|Ms|Dr|Jr|Sr|No|Mt|Ave|vs|ca|c)\.", re.I)
YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends, but never inside a [[link]] or after an abbreviation such as 'St.'."""
    links = []

    def hide(m):
        links.append(m.group(0))
        return f"\x00{len(links) - 1}\x00"
    t = re.sub(r"\[\[[^\]]*\]\]", hide, text)
    t = ABBREV_RE.sub(lambda m: m.group(0)[:-1] + "\x01", t)
    out = []
    for s in SENT_SPLIT.split(t):
        s = re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], s).replace("\x01", ".")
        out.append(s)
    return out


def later_year_penalty(text: str, year) -> int:
    """Text that names only years well after the show's year usually describes a later production.

    Not applied when the text is clearly about the Broadway run and not a revival: the show's
    `year` is often the world or regional premiere (Memphis 2003, Les Misérables 1980), so the
    Broadway opening itself can be years later.
    """
    if pd.isna(year):
        return 0
    years = [int(y) for y in YEAR_RE.findall(text)]
    if not years:
        return 0
    if re.search(r"(?<![Oo]ff-)Broadway", text) and not re.search(r"reviv|tour|concert|Encores|London|West End", text, re.I) \
            and min(years) <= year + 10:
        return 0
    if any(abs(y - year) <= 1 for y in years):
        return 0
    return -4 if any(y > year + 2 for y in years) else 0


def candidates_for_show(show_id: str, year, wikitext: str) -> list[dict]:
    """Every (link, context) pair that might name the opening theatre."""
    out = []
    order = 0
    yr = str(int(year)) if pd.notna(year) else None
    for heading, _lvl, code in sections(wikitext):
        text = clean(str(code))
        s_score = section_score(heading) + later_year_penalty(heading, year)
        if yr and yr in heading:
            s_score += 2
        for sent in split_sentences(text):
            if not OPEN_VERB.search(sent):
                continue
            # "Rehearsals began at ..." is not an opening; "previews began at ..." is
            if not re.search(r"\b(opened|premiered|premièred|debuted)\b|\b(played|ran) (at|on|in)\b", sent, re.I) \
                    and not re.search(r"preview", sent, re.I) \
                    and not re.search(r"transferred|moved", sent, re.I):
                continue
            sent_penalty = later_year_penalty(sent, year)
            for m in LINK_RE.finditer(sent):
                before = sent[max(0, m.start() - 90):m.start()]
                score = s_score + sent_penalty
                if yr and yr in sent:
                    score += 2
                if re.search(r"(?<![Oo]ff-)Broadway", before):
                    score += 2
                elif re.search(r"Broadway|New York", sent):
                    score += 1
                if BAD_CONTEXT.search(before):
                    score -= 3
                # "transferred to the X" / "moved to the X" names the second theatre of a run,
                # unless the move is onto Broadway itself ("transferred to Broadway at the X")
                # (applies to every theatre listed after the move word, e.g. "then transferred to Y and Z")
                prefix = sent[:m.start()]
                moves = [x.end() for x in re.finditer(
                    r"(transferred|transferring|moved|moving|relocated|returning) to(?! (the )?(\[\[[^\]]*\|)?Broadway\b)",
                    prefix, re.I)]
                opens = [x.end() for x in re.finditer(r"\b(opened|premiered|premièred|debuted)\b", prefix, re.I)]
                if moves and (not opens or moves[-1] > opens[-1]):
                    score -= 4
                out.append({"show_id": show_id, "link": wiki_title(m.group(1)), "source": "sentence",
                            "section": heading, "score": score, "order": order,
                            "snippet": re.sub(r"\s+", " ", sent.strip())[:300]})
                order += 1
    # infobox fields
    import mwparserfromhell as mw
    for t in mw.parse(wikitext).filter_templates(recursive=False):
        if not str(t.name).strip().lower().startswith("infobox"):
            continue
        for p in t.params:
            if not INFOBOX_FIELDS.match(str(p.name).strip()):
                continue
            val = clean(str(p.value))
            for m in LINK_RE.finditer(val):
                out.append({"show_id": show_id, "link": wiki_title(m.group(1)), "source": "infobox",
                            "section": f"infobox:{str(p.name).strip()}", "score": 1, "order": order,
                            "snippet": re.sub(r"\s+", " ", val.strip())[:300]})
                order += 1
    return out


def venue_items(client, qids) -> pd.DataFrame:
    """One row per item: label, lat, lon, types, opened/demolished year, is_broadway_theatre."""
    raw = sparql_values_batches(client, VENUE_QUERY % {
        "coord": P("coordinates"), "p31": P("instance_of"), "p279": P("subclass_of"),
        "opening": P("official_opening"), "demolished": P("demolished"), "bway": P("broadway_theatre")},
        qids, "venues", batch=100)
    if raw.empty:
        return pd.DataFrame(columns=["venue_qid", "venue_label", "lat", "lon", "types",
                                     "opened_year", "demolished_year", "is_broadway_theatre"])
    pt = raw["coord"].str.extract(r"Point\(([-\d.]+) ([-\d.]+)\)").astype(float)
    raw["lon"], raw["lat"] = pt[0], pt[1]
    raw["opened_year"] = raw["opened"].map(year_from_date)
    raw["demolished_year"] = raw["demolished"].map(year_from_date)
    g = raw.groupby("item")
    return pd.DataFrame({
        "venue_label": g["itemLabel"].first(),
        "lat": g["lat"].first(),
        "lon": g["lon"].first(),
        "types": g["typeLabel"].agg(lambda s: " | ".join(sorted({x for x in s.dropna()}))),
        "opened_year": g["opened_year"].min(),
        "demolished_year": g["demolished_year"].min(),
        "is_broadway_theatre": g["isBroadway"].first().eq("true"),
    }).rename_axis("venue_qid").reset_index()


def fix_coords(items: pd.DataFrame) -> pd.DataFrame:
    """Apply VENUE_COORD_OVERRIDES (coordinates that are wrong in Wikidata)."""
    for qid, (lat, lon) in VENUE_COORD_OVERRIDES.items():
        m = items["venue_qid"].eq(qid)
        if m.any():
            items.loc[m, ["lat", "lon"]] = [lat, lon]
            log.info("Coordinates for %s set by hand to %.4f, %.4f", qid, lat, lon)
    return items


def is_nyc_venue(row) -> bool:
    if row["venue_qid"] in NON_VENUE_QIDS or row["venue_qid"] in NON_BROADWAY_QIDS or pd.isna(row["lat"]):
        return False
    in_box = LAT_MIN <= row["lat"] <= LAT_MAX and LON_MIN <= row["lon"] <= LON_MAX
    typed = bool(row["is_broadway_theatre"]) or bool(VENUE_TYPE_RE.search(row["types"] or "")) \
        or bool(re.search(r"theat|playhouse|hall|casino|hippodrome|music box|garden", row["venue_label"] or "", re.I))
    return in_box and typed and "human" not in (row["types"] or "")


def main():
    args = parse_args(__doc__.splitlines()[0])
    shows = read_parquet(config.DATA_PROCESSED / "shows.parquet")
    shows["exclusion_reason"] = show_exclusion_reason(shows)
    core = apply_limit(shows[shows["exclusion_reason"].isna()], args.limit)
    index = read_parquet(config.DATA_INTERIM / "wikitext_index.parquet")
    title_of = dict(zip(index["show_id"], index["enwiki_title"]))
    log.info("Core shows: %d", len(core))

    cands = []
    n_article = 0
    for _, s in core.iterrows():
        title = title_of.get(s["show_id"])
        rec = load_wikitext(title) if isinstance(title, str) else None
        wt = (rec or {}).get("wikitext")
        if not wt:
            continue
        n_article += 1
        cands += candidates_for_show(s["show_id"], s["year"], wt)
    cands = pd.DataFrame(cands)
    log.info("Articles: %d | candidate links: %d (%d distinct pages)", n_article, len(cands), cands["link"].nunique())

    client = CachedClient(refresh=args.refresh)
    verify_ids(client, ["coordinates", "instance_of", "subclass_of", "official_opening", "demolished",
                        "broadway_theatre"])
    resolved = resolve_titles(client, cands["link"].unique(), subdir="pageprops_venues")
    cands["venue_qid"] = cands["link"].map(lambda t: resolved.get(t, {}).get("qid"))
    cands["resolved_title"] = cands["link"].map(lambda t: resolved.get(t, {}).get("resolved_title"))
    items = venue_items(client, cands["venue_qid"].dropna().unique())
    items = fix_coords(items)
    items["is_nyc_venue"] = items.apply(is_nyc_venue, axis=1)
    log.info("Linked items: %d | NYC venues: %d", len(items), int(items["is_nyc_venue"].sum()))

    c = cands.merge(items, on="venue_qid", how="inner")
    c = c[c["is_nyc_venue"]].copy()
    c["score"] += c["is_broadway_theatre"].astype(int)
    # A theatre that had not opened yet, or was already demolished, in the show's year names a later
    # production (usually a revival): drop it and let the next candidate win.
    yr = c["show_id"].map(dict(zip(core["show_id"], core["year"])))
    impossible = (c["opened_year"].notna() & yr.lt(c["opened_year"] - 1)) | \
                 (c["demolished_year"].notna() & yr.gt(c["demolished_year"]))
    log.info("Candidates dropped because the theatre did not exist in the show's year: %d", int(impossible.sum()))
    c = c[~impossible]
    weak = c["score"].lt(MIN_SCORE)
    log.info("Candidates dropped for a score below %d (revival or unrelated context): %d", MIN_SCORE, int(weak.sum()))
    c = c[~weak]
    best = (c.sort_values(["show_id", "score", "order"], ascending=[True, False, True])
             .drop_duplicates("show_id"))
    n_cands = c.groupby("show_id")["venue_qid"].nunique().rename("n_venue_candidates")

    out = core[["show_id", "title", "year"]].merge(
        best[["show_id", "venue_qid", "resolved_title", "source", "section", "score", "snippet"]],
        on="show_id", how="left").merge(n_cands, on="show_id", how="left")
    out["n_venue_candidates"] = out["n_venue_candidates"].fillna(0).astype(int)
    out["venue_basis"] = out["source"].fillna("not_found")
    out.loc[~out["show_id"].isin(title_of) | out["show_id"].map(lambda i: not isinstance(title_of.get(i), str)),
            "venue_basis"] = "no_article"
    for sid, qid in VENUE_OVERRIDES.items():
        m = out["show_id"].eq(sid)
        out.loc[m, ["venue_qid", "resolved_title", "venue_basis", "section", "snippet", "score"]] = \
            [qid, None, "manual", None, None, None]
    # Overrides may name items no article linked: fetch them too
    extra = sorted({q for q in VENUE_OVERRIDES.values() if q} - set(items["venue_qid"]))
    if extra:
        more = venue_items(client, extra)
        more = fix_coords(more)
        more["is_nyc_venue"] = True
        items = pd.concat([items, more], ignore_index=True)
    out = out.drop(columns="source").merge(
        items[["venue_qid", "venue_label", "lat", "lon", "opened_year", "demolished_year", "is_broadway_theatre"]],
        on="venue_qid", how="left")
    # Display name from the Wikipedia article title; for hand overrides, reuse the name another show
    # gives the same theatre, else the Wikidata label
    out["venue_name"] = out["resolved_title"].map(display_name)
    name_of = out.dropna(subset=["venue_name"]).groupby("venue_qid")["venue_name"].first()
    out["venue_name"] = out["venue_name"].fillna(out["venue_qid"].map(name_of)).fillna(out["venue_label"])
    # A theatre cannot host a show before it opened or after it was demolished
    out["venue_date_conflict"] = (out["opened_year"].notna() & out["year"].lt(out["opened_year"] - 1)) | \
                                 (out["demolished_year"].notna() & out["year"].gt(out["demolished_year"]))
    write_parquet(out, OUT_DIR / "show_venues.parquet")

    theatres = (items[items["is_nyc_venue"] & items["venue_qid"].isin(out["venue_qid"])]
                .drop(columns="is_nyc_venue")
                .merge(out.groupby("venue_qid").agg(venue_name=("venue_name", "first"),
                                                    n_shows=("show_id", "size")), on="venue_qid")
                .sort_values("n_shows", ascending=False))
    write_parquet(theatres, OUT_DIR / "theatres.parquet")

    out.sort_values(["venue_basis", "year"]).to_csv(config.OUTPUT_TABLES / "show_venues_review.csv", index=False)
    out["decade"] = (out["year"] // 10 * 10).astype("Int64")
    cov = out.groupby("decade").agg(shows=("show_id", "size"),
                                    with_venue=("venue_qid", lambda s: s.notna().sum()))
    cov["pct"] = (100 * cov["with_venue"] / cov["shows"]).round(1)
    cov.reset_index().to_csv(config.OUTPUT_TABLES / "venue_coverage.csv", index=False)

    log.info("Venue basis:\n%s", out["venue_basis"].value_counts().to_string())
    log.info("Shows with a venue: %d / %d (%.1f%%) | distinct theatres: %d | date conflicts: %d",
             out["venue_qid"].notna().sum(), len(out), 100 * out["venue_qid"].notna().mean(),
             len(theatres), int(out["venue_date_conflict"].sum()))
    log.info("Coverage by decade:\n%s", cov.to_string())
    log.info("Top theatres:\n%s", theatres.head(12)[["venue_name", "n_shows", "opened_year", "demolished_year"]]
             .to_string(index=False))
    log.info("HTTP: %d network requests, %d served from cache", client.n_network, client.n_cached)


if __name__ == "__main__":
    main()
