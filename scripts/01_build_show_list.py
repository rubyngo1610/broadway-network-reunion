"""Step 01: build the list of Broadway musicals from Wikidata + Wikipedia.

Sources
  A. Wikidata items with an IBDB show ID (P1219) that are typed as a musical
     (P31/P136/P7937 -> Q2743 or a subclass) or as a dramatico-musical work.
  B. Wikidata items typed as a musical whose first-performance location /
     location is a Broadway theatre (instance of Q235065, or has an IBDB venue ID).
  C. Pages in the Wikipedia category tree under config.ROOT_CATEGORY.

Wikipedia titles are mapped to QIDs via the page's wikibase_item property, so
both sources deduplicate on the QID. Nothing is dropped: every row carries
flags saying how it was found and how Wikidata types it.

Output: data/interim/shows.parquet
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import log, parse_args, write_parquet
from src.http_client import CachedClient
from src.names import wiki_title
from src.wikidata import P, bindings_to_df, sparql_values_batches, verify_ids, year_from_date
from src.wikipedia import category_members, resolve_titles

# Subcategories that hold files or non-show material, never shows
SKIP_SUBCAT = re.compile(r"poster|image|photograph|logo|album|recording|song", re.I)

MUSICAL_TYPED = (f"(wdt:{P('instance_of')}|wdt:{P('genre')}|wdt:{P('form_of_work')})"
                 f"/wdt:{P('subclass_of')}* wd:{P('musical')}")
BROADWAY_VENUE = (f"?show (wdt:{P('first_perf_location')}|wdt:{P('location')}) ?venue. "
                  f"{{ ?venue wdt:{P('instance_of')} wd:{P('broadway_theatre')} }} "
                  f"UNION {{ ?venue wdt:{P('ibdb_venue_id')} [] }}")


def wikidata_candidates(client, limit):
    lim = f"LIMIT {limit}" if limit else ""
    q_ibdb = f"""
SELECT DISTINCT ?show WHERE {{
  ?show wdt:{P('ibdb_show_id')} [].
  {{ ?show {MUSICAL_TYPED} }} UNION {{ ?show wdt:{P('instance_of')} wd:{P('dramatico_musical_work')} }}
}} {lim}"""
    q_venue = f"""
SELECT DISTINCT ?show WHERE {{
  {BROADWAY_VENUE}
  ?show {MUSICAL_TYPED}.
}} {lim}"""
    a = set(bindings_to_df(client.sparql(q_ibdb, "show_candidates"))["show"])
    log.info("Wikidata A (IBDB show ID + musical/dramatico-musical typing): %d items", len(a))
    b = set(bindings_to_df(client.sparql(q_venue, "show_candidates"))["show"])
    log.info("Wikidata B (musical typing + Broadway venue): %d items", len(b))
    return a, b


FACTS_QUERY = f"""
SELECT ?show (SAMPLE(?lbl) AS ?label) (SAMPLE(?wp) AS ?enwiki)
       (GROUP_CONCAT(DISTINCT ?ibdb; separator="|") AS ?ibdb_ids)
       (MIN(?fp) AS ?first_performance) (MIN(?pub) AS ?publication) (MIN(?inc) AS ?inception)
       (SAMPLE(?m31) AS ?mus_p31) (SAMPLE(?mgen) AS ?mus_genre) (SAMPLE(?mform) AS ?mus_form)
       (SAMPLE(?dmw) AS ?dramatico_musical) (SAMPLE(?bwy) AS ?broadway_venue)
       (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types)
