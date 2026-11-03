"""Step 04: parse creative credits, productions and premiere info from wikitext.

Two extraction methods, both kept and labelled in the `extraction` column:
  infobox  person fields of {{Infobox musical}} / {{Infobox play}} etc.
           (music, lyrics, book, ...). Describes the work / original production.
  prose    '<role phrase> by <names>' sentences anywhere in the article
           ('orchestrations by [[Robert Ginzler]]'). Covers directors,
           choreographers, orchestrators, designers - but may describe a
           revival, a London run or a film, so each row carries context flags.

Outputs
  data/interim/credits_wikipedia.parquet     one row per (show, person mention)
  data/interim/infobox_shows.parquet         show-level infobox fields (basis, premiere, ...)
  data/interim/productions_wikipedia.parquet one row per line of the infobox 'productions' field
  outputs/tables/infobox_parse_issues.csv    fields/templates that could not be parsed
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mwparserfromhell as mw
import pandas as pd
from tqdm import tqdm

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.roles import normalize_role
from src.wikitext import TOKEN_RE, Renderer, find_infoboxes, sections, split_people, strip_markup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module

load_wikitext = import_module("03_fetch_wikitext").load_wikitext

# Infobox fields naming creatives -> raw role (normalized via src/roles.py)
PERSON_FIELDS = {"music", "lyrics", "book", "libretto", "writer", "concept", "conception", "conceived_by",
                 "director", "direction", "choreography", "choreographer", "orchestrations", "orchestrator",
                 "musical_director", "music_director", "producer", "producers", "composer", "lyricist",
                 "creator", "created_by", "playwright"}
# Show-level fields, not people
SHOW_FIELDS = {"name", "subtitle", "image", "image_size", "imagesize", "image_upright", "upright",
               "caption", "alt", "basis", "productions", "awards", "setting", "genre", "subject",
               "original_language", "language", "premiere_date", "premiere_location", "premiere_place",
               "place", "date", "series", "website", "characters", "mute", "chorus", "nominations",
               "native_name", "translation", "image_alt", "film"}

YEAR_RE = re.compile(r"\b(1[7-9]\d\d|20[0-3]\d)\b")
SKIP_SECTIONS = re.compile(r"references|external links|notes|sources|bibliography|further reading|"
                           r"see also|citations|footnotes", re.I)

_ROLE_PHRASE = (r"directed and choreographed|direction and choreography|directed|direction|staged|"
                r"choreographed|choreography|musical staging|dances(?: staged)?|"
                r"orchestrations?|orchestrated|musical direction|music direction|musical director|"
                r"music director|musical supervision|music supervision|vocal arrangements|"
                r"dance arrangements|dance music arranged|arrangements|"
                r"(?:scenic|set|costume|lighting|sound|projection|video) designs?|"
                r"(?:costumes|sets|scenery|lighting) (?:were |was )?designed|"
                r"scenery|sets|costumes|lighting|produced")
_HONORIFIC = r"(?:(?:Sir|Dame|Lord|Lady|Dr\.|Mr\.|Mrs\.|Ms\.)\s+)?"
_UNIT = _HONORIFIC + r"(?:\x01\d+\x02|[A-ZÀ-ɏ][\w.'’\-]+(?:\s+[A-ZÀ-ɏ][\w.'’\-]+){0,3})"
# Case-insensitive only for the role phrase; names must be capitalized
PROSE_RE = re.compile(
    rf"\b(?P<role>(?i:{_ROLE_PHRASE}))(?:\s+(?:were|was|is|are))?"
    rf"(?:\s+and\s+(?P<role2>(?i:choreographed|directed|staged)))?\s+by\s+"
    rf"(?P<names>(?:{_UNIT})(?:\s*(?:,\s*and|,|and|&)\s*(?:{_UNIT}))*)")
# '<name> (serving) as (the) <role>' / '<name> was the <role>'
_ROLE_NOUN = (r"musical director|music director|director.choreographer|director|choreographer|"
              r"orchestrator|conductor|musical supervisor|music supervisor|set designer|scenic designer|"
              r"costume designer|lighting designer|sound designer|dance arranger|vocal arranger|producer")
PROSE_AS_RE = re.compile(
    rf"(?P<names>{_UNIT})\s+(?:(?:(?:was|were|served|serving|acted|acting)\s+as|as|was|were)\s+)"
    rf"(?:the\s+|its\s+|production's\s+)?(?P<role>(?i:{_ROLE_NOUN}))\b")

# Sentence boundary, but not after initials ('Alex A. Aarons') or common abbreviations
SENT_SPLIT = re.compile(r"(?<=[.!?])(?<!\b[A-Z]\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bJr\.)(?<!\bSr\.)(?<!\bSt\.)"
                        r"(?<!\bMrs\.)\s+(?=[A-Z\x01\"'(])|\n+")


def detokenize(text: str, links) -> str:
    return strip_markup(TOKEN_RE.sub(lambda m: links[int(m.group(1))][1], text))

SECTION_TARGET_RE = re.compile(
    r"\b(production\s+history|productions?|history|background|synopsis|premiere)\b", 
    re.I
)

KEYWORD_PREMIERE_RE = re.compile(
    r"\b(premiere[d]?|debuted|first\s+performed|opened|first\s+produced)\b", 
    re.I
)

# Extract premiere year from the first few paragraphs of wikitext
PREMIERE_KEYWORDS = re.compile(r"\b(produced|premiered|opened|written|composed|created|released|broadway|west end)\b", re.I)

def extract_lead_year(code: mw.wikicode, max_paragraphs: int = 3) -> int | None:
    lead_text = ""
    for section in code.get_sections(flat=True, include_lead=True):
        lead_text = section.strip_code()
        break

    if not lead_text:
        return None

    paragraphs = [p.strip() for p in lead_text.split("\n\n") if p.strip()]

    # Step 1: Check paragraphs for premiere keywords + year
    for paragraph in paragraphs[:max_paragraphs]:
        for sentence in SENT_SPLIT.split(paragraph):
            if PREMIERE_KEYWORDS.search(sentence):
                years = YEAR_RE.findall(sentence)
                if years:
                    return int(years[0])

    # Step 2: Fallback — grab first year in first two paragraphs
    for paragraph in paragraphs[:min(2, len(paragraphs))]:
        years = YEAR_RE.findall(paragraph)
        if years:
            return int(years[0])

    return None

# Extract premier year specifically from sections titled productions or similar in article

def extract_section_premiere_year(code: mw.wikicode) -> int | None:
    """Target production/history sections specifically for premiere years."""
    # iterate through all parsed wikitext sections
    for section_title, _, sec_code in sections(code):
        if not SECTION_TARGET_RE.search(section_title):
            continue

        sec_text = sec_code.strip_code()
        sentences = SENT_SPLIT.split(sec_text)

        # Priority 1: Match sentence with explicit premiere verb + year
        for sentence in sentences:
            if KEYWORD_PREMIERE_RE.search(sentence):
                years = YEAR_RE.findall(sentence)
                if years:
                    return int(years[0])

        # Priority 2: Take first valid year in the section
        years = YEAR_RE.findall(sec_text)
        if years:
            return int(years[0])

    return None

def context_flags(sentence: str, section: str) -> dict:
    s = (sentence + " " + section).lower()
    years = sorted({int(y) for y in YEAR_RE.findall(sentence)})
    return {
        "context_years": ",".join(map(str, years)) or None,
        "mentions_broadway": "broadway" in s.replace("off-broadway", ""),
        "mentions_off_broadway": "off-broadway" in s,
        "mentions_revival": "revival" in s or "revived" in s,
        "mentions_original": "original" in s or "premiere" in s,
        "mentions_london": bool(re.search(r"london|west end", s)),
        "mentions_tour": "tour" in s,
        "mentions_film_tv": bool(re.search(r"\bfilm|movie|television|\btv\b", s)),
    }


def parse_infobox(show_id, tpl, issues):
    credits, show, productions = [], {}, []
    tname = str(tpl.name).strip()
    show["infobox_template"] = tname
    for p in tpl.params:
        field = str(p.name).strip().lower().replace(" ", "_")
        raw_value = str(p.value).strip()
        if not raw_value:
            continue
        r = Renderer()
        text = r.render(p.value)
        for d in r.dropped:
            issues.append({"show_id": show_id, "field": field, "issue": f"dropped template {{{{{d}}}}}",
                           "value": raw_value[:300]})
        if field in PERSON_FIELDS:
            people = split_people(text, r.links)
            if not people:
                issues.append({"show_id": show_id, "field": field, "issue": "no names found",
                               "value": raw_value[:300]})
            for e in people:
                role_raw = field + (f" ({e['annotation']})" if e["annotation"] else "")
                credits.append({"show_id": show_id, **e, "role_raw": role_raw,
                                "role": normalize_role(field), "extraction": "infobox",
                                "section": "infobox", "context": None})
        elif field == "productions":
            productions = parse_productions(show_id, text, r.links)
            show["productions_raw"] = detokenize(text, r.links)[:2000]
        elif field == "basis":
            show["basis"] = detokenize(text, r.links)[:1000]
            show["basis_links"] = " | ".join(t for t, _ in r.links) or None
        elif field.startswith("premiere") or field in ("date", "place"):
            show[f"infobox_{field}"] = detokenize(text, r.links)[:300]
        elif field in SHOW_FIELDS:
            continue
        elif r.links:
            # an unknown field that links to pages: maybe people, flag for review
            issues.append({"show_id": show_id, "field": field, "issue": "unhandled field with links",
                           "value": raw_value[:300]})
    return credits, show, productions


def parse_productions(show_id, text, links):
    rows = []
    for i, line in enumerate(l for l in text.split("\n") if strip_markup(TOKEN_RE.sub("x", l))):
        plain = detokenize(line, links)
        low = plain.lower()
        years = YEAR_RE.findall(plain)
        rows.append({
            "show_id": show_id, "order": i, "text": plain,
            "year": int(years[0]) if years else None,
            "is_broadway": "broadway" in low.replace("off-broadway", ""),
            "is_off_broadway": "off-broadway" in low,
            "is_revival": "revival" in low or "revived" in low,
            "is_tour": "tour" in low,
            "is_concert": "concert" in low or "encores" in low,
            "is_west_end": "west end" in low or "london" in low,
        })
    # the original Broadway production: earliest Broadway line that is not a revival/tour/concert
    cand = [r for r in rows if r["is_broadway"] and not (r["is_revival"] or r["is_tour"] or r["is_concert"])]
    cand.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["order"]))
    for r in rows:
        r["is_original_broadway"] = bool(cand) and r is cand[0]
    return rows


def parse_prose(show_id, code, issues):
    out = []
    for section, _, sec in sections(code):
        if SKIP_SECTIONS.search(section):
            continue
        r = Renderer()
        text = r.render(sec)
        for sentence in SENT_SPLIT.split(text):
            matches = [(m, "by") for m in PROSE_RE.finditer(sentence)]
            matches += [(m, "as") for m in PROSE_AS_RE.finditer(sentence)]
            for m, kind in matches:
                if kind == "by":
                    # 'directed and choreographed by X' credits X with both roles
                    roles = re.split(r"\s+and\s+", m.group("role")) + ([m.group("role2")] if m.group("role2") else [])
                else:
                    roles = re.split(r"\W", m.group("role")) if "choreographer" in m.group("role").lower() \
                        and "director" in m.group("role").lower() else [m.group("role")]
                people = split_people(m.group("names"), r.links)
                ctx = context_flags(detokenize(sentence, r.links), section)
                for phrase in roles:
                    for e in people:
                        out.append({"show_id": show_id, **e,
                                    "role_raw": f"prose: {phrase.lower()} by" if kind == "by" else f"prose: as {phrase.lower()}",
                                    "role": normalize_role(phrase), "extraction": "prose",
                                    "section": section, "context": detokenize(sentence, r.links)[:400],
                                    **ctx})
    return out


def main():
    args = parse_args(__doc__.splitlines()[0])
    shows = apply_limit(read_parquet(config.DATA_INTERIM / "shows.parquet"), args.limit)
    index = read_parquet(config.DATA_INTERIM / "wikitext_index.parquet")
    index = index[index["show_id"].isin(shows["show_id"])]

    credits, show_rows, productions, issues = [], [], [], []
    templates = Counter()
    for show_id, title in tqdm(list(zip(index["show_id"], index["enwiki_title"])), desc="parse"):
        rec = load_wikitext(title)
        if not rec or not rec.get("wikitext"):
            issues.append({"show_id": show_id, "field": None, "issue": "no wikitext", "value": title})
            continue
        code = mw.parse(rec["wikitext"])
        boxes = find_infoboxes(code)

        # Extract lead section/sentence year fallback
        first_sent_year = extract_lead_year(code)
        section_year = extract_section_premiere_year(code)
       
        row = {
            "show_id": show_id,
            "enwiki_title": rec["resolved_title"],
            "has_infobox": bool(boxes),
            "n_infoboxes": len(boxes),
            "first_sentence_year": first_sent_year,
            "section_premiere_year": section_year,
        }

        if boxes:
            # Use the first infobox; later ones are usually films/recordings
            c, s, p = parse_infobox(show_id, boxes[0], issues)
            credits += c
            productions += p
            row.update(s) # Merges infobox keys (like productions_raw, infobox_premiere_date) into row
            templates[s["infobox_template"].lower()] += 1
        else:
            issues.append({"show_id": show_id, "field": None, "issue": "no infobox", "value": title})

        credits += parse_prose(show_id, code, issues)
        show_rows.append(row)

    cred = pd.DataFrame(credits)
    cred["source"] = "wikipedia"
    flag_cols = ["mentions_broadway", "mentions_off_broadway", "mentions_revival", "mentions_original",
                 "mentions_london", "mentions_tour", "mentions_film_tv"]
    for c in flag_cols + ["context_years"]:
        if c not in cred:
            cred[c] = None
    cols = ["show_id", "person_name", "person_link", "role_raw", "role", "is_linked", "is_plausible_name",
            "annotation", "extraction", "section", "context", "context_years"] + flag_cols + ["source"]
    cred = cred[cols].drop_duplicates().reset_index(drop=True)
    write_parquet(cred, config.DATA_INTERIM / "credits_wikipedia.parquet")

    prod = pd.DataFrame(productions)
    if not prod.empty:
        prod["year"] = prod["year"].astype("Int64")
    write_parquet(prod, config.DATA_INTERIM / "productions_wikipedia.parquet")

    sh = pd.DataFrame(show_rows)
    if not prod.empty:
        orig = prod[prod["is_original_broadway"]].set_index("show_id")["year"]
        sh["original_broadway_year"] = sh["show_id"].map(orig).astype("Int64")
        sh["n_productions_listed"] = sh["show_id"].map(prod.groupby("show_id").size()).fillna(0).astype(int)

    # -------------------------------------------------------------------------
    # PREMIERE YEAR EXTRACTION & FALLBACK CHAIN
    # -------------------------------------------------------------------------

    # Step 1: Primary source — extract premiere_year from explicit infobox premiere/date fields
    prem_cols = [c for c in sh.columns if c.startswith("infobox_premiere") or c == "infobox_date"]
    if prem_cols:
        prem = sh[prem_cols].fillna("").astype(str).agg(" ".join, axis=1)
        sh["premiere_year"] = prem.str.extract(YEAR_RE, expand=False).astype("Int64")
    else:
        sh["premiere_year"] = pd.Series(dtype="Int64", index=sh.index)

    # Step 2: Fallback 1 — use `original_broadway_year` calculated from parsed productions
    if "original_broadway_year" in sh.columns:
        sh["premiere_year"] = sh["premiere_year"].fillna(sh["original_broadway_year"])

    # Step 3: Fallback 2 — extract the earliest year directly from raw infobox productions text
    if "productions_raw" in sh.columns:
        prod_raw_years = sh["productions_raw"].fillna("").str.extract(YEAR_RE, expand=False).astype("Int64")
        sh["premiere_year"] = sh["premiere_year"].fillna(prod_raw_years)

    # Step 4: Fallback 3 — legacy production_year column check (if present)
    if "production_year" in sh.columns:
        sh["premiere_year"] = sh["premiere_year"].fillna(sh["production_year"])

    # Step 5: Fall back 4 - specifically listed in a separate sections (titled productions or similar) rather than first few paras
    if "section_premiere_year" in sh.columns:
        sh["premiere_year"] = sh["premiere_year"].fillna(sh["section_premiere_year"])     

    # Step 6: Fallback 5 — lead paragraph/sentence year fallback & recovery logging
    if "first_sentence_year" in sh.columns:
        # Apply lead text fallback
        sh["premiere_year"] = sh["premiere_year"].fillna(sh["first_sentence_year"]).astype("Int64")

    
    write_parquet(sh, config.DATA_INTERIM / "infobox_shows.parquet")

    iss = pd.DataFrame(issues, columns=["show_id", "field", "issue", "value"])
    iss.to_csv(config.OUTPUT_TABLES / "infobox_parse_issues.csv", index=False)

    log.info("Infobox templates: %s", dict(templates))
    log.info("Shows parsed: %d | with infobox %d | issues logged %d (outputs/tables/infobox_parse_issues.csv)",
             len(sh), sh["has_infobox"].sum() if len(sh) else 0, len(iss))
    if not cred.empty:
        log.info("Credits by extraction x role:\n%s",
                 pd.crosstab(cred["role"], cred["extraction"]).to_string())
        log.info("Linked %.0f%% | plausible-name %.0f%%", 100 * cred.is_linked.mean(),
                 100 * cred.is_plausible_name.mean())


if __name__ == "__main__":
    main()
