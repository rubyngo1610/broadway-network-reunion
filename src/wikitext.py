"""Turn wikitext into plain text with wikilinks preserved as tokens, then split
it into names. Shared by the infobox, prose and cast parsers.

render() returns (text, links): every person-like wikilink becomes the token
'\x01N\x02', where links[N] = (target, display). Lists, <br> and list
templates become newlines; refs, comments, files and citation templates are
dropped. Unknown templates are dropped and recorded in `dropped`.
"""
import html
import re

import mwparserfromhell as mw
from mwparserfromhell.nodes import Comment, ExternalLink, HTMLEntity, Heading, Tag, Template, Text, Wikilink

from src.names import wiki_title

TOKEN_RE = re.compile(r"\x01(\d+)\x02")

# Templates whose positional parameters are list items
LIST_TEMPLATES = {"plainlist", "plain list", "ubl", "unbulleted list", "flatlist", "flat list",
                  "hlist", "bulleted list", "bulletedlist", "collapsible list", "unbulletedlist",
                  "ordered list", "startplainlist", "endplainlist", "endflatlist", "cslist",
                  "cast listing", "castlist", "div col", "columns-list", "col-begin"}
# Templates whose first positional parameter is inline text to keep
INLINE_TEMPLATES = {"nowrap", "nobr", "small", "smaller", "big", "lang", "nowrap begin", "abbr",
                    "sc", "smallcaps", "small caps", "midsize", "resize", "ill", "interlanguage link",
                    "illm", "sortname", "anchor", "nobold", "noitalic", "visible anchor"}
# Templates that render a fixed character
CHAR_TEMPLATES = {"nbsp": " ", "ndash": " – ", "mdash": " — ", "snd": " – ", "spaced ndash": " – ",
                  "'": "'", "dot": " · ", "middot": " · ", "·": " · ", "•": " · ", "pipe": "|",
                  "ampersand": "&", "amp": "&"}
# Templates dropped silently (citations, footnotes, maintenance)
SILENT_TEMPLATES = re.compile(r"^(cite|citation|sfn|sfnm|harvnb|efn|refn|ref|r$|rp$|citation needed|"
                              r"cn$|when|by whom|who|clarify|dubious|failed verification|"
                              r"better source|update|as of|dead link|webarchive|use |circa|c\.$|"
                              r"lang-|ibdb|iobdb|imdb|official website|portal|reflist|notelist|"
                              r"main|see also|further|for$|about$|redirect|short description|"
                              r"sic$|nowrap end|small caps end)", re.I)


def _tname(t: Template) -> str:
    return str(t.name).strip().lower().replace("_", " ")


def _positional(t: Template):
    return [p.value for p in t.params if not p.showkey]


class Renderer:
    def __init__(self, keep_lowercase_links_as_text: bool = True, skip_tables: bool = False):
        self.links: list[tuple[str, str]] = []
        self.dropped: list[str] = []
        self.keep_lc = keep_lowercase_links_as_text
        self.skip_tables = skip_tables

    def render(self, code) -> str:
        if isinstance(code, str):
            code = mw.parse(code)
        return "".join(self._node(n) for n in code.nodes)

    def _node(self, n) -> str:
        if isinstance(n, Text):
            return str(n)
        if isinstance(n, Comment):
            return ""
        if isinstance(n, Heading):
            return "\n"
        if isinstance(n, HTMLEntity):
            return html.unescape(str(n)).replace("\xa0", " ")
        if isinstance(n, ExternalLink):
            return self.render(n.title) if n.title else ""
        if isinstance(n, Wikilink):
            return self._link(n)
        if isinstance(n, Template):
            return self._template(n)
        if isinstance(n, Tag):
            tag = str(n.tag).lower()
            if tag in ("ref", "references", "gallery", "math", "score", "timeline", "templatestyles"):
                return ""
            if tag == "br":
                return "\n"
            if tag == "table" and self.skip_tables:
                return "\n"
            if tag in ("li", "dd", "dt") or n.wiki_markup in ("*", "#", ";", ":"):
                return "\n" + (self.render(n.contents) if n.contents else "")
            if tag in ("sup",):
                return ""
            return self.render(n.contents) if n.contents else ""
        return str(n)

    def _link(self, n: Wikilink) -> str:
        target = str(n.title).strip()
        low = target.lower().lstrip(":")
        if low.startswith(("file:", "image:", "category:", "media:")):
            return ""
        display = self.render(n.text).strip() if n.text else target.split("#")[0]
        display = strip_markup(display)
        if not target or target.startswith("#") or low.startswith(("wikt:", "wiktionary:")):
            return display
        # Lowercase-initial display text is a common noun ('[[choreographed]]'), not a person
        if self.keep_lc and display[:1].islower():
            return display
        self.links.append((wiki_title(target), display))
        return f"\x01{len(self.links) - 1}\x02"

    def _template(self, t: Template) -> str:
        name = _tname(t)
        pos = _positional(t)
        if name in LIST_TEMPLATES:
            return "\n" + "\n".join(self.render(v) for v in pos) + "\n"
        if name == "hidden":
            return "\n" + (self.render(pos[1]) if len(pos) > 1 else "") + "\n"
        if name in CHAR_TEMPLATES:
            return CHAR_TEMPLATES[name]
        if name in INLINE_TEMPLATES:
            if name in ("lang",) and len(pos) > 1:
                return self.render(pos[1])
            return self.render(pos[0]) if pos else ""
        if name in ("start date", "start date and age", "opening date", "date", "dts"):
            return "-".join(strip_markup(self.render(v)) for v in pos if not str(v).strip().startswith("df"))
        if name == "based on":
            # {{Based on|work|author1|author2}} -> "work\nby author1\nauthor2"
            parts = [self.render(v) for v in pos]
            return "\n" + "\n".join(parts) + "\n"
        if name in ("lyricist and composer", "music by", "lyrics by"):
            return "\n".join(self.render(v) for v in pos)
        if SILENT_TEMPLATES.match(name):
            return ""
        self.dropped.append(name)
        return ""


