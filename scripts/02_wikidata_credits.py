"""Step 02: creative credits and person attributes from Wikidata.

For every show with a QID, pulls each creative-role statement listed in
src/wikidata.py ROLE_PROPS (with the 'object of statement has role'
qualifier and statement rank), then pulls origin fields for every person QID.

Outputs: data/interim/credits_wikidata.parquet, data/interim/people_wikidata.parquet
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.http_client import CachedClient
from src.wikidata import (P, QUALIFIER_PROPS, ROLE_PROPS, PERSON_PROPS, CLASSES,
                          fetch_people, sparql_values_batches, verify_ids)

ROLE_VALUES = " ".join(f'("{k}" p:{pid} ps:{pid})' for k, (pid, _) in ROLE_PROPS.items())

CREDITS_QUERY = f"""
SELECT ?show ?role ?person ?personLabel ?qualRole ?qualRoleLabel ?rank WHERE {{
  VALUES ?show {{ {{values}} }}
  VALUES (?role ?p ?ps) {{ {ROLE_VALUES} }}
  ?show ?p ?st. ?st ?ps ?person; wikibase:rank ?rank.
  OPTIONAL {{ ?person rdfs:label ?personLabel FILTER(lang(?personLabel)="en") }}
  OPTIONAL {{ ?st pq:{P('object_has_role')} ?qualRole.
             OPTIONAL {{ ?qualRole rdfs:label ?qualRoleLabel FILTER(lang(?qualRoleLabel)="en") }} }}
}}"""


def main():
    args = parse_args(__doc__.splitlines()[0])
    client = CachedClient(refresh=args.refresh)
    verify_ids(client, list(ROLE_PROPS) + list(QUALIFIER_PROPS) + list(PERSON_PROPS) + list(CLASSES)
               + ["instance_of"])

    shows = apply_limit(read_parquet(config.DATA_INTERIM / "shows.parquet"), args.limit)
    qids = shows["wikidata_qid"].dropna().unique()
    log.info("Querying credits for %d shows with a QID (%d without a QID skipped)",
             len(qids), shows["wikidata_qid"].isna().sum())

    raw = sparql_values_batches(client, CREDITS_QUERY, qids, "credits")
    if raw.empty:
        log.warning("No credits returned")
        return
    raw["rank"] = raw["rank"].str.rsplit("#", n=1).str[-1].str.replace("Rank", "").str.lower()
    # 'unknown value' statements come back as blank-node URIs, not QIDs
    raw["is_unknown_value"] = ~raw["person"].str.match(r"^Q\d+$", na=False)
    raw.loc[raw["is_unknown_value"], "person"] = None

    show_qid_to_id = dict(zip(shows["wikidata_qid"], shows["show_id"]))
    credits = raw.rename(columns={"person": "person_qid", "personLabel": "person_label",
                                  "qualRole": "role_qualifier_qid", "qualRoleLabel": "role_qualifier"})
    credits["show_id"] = credits["show"].map(show_qid_to_id)
    credits["prop_id"] = credits["role"].map(lambda k: ROLE_PROPS[k][0])
    credits["role_raw"] = credits["role"] + credits["role_qualifier"].map(
        lambda r: f" ({r})" if isinstance(r, str) else "")
    credits["source"] = "wikidata"
    credits = (credits[["show_id", "person_qid", "person_label", "role", "role_raw", "prop_id",
                        "role_qualifier", "role_qualifier_qid", "rank", "is_unknown_value", "source"]]
               .drop_duplicates()
               .sort_values(["show_id", "role", "person_qid"])
               .reset_index(drop=True))
    write_parquet(credits, config.DATA_INTERIM / "credits_wikidata.parquet")

    people = fetch_people(client, credits["person_qid"].dropna().unique())

    # TIGHTEN ORIGINAL RULES: extract death_year
    # Parse 4-digit death year if a death_date or date_of_death column exists
    death_col = next((c for c in ["death_date", "date_of_death", "death_year"] if c in people.columns), None)
    if death_col and death_col != "death_year":
        people["death_year"] = (
            people[death_col]
            .astype(str)
            .str.extract(r"(\b\d{4}\b)")[0]
            .astype("Int64")
        )

    write_parquet(people, config.DATA_INTERIM / "people_wikidata.parquet")

    log.info("Credits by role:\n%s", credits["role"].value_counts().to_string())
    log.info("Shows with >=1 credit: %d / %d", credits["show_id"].nunique(), len(qids))
    if not people.empty:
        log.info("People: %d | human %d | birthplace %d | coords %d | citizenship %d | birth year %d",
                 len(people), people.is_human.sum(), people.birthplace_qid.notna().sum(),
                 people.lat.notna().sum(), people.citizenship.notna().sum(),
                 people.birth_year.notna().sum())
    log.info("HTTP: %d network requests, %d served from cache", client.n_network, client.n_cached)


if __name__ == "__main__":
    main()
