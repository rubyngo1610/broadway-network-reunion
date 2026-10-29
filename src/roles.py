"""Fixed role vocabulary and the mapping from raw role strings onto it.

Raw strings come from Wikidata property keys (+ 'object has role'
qualifiers), infobox field names, and prose phrases ('orchestrations by').
The raw string is always kept alongside as role_raw.
"""
import re

ROLE_VOCAB = [
    # authorship
    "composer", "lyricist", "book_writer", "playwright", "conceived_by",
    # staging
    "director", "choreographer",
    # music staff
    "orchestrator", "music_director", "music_supervisor", "arranger",
    # design
    "scenic_designer", "costume_designer", "lighting_designer", "sound_designer", "projection_designer",
    # business
    "producer", "production_company",
    # unclear on the source side
    "author_unspecified", "creator_unspecified", "other_creative",
]

# Exact keys (Wikidata ROLE_PROPS keys and infobox field names)
_EXACT = {
    "composer": "composer", "music": "composer",
    "lyricist": "lyricist", "lyrics": "lyricist",
    "librettist": "book_writer", "book": "book_writer", "libretto": "book_writer",
    "writer": "playwright", "playwright": "playwright", "screenwriter": "author_unspecified",
    "concept": "conceived_by", "conception": "conceived_by", "conceived_by": "conceived_by",
    "director": "director", "direction": "director",
    "choreographer": "choreographer", "choreography": "choreographer",
    "orchestrator": "orchestrator", "orchestrations": "orchestrator", "orchestration": "orchestrator",
    "musical_conductor": "music_director", "musical_director": "music_director",
    "music_director": "music_director",
    "scenographer": "scenic_designer", "production_designer": "scenic_designer",
    "costume_designer": "costume_designer", "lighting_designer": "lighting_designer",
    "sound_designer": "sound_designer", "video_designer": "projection_designer",
    "projection_designer": "projection_designer",
    "dramaturge": "other_creative",
    "producer": "producer", "producers": "producer", "executive_producer": "producer",
    "production_company": "production_company",
    "author": "author_unspecified", "creator": "creator_unspecified", "created_by": "creator_unspecified",
    "contributor": "other_creative",
}

# Keyword rules for free text (qualifier labels, prose phrases); first match wins
_KEYWORDS = [
    (r"director.?choreograph|directed and choreographed|direction and choreography", "director"),
    (r"orchestrat", "orchestrator"),
    (r"music(al)? supervis", "music_supervisor"),
    (r"music(al)? direct|conduct", "music_director"),
    (r"arrange", "arranger"),
    (r"choreograph|musical staging|dances", "choreographer"),
    (r"direct|staged|stage director", "director"),
    (r"scen|set design|sets\b|scenery|production design", "scenic_designer"),
    (r"costume", "costume_designer"),
    (r"lighting", "lighting_designer"),
    (r"sound", "sound_designer"),
    (r"projection|video", "projection_designer"),
    (r"lyric", "lyricist"),
    (r"compos|\bmusic\b|\bscore\b", "composer"),
    (r"libret|\bbook\b", "book_writer"),
    (r"produc", "producer"),
    (r"concept|conceiv", "conceived_by"),
]


def normalize_role(raw: str) -> str:
    if not raw:
        return "other_creative"
    key = raw.strip().lower().replace(" ", "_")
    if key in _EXACT:
        return _EXACT[key]
    text = raw.lower().replace("_", " ")
    for pattern, role in _KEYWORDS:
        if re.search(pattern, text):
            return role
    return "other_creative"
