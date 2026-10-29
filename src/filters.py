"""Show-set filters. These only select rows for analysis; nothing is deleted from data/."""
import pandas as pd

import config


def show_exclusion_reason(shows: pd.DataFrame) -> pd.Series:
    """Why each show is outside the core set (None = in the core set).

    subcategory_page  found only in a per-show Wikipedia subcategory (songs, albums, films, people)
                      and in neither Wikidata query
    before_<year>     known year earlier than config.CORE_MIN_YEAR
    Shows with an unknown year stay in: most are real shows whose year was not recorded.
    """
    sub_only = (shows["wp_category_depth"].eq(1)
                & ~shows["in_wd_ibdb_query"].fillna(False).astype(bool)
                & ~shows["in_wd_venue_query"].fillna(False).astype(bool))
    early = shows["year"].lt(config.CORE_MIN_YEAR).fillna(False).astype(bool)
    reason = pd.Series(None, index=shows.index, dtype=object)
    reason[early] = f"before_{config.CORE_MIN_YEAR}"
    reason[sub_only] = "subcategory_page"  # takes precedence over the year
    return reason


def core_shows(shows: pd.DataFrame) -> pd.DataFrame:
    return shows[show_exclusion_reason(shows).isna()]
