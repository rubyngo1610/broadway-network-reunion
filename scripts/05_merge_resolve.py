"""Step 05: merge Wikidata + Wikipedia creative credits and resolve people.

Person resolution, in order:
  1. Wikidata credit            -> person_id = QID
  2. Wikipedia wikilink         -> QID via the article's Wikidata sitelink
                                   (no item: 'enwiki:<Title>')
  3. Unlinked name, exact normalized match
       a. against people already credited on the same show
       b. single surname ('Lapine') against a unique same-show surname
       c. against every resolved person in the dataset (must be unique)
  4. Otherwise person_id = 'name:<normalized name>' and the row goes to
     outputs/tables/unresolved_names.csv (with a non-binding suggestion from a
     Wikipedia title lookup) for manual review.

Outputs: data/processed/credits.parquet, people.parquet, shows.parquet,
         data/interim/credit_mentions.parquet (every mention before aggregation),
         outputs/tables/unresolved_names.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.http_client import CachedClient
from src.names import enwiki_url, normalize_name, wiki_title
from src.roles import normalize_role
from src.wikidata import CLASSES, PERSON_PROPS, fetch_people, verify_ids
from src.wikipedia import resolve_titles

AUTHORSHIP = {"composer", "lyricist", "book_writer", "playwright", "conceived_by"}


def original_flag(row, orig_year):
    """is_original_production for one mention: True / False / <NA>, plus the reason."""
    if row["source"] == "wikidata":
        return (True, "authorship credit on the work") if row["role"] in AUTHORSHIP else (pd.NA, "wikidata, not production-specific")
    if row["extraction"] == "infobox":
        return True, "infobox (original production)"
    # prose
    if row["mentions_film_tv"]:
        return False, "prose: film/TV context"
    if row["mentions_revival"] or row["mentions_tour"]:
        return False, "prose: revival/tour context"
    years = [int(y) for y in str(row["context_years"]).split(",")] if isinstance(row["context_years"], str) else []
    if pd.notna(orig_year) and years:
        if any(abs(y - orig_year) <= 1 for y in years):
            return (False, "prose: London context") if row["mentions_london"] else (True, "prose: year matches original Broadway")
        return False, "prose: year differs from original Broadway"
    if row["mentions_london"]:
        return False, "prose: London context"
    if row["mentions_original"]:
        return True, "prose: 'original'/'premiere' context, no year"
    return pd.NA, "prose: no year/context"


def main():
    args = parse_args(__doc__.splitlines()[0])
    client = CachedClient(refresh=args.refresh)
    verify_ids(client, list(PERSON_PROPS) + list(CLASSES) + ["instance_of"])

    shows = apply_limit(read_parquet(config.DATA_INTERIM / "shows.parquet"), args.limit)
    keep = set(shows["show_id"])
    wd = read_parquet(config.DATA_INTERIM / "credits_wikidata.parquet")
    wd = wd[wd["show_id"].isin(keep)].copy()
    wp = read_parquet(config.DATA_INTERIM / "credits_wikipedia.parquet")
    wp = wp[wp["show_id"].isin(keep)].copy()
    people_wd = read_parquet(config.DATA_INTERIM / "people_wikidata.parquet")
    infobox = read_parquet(config.DATA_INTERIM / "infobox_shows.parquet", required=False)

    # ---- show years ---------------------------------------------------------
    sh = shows.copy()
    if infobox is not None:
        sh = sh.merge(infobox[["show_id", "has_infobox", "original_broadway_year", "premiere_year"]],
                      on="show_id", how="left")
    else:
        sh["has_infobox"], sh["original_broadway_year"], sh["premiere_year"] = False, pd.NA, pd.NA
    sh["year"], sh["year_source"] = pd.NA, None
    for col, src in [("opening_year", "wikidata"), ("premiere_year", "infobox_premiere"),
                     ("original_broadway_year", "infobox_productions")]:  # last wins = highest priority
        m = sh[col].notna()
        sh.loc[m, "year"] = sh.loc[m, col]
        sh.loc[m, "year_source"] = src
    sh["year"] = sh["year"].astype("Int64")
    orig_year = dict(zip(sh["show_id"], sh["original_broadway_year"].fillna(sh["year"])))

    # ---- 1. Wikidata mentions -------------------------------------------------
    wd["person_id"] = wd["person_qid"]
    wd["person_name"] = wd["person_label"]
    wd["resolution"] = wd["person_qid"].map(lambda q: "wikidata_qid" if isinstance(q, str) else "unknown_value")
    wd["role_norm"] = [normalize_role(q) if r == "contributor" and isinstance(q, str) else normalize_role(r)
                       for r, q in zip(wd["role"], wd["role_qualifier"])]
    wd["extraction"] = "wikidata"
    wd["person_link"] = None
    wd["is_linked"] = True

    # ---- 2. Wikilinks -> QID ---------------------------------------------------
    links = wp.loc[wp["is_linked"], "person_link"].dropna().unique()
    resolved = resolve_titles(client, links)
    wp["link_title"] = wp["person_link"].map(lambda t: wiki_title(t) if isinstance(t, str) else None)
    wp["link_resolved"] = wp["link_title"].map(lambda t: resolved.get(t, {}).get("resolved_title") if t else None)
    wp["link_qid"] = wp["link_title"].map(lambda t: resolved.get(t, {}).get("qid") if t else None)
    wp["link_missing"] = wp["link_title"].map(lambda t: resolved.get(t, {}).get("missing") if t else None)
    wp["person_id"] = None
    wp["resolution"] = None
    m = wp["link_qid"].notna()
    wp.loc[m, "person_id"] = wp.loc[m, "link_qid"]
    wp.loc[m, "resolution"] = "wikilink_qid"
    m = wp["is_linked"] & wp["link_qid"].isna() & (wp["link_missing"] == False)  # noqa: E712
    wp.loc[m, "person_id"] = "enwiki:" + wp.loc[m, "link_resolved"]
    wp.loc[m, "resolution"] = "wikilink_no_qid"
    # red links fall through to name matching below
    wp["role_norm"] = wp["role_raw"].map(lambda r: normalize_role(r.split("(")[0].replace("prose:", "").strip()))
    wp["is_original_production"] = None

    # ---- 3. Name matching -------------------------------------------------------
    # name index: normalized name -> person_ids, from Wikidata labels and wikilinked mentions
    name_rows = pd.concat([
        wd[["show_id", "person_id", "person_name"]],
        wp.loc[wp["person_id"].notna(), ["show_id", "person_id", "person_name"]],
        wp.loc[wp["person_id"].notna(), ["show_id", "person_id", "link_resolved"]].rename(
            columns={"link_resolved": "person_name"}).assign(
            person_name=lambda d: d["person_name"].str.replace(r"\s*\(.*\)$", "", regex=True)),
        people_wd[["person_qid", "person_label"]].rename(
            columns={"person_qid": "person_id", "person_label": "person_name"}).assign(show_id=None),
    ]).dropna(subset=["person_id", "person_name"])
    name_rows["norm"] = name_rows["person_name"].map(normalize_name)
    name_rows["surname"] = name_rows["norm"].str.split().str[-1]
    global_idx = name_rows.groupby("norm")["person_id"].agg(lambda s: sorted(set(s)))
    show_idx = name_rows.dropna(subset=["show_id"]).groupby(["show_id", "norm"])["person_id"].agg(lambda s: sorted(set(s)))
    surname_idx = name_rows.dropna(subset=["show_id"]).groupby(["show_id", "surname"])["person_id"].agg(lambda s: sorted(set(s)))

    unresolved = []
    todo = wp["person_id"].isna()
    for i in wp.index[todo]:
        name, show = wp.at[i, "person_name"], wp.at[i, "show_id"]
        norm = normalize_name(name)
        cands, method = show_idx.get((show, norm)), "name_same_show"
        if not cands and len(norm.split()) == 1:
            cands, method = surname_idx.get((show, norm)), "surname_same_show"
        if not cands:
            cands, method = global_idx.get(norm), "name_exact_global"
        if cands and len(cands) == 1:
            wp.at[i, "person_id"], wp.at[i, "resolution"] = cands[0], method
            continue
        if not wp.at[i, "is_plausible_name"]:
            # e.g. '1956 version': kept in credit_mentions and the review file, not in credits
            status = "implausible_name"
            wp.at[i, "person_id"] = None
        else:
            status = "ambiguous" if cands else "unresolved"
            wp.at[i, "person_id"] = "name:" + norm if norm else None
        wp.at[i, "resolution"] = status
        unresolved.append({"show_id": show, "person_name": name, "normalized": norm, "status": status,
                           "candidates": " | ".join(cands or []), "role": wp.at[i, "role_norm"],
                           "extraction": wp.at[i, "extraction"], "is_plausible_name": wp.at[i, "is_plausible_name"],
                           "red_link": wp.at[i, "person_link"], "context": wp.at[i, "context"]})

    # Suggestions for manual review only (never applied automatically)
    unres = pd.DataFrame(unresolved)
    if not unres.empty:
        names = unres.loc[unres["is_plausible_name"].astype(bool), "person_name"].unique()
        sugg = resolve_titles(client, names)
        unres["suggested_enwiki"] = unres["person_name"].map(
            lambda n: (sugg.get(wiki_title(n)) or {}).get("resolved_title")
            if not (sugg.get(wiki_title(n)) or {}).get("missing", True) else None)
        unres["suggested_qid"] = unres["person_name"].map(lambda n: (sugg.get(wiki_title(n)) or {}).get("qid"))
        unres["suggested_url"] = unres["suggested_enwiki"].map(lambda t: enwiki_url(t) if isinstance(t, str) else None)
        unres = unres.merge(shows[["show_id", "title", "enwiki_title"]], on="show_id", how="left")
        unres["show_url"] = unres["enwiki_title"].map(lambda t: enwiki_url(t) if isinstance(t, str) else None)
        unres["resolved_qid_manual"] = ""  # to fill in by hand
    cols = ["status", "show_id", "title", "person_name", "normalized", "role", "extraction", "is_plausible_name",
            "candidates", "suggested_enwiki", "suggested_qid", "suggested_url", "red_link", "show_url",
            "context", "resolved_qid_manual"]
    (unres.reindex(columns=cols).sort_values(["status", "person_name"]) if not unres.empty
     else pd.DataFrame(columns=cols)).to_csv(config.OUTPUT_TABLES / "unresolved_names.csv", index=False)

    # ---- 4. Long table of every mention ---------------------------------------
    mention_cols = ["show_id", "person_id", "person_name", "role_norm", "role_raw", "source", "extraction",
                    "resolution", "person_link", "is_linked", "context", "context_years", "mentions_revival",
                    "mentions_tour", "mentions_film_tv", "mentions_london", "mentions_original"]
    mentions = pd.concat([wd.reindex(columns=mention_cols), wp.reindex(columns=mention_cols)], ignore_index=True)
    mentions = mentions.rename(columns={"role_norm": "role"})
    flags = [original_flag(r, orig_year.get(r["show_id"])) for _, r in mentions.iterrows()]
    mentions["is_original_production"] = pd.array([f[0] for f in flags], dtype="boolean")
    mentions["original_basis"] = [f[1] for f in flags]
    write_parquet(mentions, config.DATA_INTERIM / "credit_mentions.parquet")

    # ---- 5. People --------------------------------------------------------------
    qids = sorted({p for p in mentions["person_id"].dropna() if p.startswith("Q")})
    missing = [q for q in qids if q not in set(people_wd["person_qid"])]
    log.info("People with QIDs: %d (%d already fetched in step 02, %d new from wikilinks)",
             len(qids), len(qids) - len(missing), len(missing))
    extra = fetch_people(client, missing) if missing else pd.DataFrame()
    ppl_q = pd.concat([people_wd, extra], ignore_index=True).drop_duplicates("person_qid")
    ppl_q = ppl_q[ppl_q["person_qid"].isin(qids)]
    ppl_q = ppl_q.rename(columns={"person_qid": "qid", "person_label": "name"})
    ppl_q["person_id"] = ppl_q["qid"]
    others = (mentions[mentions["person_id"].notna() & ~mentions["person_id"].str.startswith("Q", na=False)]
              .groupby("person_id")["person_name"].agg(lambda s: s.mode().iat[0]).reset_index()
              .rename(columns={"person_name": "name"}))
    others["enwiki_title"] = others["person_id"].map(lambda p: p[7:] if p.startswith("enwiki:") else None)
    people = pd.concat([ppl_q, others], ignore_index=True)
    people["id_type"] = people["person_id"].str.split(":").str[0].where(
        people["person_id"].str.contains(":"), "qid")
    stats = mentions.dropna(subset=["person_id"]).groupby("person_id").agg(
        n_shows=("show_id", "nunique"), roles=("role", lambda s: " | ".join(sorted(set(s)))))
    people = people.merge(stats, left_on="person_id", right_index=True, how="left")
    pcols = ["person_id", "name", "qid", "enwiki_title", "birthplace", "birthplace_qid", "lat", "lon",
             "citizenship", "birth_year", "is_human", "ibdb_person_id", "id_type", "n_shows", "roles",
             "n_birthplaces", "citizenship_qids", "birth_date"]
    people = people.reindex(columns=pcols).sort_values("person_id").reset_index(drop=True)
    people["birth_year"] = people["birth_year"].astype("Int64")
    people["is_human"] = people["is_human"].astype("boolean")
    write_parquet(people, config.DATA_PROCESSED / "people.parquet")

    # ---- 6. Aggregate to one row per (show, person, role) ------------------------
    def agg_orig(s):
        s = s.dropna()
        return pd.NA if s.empty else bool(s.any())

    m = mentions.dropna(subset=["person_id"])
    credits = (m.groupby(["show_id", "person_id", "role"], as_index=False)
                .agg(role_raw=("role_raw", lambda s: " | ".join(sorted(set(s.dropna())))),
                     source=("source", lambda s: ";".join(sorted(set(s)))),
                     extraction=("extraction", lambda s: ";".join(sorted(set(s)))),
                     resolution=("resolution", lambda s: ";".join(sorted(set(s.dropna())))),
                     is_original_production=("is_original_production", agg_orig),
                     n_mentions=("role", "size"),
                     mention_name=("person_name", "first")))
    credits["is_original_production"] = credits["is_original_production"].astype("boolean")
    name_map = dict(zip(people["person_id"], people["name"]))
    credits["person_name"] = credits["person_id"].map(name_map).fillna(credits["mention_name"])
    credits = credits.merge(sh[["show_id", "title", "year"]], on="show_id", how="left")
    ccols = ["show_id", "title", "year", "person_id", "person_name", "role", "role_raw", "source",
             "is_original_production", "extraction", "resolution", "n_mentions"]
    credits = credits[ccols].sort_values(["show_id", "role", "person_id"]).reset_index(drop=True)
    write_parquet(credits, config.DATA_PROCESSED / "credits.parquet")

    # ---- 7. Shows ------------------------------------------------------------
    per_show = credits.groupby("show_id").agg(n_credits=("person_id", "size"), n_people=("person_id", "nunique"))
    sh = sh.merge(per_show, left_on="show_id", right_index=True, how="left")
    sh[["n_credits", "n_people"]] = sh[["n_credits", "n_people"]].fillna(0).astype(int)
    scols = ["show_id", "title", "year", "year_source", "wikidata_qid", "enwiki_title", "ibdb_id",
             "opening_year", "original_broadway_year", "premiere_year", "has_infobox", "n_credits", "n_people",
             "in_wd_ibdb_query", "in_wd_venue_query", "in_wp_category", "wp_category_depth", "wd_is_musical",
             "wd_dramatico_musical", "wd_broadway_venue", "wd_instance_of"]
    write_parquet(sh.reindex(columns=scols), config.DATA_PROCESSED / "shows.parquet")

    # ---- Summary -------------------------------------------------------------
    log.info("Mentions by resolution:\n%s", mentions["resolution"].value_counts(dropna=False).to_string())
    log.info("Credits: %d rows | shows %d | people %d | sources: %s", len(credits), credits.show_id.nunique(),
             credits.person_id.nunique(), credits["source"].value_counts().to_dict())
    log.info("is_original_production: %s", credits["is_original_production"].value_counts(dropna=False).to_dict())
    log.info("Unresolved/ambiguous names for review: %d -> outputs/tables/unresolved_names.csv", len(unres))
    log.info("HTTP: %d network requests, %d served from cache", client.n_network, client.n_cached)


if __name__ == "__main__":
    main()
