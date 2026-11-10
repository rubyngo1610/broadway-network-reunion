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


# Shows that never ran on Broadway, checked by hand 2026-11-02. They enter through Wikidata's IBDB IDs
# (IBDB also lists US tours) or the main category. Only shows we are certain about are listed.
NEVER_ON_BROADWAY = {
    "Q1051695": "We Will Rock You: West End and tours",
    "Q1458184": "Martin Guerre: West End and tours",
    "Q950119": "Whistle Down the Wind (1996): closed in its Washington tryout",
    "Q29017615": "Doctor Dolittle: West End and US tour",
    "Q2255873": "Copacabana: West End and US tours",
    "Q7091479": "On the Record: US tour",
    "Q5457609": "Flashdance: West End and US tour",
    "Q7719011": "The Bodyguard: West End and US tour",
    "Q6650366": "Little House on the Prairie: regional and US tour",
    "Q7711731": "The 101 Dalmatians Musical: US tour (Broadway run cancelled)",
    "Q16841823": "Happy Days (2007): regional and tours",
    "Q20899494": "Love Birds (Sherman, 2015): Edinburgh Fringe",
    "Q1425565": "Tick, Tick... Boom!: Off-Broadway",
    "Q4753455": "And the World Goes 'Round: Off-Broadway",
    "Q2336119": "High School Musical on Stage!: licensed stage version",
}


# Operas, dropped by team decision 2026-11-09 (operas that played Broadway are dropped too).
# Found among the ~90 core shows that are neither in the Wikipedia musicals category nor typed
# as a musical in Wikidata, then checked by hand: the article uses {{Infobox opera}} or its lead
# calls the work an opera. Operettas, comic operas (Gilbert & Sullivan) and revues stay in:
# they belong to musical-theatre history. Works in the musicals category (Porgy and Bess,
# Street Scene, Four Saints in Three Acts) also stay in.
OPERAS = {
    "Q192941": "Tosca",
    "Q654633": "Ariadne auf Naxos",
    "Q593511": "The Consul (Menotti)",
    "Q5494819": "Regina (Blitzstein)",
    "Q1169743": "The Medium (Menotti)",
    "Q1170527": "The Telephone (Menotti)",
    "Q3989123": "The Saint of Bleecker Street (Menotti)",
    "Q6761228": "Maria Golovin (Menotti)",
    "Q377876": "Trouble in Tahiti (Bernstein)",
    "Q1197934": "The Eternal Road (Weill)",
    "Q240685": "The Rape of Lucretia (Britten)",
    "Q467698": "The Little Sweep (Britten)",
    "Q2966173": "Christophe Colomb (Milhaud)",
    "Q55635588": "The Transposed Heads (Glanville-Hicks)",
    "Q5036691": "Captain Jinks of the Horse Marines (Beeson)",
    "Q628536": "Monna Vanna (Février)",
    "Q65065531": "A Letter for Queen Victoria (Wilson)",
    "Q727868": "Gianni Schicchi (Puccini)",
    "Q471725": "The Fair at Sorochyntsi (Mussorgsky)",
    "Q7715398": "The Ballad of Baby Doe (Moore)",
    "Q775812": "Treemonisha (Joplin)",
    "Q8012710": "Madeleine (Herbert, one-act opera)",
    "Q4902482": "Bianca (Hadley, one-act opera)",
}


def _instance_sets(shows: pd.DataFrame) -> pd.Series:
    """wd_instance_of holds several types joined with '|'."""
    return shows["wd_instance_of"].fillna("").str.lower().str.split("|").map(lambda v: {t.strip() for t in v} - {""})


def show_exclusion_reason(shows: pd.DataFrame) -> pd.Series:
    """Why each show is outside the core set (None = in the core set).

    subcategory_page  found only in a per-show Wikipedia subcategory (songs, albums, films, people)
                      and in neither Wikidata query
    before_<year>     known year earlier than config.CORE_MIN_YEAR
    never_on_broadway in NEVER_ON_BROADWAY (tours, West End or Off-Broadway only)
    opera             in OPERAS (operas, including those that played Broadway)
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
    reason[shows["show_id"].isin(NEVER_ON_BROADWAY)] = "never_on_broadway"
    reason[shows["show_id"].isin(OPERAS)] = "opera"
    reason[sub_only] = "subcategory_page"  # takes precedence over the year
    return reason


def core_shows(shows: pd.DataFrame) -> pd.DataFrame:
    return shows[show_exclusion_reason(shows).isna()]
