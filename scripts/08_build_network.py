"""Step 08: collaboration network, time windows and reunion labels for BigCLAM and H1/H3.

Applies the team decisions (Pipeline Findings, sections 7 and 8):
  * core show set only (src/filters.py), core roles only (config.NETWORK_ROLES)
  * one row per person-show pair, roles kept as an attribute
  * posthumous credits dropped (death year from Wikidata P570, fetched here)
  * two modes: strict = original production only; loose = original or unknown
  * repeated time splits: for each cutoff T, edges come only from [T - W, T) and
    labels only from [T, T + H), so nothing learned can see the reunion

Outputs (data/processed/network/)
  person_show.parquet         one row per person-show (all years), with flags, for the views
  edges_by_window.parquet     mode x cutoff x person pair: co-credits in the training window
  reunion_labels.parquet      same pairs: did they share a show in the reunion window?
  outputs/tables/network_windows.csv   per mode and cutoff: shows, people, edges, reunion rate
"""
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.filters import show_exclusion_reason
from src.http_client import CachedClient
from src.wikidata import P, sparql_values_batches, verify_ids, year_from_date

OUT_DIR = config.DATA_PROCESSED / "network"
MODES = ["strict", "loose"]

DEATH_QUERY = """
SELECT ?person ?dod WHERE {
  VALUES ?person { {values} }
  ?person wdt:%(dod)s ?dod.
}"""


def death_years(client, qids) -> pd.Series:
    """Earliest recorded death year per person QID."""
    raw = sparql_values_batches(client, DEATH_QUERY % {"dod": P("date_of_death")}, qids, "deaths")
    if raw.empty:
        return pd.Series(dtype="Int64")
    raw["person"] = raw["person"].str.rsplit("/", n=1).str[-1]
    raw["death_year"] = raw["dod"].map(year_from_date)
    return raw.groupby("person")["death_year"].min().astype("Int64")


def original_status(flags: pd.Series):
    """Combine role-level flags for one person on one show: any True wins, then unknown, then False."""
    if flags.eq(True).any():
        return True
    if flags.isna().any():
        return pd.NA
    return False


def person_show_table(credits, shows, deaths):
    c = credits.merge(shows[["show_id", "year"]].rename(columns={"year": "show_year"}), on="show_id")
    ps = (c.groupby(["show_id", "person_id"], sort=True)
          .agg(person_name=("person_name", "first"), show_year=("show_year", "first"),
               roles=("role", lambda s: "|".join(sorted(set(s)))),
               is_original=("is_original_production", original_status))
          .reset_index())
    ps["death_year"] = ps["person_id"].map(deaths).astype("Int64")
    ps["is_posthumous"] = (ps["show_year"] > ps["death_year"] + config.POSTHUMOUS_GRACE_YEARS).fillna(False)
    ps["in_strict"] = ps["is_original"].eq(True).fillna(False) & ~ps["is_posthumous"]
    ps["in_loose"] = ps["is_original"].ne(False).fillna(True) & ~ps["is_posthumous"]
    return ps


def pair_rows(ps):
    """Every pair of people who share a show, one row per (pair, show)."""
    rows = []
    for sid, g in ps.groupby("show_id", sort=False):
        year = g["show_year"].iloc[0]
        for a, b in combinations(sorted(g["person_id"].unique()), 2):
            rows.append((a, b, sid, year))
    return pd.DataFrame(rows, columns=["person_a", "person_b", "show_id", "year"])


def windows(pairs, mode):
    edges, labels, summary = [], [], []
    W, H = config.NETWORK_WINDOW_YEARS, config.NETWORK_HORIZON_YEARS
    for T in config.NETWORK_CUTOFFS:
        train = pairs[(pairs["year"] >= T - W) & (pairs["year"] < T)]
        future = pairs[(pairs["year"] >= T) & (pairs["year"] < T + H)]
        e = (train.groupby(["person_a", "person_b"])
             .agg(weight=("show_id", "nunique"), first_year=("year", "min"), last_year=("year", "max"))
             .reset_index())
        f = (future.groupby(["person_a", "person_b"])
             .agg(n_reunion_shows=("show_id", "nunique"), first_reunion_year=("year", "min"))
             .reset_index())
        lab = e[["person_a", "person_b", "weight"]].merge(f, on=["person_a", "person_b"], how="left")
        lab["reunited"] = lab["n_reunion_shows"].notna()
        lab["n_reunion_shows"] = lab["n_reunion_shows"].fillna(0).astype(int)
        for df in (e, lab):
            df.insert(0, "cutoff", T)
            df.insert(0, "mode", mode)
        edges.append(e)
        labels.append(lab)
        people = pd.unique(pd.concat([train["person_a"], train["person_b"]]))
        summary.append({"mode": mode, "cutoff": T, "train_window": f"{T - W}-{T - 1}",
                        "reunion_window": f"{T}-{T + H - 1}", "n_shows": train["show_id"].nunique(),
                        "n_people": len(people), "n_edges": len(e), "n_reunited": int(lab["reunited"].sum()),
                        "reunion_rate": round(lab["reunited"].mean(), 3) if len(lab) else None})
    return pd.concat(edges), pd.concat(labels), summary


def main():
    args = parse_args(__doc__.splitlines()[0])
    shows = read_parquet(config.DATA_PROCESSED / "shows.parquet")
    shows["exclusion_reason"] = show_exclusion_reason(shows)
    core = apply_limit(shows[shows["exclusion_reason"].isna()], args.limit)
    credits = read_parquet(config.DATA_PROCESSED / "credits.parquet")
    credits = credits[credits["show_id"].isin(core["show_id"]) & credits["role"].isin(config.NETWORK_ROLES)]
    log.info("Core shows: %d | core-role credits: %d", len(core), len(credits))

    client = CachedClient(refresh=args.refresh)
    verify_ids(client, ["date_of_death"])
    qids = sorted(p for p in credits["person_id"].unique() if p.startswith("Q"))
    deaths = death_years(client, qids)
    log.info("Death years found for %d of %d people with a QID", len(deaths), len(qids))

    ps = person_show_table(credits, core, deaths)
    write_parquet(ps, OUT_DIR / "person_show.parquet")
    log.info("Person-show rows: %d | original: %s | posthumous dropped: %d",
             len(ps), ps["is_original"].astype(str).value_counts().to_dict(), int(ps["is_posthumous"].sum()))
    post = ps[ps["is_posthumous"]].merge(core[["show_id", "title"]], on="show_id")
    if len(post):
        log.info("Posthumous examples:\n%s", post.sort_values("show_year", ascending=False)
                 .head(8)[["title", "show_year", "person_name", "death_year"]].to_string(index=False))

    all_edges, all_labels, summary = [], [], []
    for mode in MODES:
        sub = ps[ps[f"in_{mode}"]]
        e, lab, s = windows(pair_rows(sub), mode)
        all_edges.append(e)
        all_labels.append(lab)
        summary += s
    write_parquet(pd.concat(all_edges), OUT_DIR / "edges_by_window.parquet")
    write_parquet(pd.concat(all_labels), OUT_DIR / "reunion_labels.parquet")
    summary = pd.DataFrame(summary)
    summary.to_csv(config.OUTPUT_TABLES / "network_windows.csv", index=False)
    log.info("Wrote outputs/tables/network_windows.csv")
    log.info("Windows (strict mode):\n%s", summary[summary["mode"] == "strict"].drop(columns="mode").to_string(index=False))
    log.info("HTTP: %d network requests, %d served from cache", client.n_network, client.n_cached)


if __name__ == "__main__":
    main()