def strip_markup(s: str) -> str:
    s = re.sub(r"'{2,}", "", s)
    s = s.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


# --- name splitting --------------------------------------------------------

_SEP_RE = re.compile(r"\n|;|\*|•|·|/|,(?!\s*(?:jr|sr|ii|iii)\b\.?)|\band\b|&|\bwith\b|\(|\)|\[|\]", re.I)
# Leading lowercase phrase ('additional lyrics by '), or a piece that is all lowercase words.
# Words are separated by mandatory whitespace to avoid catastrophic backtracking.
_LEADING_LOWER = re.compile(r"^(?:(?:[a-z][\w'-]*\.?\s+)*?(?:by|of|from|after|:)\s+|[a-z][\w'-]*(?:\s+[a-z][\w'-]*)*\s*:?\s*$)")
_NAME_RE = re.compile(r"^[A-ZÀ-ɏ][\w.'’\-]*(?:\s+(?:[A-ZÀ-ɏ][\w.'’\-]*|de|da|van|von|der|la|le|du|del|di|y|St\.?))*$")
_NOT_NAMES = {"various", "uncredited", "traditional", "anonymous", "unknown", "none", "see below",
              "tbd", "tba", "others", "et al", "et al.",
              # language annotations, e.g. 'Michael Kunze (German)'
              "english", "german", "french", "italian", "spanish", "hungarian", "russian", "japanese",
              "polish", "dutch", "swedish", "korean", "czech", "danish", "hebrew", "yiddish",
              "english version", "english translation", "translation", "original"}
# Capitalized words that introduce a role rather than name a person ('Music and lyrics by ...')
_ROLE_WORDS = {"music", "lyrics", "book", "words", "score", "libretto", "story", "concept",
               "additional music", "additional lyrics", "original music", "new book", "revised book"}


def looks_like_name(s: str) -> bool:
    s = re.sub(r",\s*(Jr|Sr)\.?$", r" \1.", s.strip())
    if not s or s.lower() in _NOT_NAMES | _ROLE_WORDS or any(c.isdigit() for c in s):
        return False
    return bool(_NAME_RE.match(s)) and 1 <= len(s.split()) <= 6


def split_people(text: str, links: list) -> list[dict]:
    """Split rendered text into person entries.

    Returns dicts: person_name, person_link (or None), is_linked,
    is_plausible_name, annotation (role-qualifying text such as
    'additional lyrics by').
    """
    out = []
    pending_annotation = ""
    for piece in _SEP_RE.split(text):
        piece = strip_markup(piece).strip(" .:–—-\"'")
        if not piece:
            continue
        piece = re.sub(r"^(?:Sir|Dame|Lord|Lady|Dr\.|Mr\.|Mrs\.|Ms\.)\s+(?=\x01)", "", piece)  # 'Sir [[X]]'
        tokens = [int(i) for i in TOKEN_RE.findall(piece)]
        rest = strip_markup(TOKEN_RE.sub(" ", piece)).strip(" .:–—-")
        if tokens:
            for i in tokens:
                target, display = links[i]
                out.append({"person_name": display or target, "person_link": target, "is_linked": True,
                            "is_plausible_name": True,
                            "annotation": " ".join(x for x in (pending_annotation, rest) if x) or None})
            pending_annotation = ""
            continue
        m = _LEADING_LOWER.match(rest)
        annot, name = (m.group(0).strip(), rest[m.end():].strip()) if m else ("", rest)
        if name.lower() in _ROLE_WORDS:
            annot, name = " ".join(x for x in (annot, name.lower()) if x), ""
        if not name:
            # pure annotation such as 'additional lyrics': applies to the next name,
            # or qualifies the previous one if it trails
            if out and not pending_annotation and annot and not annot.endswith(("by", "of", ":")):
                prev = out[-1]
                prev["annotation"] = " ".join(x for x in (prev["annotation"], annot) if x)
            else:
                pending_annotation = annot
            continue
        out.append({"person_name": name, "person_link": None, "is_linked": False,
                    "is_plausible_name": looks_like_name(name),
                    "annotation": " ".join(x for x in (pending_annotation, annot) if x) or None})
        pending_annotation = ""
    return out


def find_infoboxes(code) -> list[Template]:
    return [t for t in code.filter_templates(recursive=False) if _tname(t).startswith("infobox")]


HEADING_RE = re.compile(r"^(={1,6})[ \t]*(.+?)[ \t]*\1[ \t]*(?:<!--.*?-->[ \t]*)*$", re.M)


def sections(wikitext):
    """Yield (heading_path, level, section_wikicode) for every section, including the lead.

    Splits the raw text on heading lines instead of using mwparserfromhell's
    get_sections(), which misses headings when an unclosed tag earlier in the
    article swallows the rest of the page.
    """
    text = str(wikitext)
    matches = list(HEADING_RE.finditer(text))
    lead_end = matches[0].start() if matches else len(text)
    yield ("(lead)", 0, mw.parse(text[:lead_end]))
    path = {}
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = strip_markup(Renderer().render(m.group(2))) or "(untitled)"
        path[level] = title
        for lvl in [k for k in path if k > level]:
            del path[lvl]
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield (" > ".join(path[k] for k in sorted(path)), level, mw.parse(text[m.end():end]))