WHERE {{
  VALUES ?show {{ {{values}} }}
  OPTIONAL {{ ?show rdfs:label ?lbl FILTER(lang(?lbl)="en") }}
  OPTIONAL {{ ?wpUrl schema:about ?show; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?wp. }}
  OPTIONAL {{ ?show wdt:{P('ibdb_show_id')} ?ibdb. }}
  OPTIONAL {{ ?show wdt:{P('first_performance')} ?fp. }}
  OPTIONAL {{ ?show wdt:{P('publication_date')} ?pub. }}
  OPTIONAL {{ ?show wdt:{P('inception')} ?inc. }}
  OPTIONAL {{ ?show wdt:{P('instance_of')} ?type. ?type rdfs:label ?typeLabel FILTER(lang(?typeLabel)="en") }}
  BIND(EXISTS {{ ?show wdt:{P('instance_of')}/wdt:{P('subclass_of')}* wd:{P('musical')} }} AS ?m31)
  BIND(EXISTS {{ ?show wdt:{P('genre')}/wdt:{P('subclass_of')}* wd:{P('musical')} }} AS ?mgen)
  BIND(EXISTS {{ ?show wdt:{P('form_of_work')}/wdt:{P('subclass_of')}* wd:{P('musical')} }} AS ?mform)
  BIND(EXISTS {{ ?show wdt:{P('instance_of')} wd:{P('dramatico_musical_work')} }} AS ?dmw)
  BIND(EXISTS {{ {BROADWAY_VENUE} }} AS ?bwy)
}} GROUP BY ?show"""


def show_facts(client, qids) -> pd.DataFrame:
    df = sparql_values_batches(client, FACTS_QUERY, qids, "show_facts")
    for c in ["mus_p31", "mus_genre", "mus_form", "dramatico_musical", "broadway_venue"]:
        df[c] = df[c] == "true"
    return df


def main():
    args = parse_args(__doc__.splitlines()[0])
    client = CachedClient(refresh=args.refresh)
    verify_ids(client)

    # --- Wikidata --------------------------------------------------------
    a, b = wikidata_candidates(client, args.limit)

    # --- Wikipedia category --------------------------------------------
    pages, visited = category_members(client, config.ROOT_CATEGORY, config.CATEGORY_MAX_DEPTH,
                                      limit=args.limit, skip_subcat=SKIP_SUBCAT.search)
    log.info("Wikipedia: %d articles from %d categories (%d skipped)", len(pages),
             sum(not s for *_, s in visited), sum(s for *_, s in visited))
    pd.DataFrame(visited, columns=["category", "depth", "skipped"]).to_csv(
        config.DATA_INTERIM / "categories_visited.csv", index=False)
    resolved = resolve_titles(client, pages)
    wp = pd.DataFrame([
        {"wp_title": wiki_title(t), "wp_category_depth": d, "wp_category": cat}
        for t, (d, cat) in pages.items()])
    if not wp.empty:
        wp["enwiki_title_resolved"] = wp["wp_title"].map(lambda t: resolved[t]["resolved_title"])
        wp["qid_from_wp"] = wp["wp_title"].map(lambda t: resolved[t]["qid"])
    n_noqid = wp["qid_from_wp"].isna().sum() if not wp.empty else 0
    log.info("Wikipedia articles without a Wikidata item: %d", n_noqid)

    # --- Facts for every QID from any source -----------------------------
    all_qids = a | b | set(wp["qid_from_wp"].dropna() if not wp.empty else [])
    facts = show_facts(client, all_qids)
    log.info("Fetched Wikidata facts for %d items", len(facts))

    shows = facts.rename(columns={"show": "wikidata_qid"})
    shows["in_wd_ibdb_query"] = shows["wikidata_qid"].isin(a)
    shows["in_wd_venue_query"] = shows["wikidata_qid"].isin(b)

    # Attach Wikipedia category info by QID, then add category pages with no QID
    if not wp.empty:
        wp_q = (wp.dropna(subset=["qid_from_wp"])
                  .sort_values("wp_category_depth")
                  .drop_duplicates("qid_from_wp"))
        shows = shows.merge(wp_q[["qid_from_wp", "wp_category_depth", "wp_category"]],
                            left_on="wikidata_qid", right_on="qid_from_wp", how="left").drop(columns="qid_from_wp")
        no_q = wp[wp["qid_from_wp"].isna()].copy()
        no_q = no_q.assign(wikidata_qid=None, label=no_q["enwiki_title_resolved"],
                           enwiki=no_q["enwiki_title_resolved"])
        shows = pd.concat([shows, no_q[["wikidata_qid", "label", "enwiki", "wp_category_depth", "wp_category"]]],
                          ignore_index=True)
    shows["in_wp_category"] = shows["wp_category_depth"].notna()

    for c in ["in_wd_ibdb_query", "in_wd_venue_query", "mus_p31", "mus_genre", "mus_form",
              "dramatico_musical", "broadway_venue"]:
        shows[c] = shows[c].fillna(False).astype(bool)

    # --- Final columns -------------------------------------------------
    shows["show_id"] = shows["wikidata_qid"].fillna("enwiki:" + shows["enwiki"].fillna(""))
    shows["title"] = shows["label"].fillna(shows["enwiki"])
    shows["enwiki_title"] = shows["enwiki"]
    shows["ibdb_id"] = shows["ibdb_ids"].replace("", None)
    shows["n_ibdb_ids"] = shows["ibdb_id"].fillna("").map(lambda s: len(s.split("|")) if s else 0)
    shows["wd_is_musical"] = shows[["mus_p31", "mus_genre", "mus_form"]].any(axis=1)
    for col in ["first_performance", "publication", "inception"]:
        shows[col + "_year"] = shows[col].map(year_from_date).astype("Int64")
    shows["opening_year"] = (shows["first_performance_year"]
                             .fillna(shows["publication_year"]).fillna(shows["inception_year"]))
    shows["opening_year_source"] = None
    for col, src in [("inception_year", "wd_inception"), ("publication_year", "wd_publication"),
                     ("first_performance_year", "wd_first_performance")]:
        shows.loc[shows[col].notna(), "opening_year_source"] = src
    shows["wp_category_depth"] = shows["wp_category_depth"].astype("Int64")
    shows = shows.rename(columns={"types": "wd_instance_of", "broadway_venue": "wd_broadway_venue",
                                  "dramatico_musical": "wd_dramatico_musical",
                                  "mus_p31": "wd_musical_via_p31", "mus_genre": "wd_musical_via_genre",
                                  "mus_form": "wd_musical_via_form"})
    cols = ["show_id", "title", "wikidata_qid", "enwiki_title", "ibdb_id", "n_ibdb_ids",
            "opening_year", "opening_year_source",
            "in_wd_ibdb_query", "in_wd_venue_query", "in_wp_category", "wp_category_depth", "wp_category",
            "wd_is_musical", "wd_musical_via_p31", "wd_musical_via_genre", "wd_musical_via_form",
            "wd_dramatico_musical", "wd_broadway_venue", "wd_instance_of"]
    shows = shows[cols].sort_values("show_id").drop_duplicates("show_id").reset_index(drop=True)
    if args.limit:
        shows = shows.head(args.limit)

    write_parquet(shows, config.DATA_INTERIM / "shows.parquet")
    log.info("Summary: %d shows | wikidata-only %d | wikipedia-only %d | both %d | "
             "typed as musical %d | has IBDB id %d | has opening year %d",
             len(shows),
             (~shows.in_wp_category).sum(),
             (shows.in_wp_category & ~(shows.in_wd_ibdb_query | shows.in_wd_venue_query)).sum(),
             (shows.in_wp_category & (shows.in_wd_ibdb_query | shows.in_wd_venue_query)).sum(),
             shows.wd_is_musical.sum(), shows.ibdb_id.notna().sum(), shows.opening_year.notna().sum())
    log.info("HTTP: %d network requests, %d served from cache", client.n_network, client.n_cached)


if __name__ == "__main__":
    main()
