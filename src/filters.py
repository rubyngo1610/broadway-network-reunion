"""Show-set filters. These only select rows for analysis; nothing is deleted from data/."""
import pandas as pd

import config

# --- TASK 5 EDIT: Wikidata instance_of types that are not stage works ---
NON_STAGE_INSTANCES = {
    # films and TV
    "film", "film adaptation", "animated film", "television film", "television series",
    "television series episode", "television special",
    # recordings and songs
    "album", "soundtrack album", "cast recording", "music album", "single", "song", "audio track", "discography",
    # people, groups, characters
    "human", "musical group", "musical duo", "singing duo", "male duo", "dance troupe", "theatre company",
    "film character", "musical theatre character", "fictional human", "occupation",
    # list and other non-work pages
    "wikimedia music-related list", "wikimedia list article", "wikimedia disambiguation page", "award",
    "biographical novel",
}
# A show typed with any of these stays in even if it also has a non-stage type
STAGE_INSTANCES = {
    "dramatico-musical work", "musical production", "theatrical production", "performing arts production",
    "musical play", "revue", "theatrical work", "show",
}


# Pages in the main Wikipedia category that are not one show (checked by hand, 2026-11-02)
MANUAL_EXCLUDE = {
    "Q152521": "Ziegfeld Follies: article about the whole series",
    "Q4743580": "American Dance Machine: a dance company",
}


def _instance_sets(shows: pd.DataFrame) -> pd.Series:
    """wd_instance_of holds several types joined with '|'."""
    return shows["wd_instance_of"].fillna("").str.lower().str.split("|").map(lambda v: {t.strip() for t in v} - {""})


def show_exclusion_reason(shows: pd.DataFrame) -> pd.Series:
    """Why each show is outside the core set (None = in the core set).

    subcategory_page  found only in a per-show Wikipedia subcategory (songs, albums, films, people)
                      and in neither Wikidata query
    before_<year>     known year earlier than config.CORE_MIN_YEAR
    manual_exclude    in MANUAL_EXCLUDE (series or company pages in the main category)
    non_stage         not in the main Wikipedia category, and Wikidata says it is a film, album, song, person or list page, not a stage work
    no_year           no year from any source (mostly minor early shows with no Wikipedia article);
                      they cannot be placed in a time window
    """
    sub_only = (shows["wp_category_depth"].eq(1)
                & ~shows["in_wd_ibdb_query"].fillna(False).astype(bool)
                & ~shows["in_wd_venue_query"].fillna(False).astype(bool))
    early = shows["year"].lt(config.CORE_MIN_YEAR).fillna(False).astype(bool)
    # --- TASK 5 EDIT: non-stage items (films, albums, songs, people, list pages) ---
    # Not applied to pages in the main Wikipedia category: those articles are about the stage show
    # even when Wikidata mistypes the item (The Belle of Bohemia is typed "film").
    types = _instance_sets(shows)
    in_main_category = shows["wp_category_depth"].eq(0).fillna(False).astype(bool)
    is_non_stage = types.map(lambda t: bool(t & NON_STAGE_INSTANCES) and not (t & STAGE_INSTANCES)) & ~in_main_category

    reason = pd.Series(None, index=shows.index, dtype=object)
    reason[shows["year"].isna()] = "no_year"
    reason[early] = f"before_{config.CORE_MIN_YEAR}"
    reason[is_non_stage] = "non_stage"
    reason[shows["show_id"].isin(MANUAL_EXCLUDE)] = "manual_exclude"
    reason[sub_only] = "subcategory_page"  # takes precedence over the year
    return reason


def core_shows(shows: pd.DataFrame) -> pd.DataFrame:
    return shows[show_exclusion_reason(shows).isna()]
