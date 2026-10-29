"""Name and title normalization."""
import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation/suffixes, collapse whitespace.

    'Oscar Hammerstein II' -> 'oscar hammerstein'
    'José  Ferrer, Jr.'    -> 'jose ferrer'
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    return " ".join(tokens)


def wiki_title(title: str) -> str:
    """Canonical form of an enwiki page title (as MediaWiki would store it)."""
    if not title:
        return ""
    t = title.replace("_", " ").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.split("#", 1)[0].strip()  # drop section anchors
    if t.startswith(":"):
        t = t[1:]
    return t[:1].upper() + t[1:] if t else t


def enwiki_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + wiki_title(title).replace(" ", "_")
