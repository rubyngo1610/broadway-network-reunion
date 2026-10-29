"""Step 04b (optional): performers, kept separate from creative credits.

Sources
  table     wikitables in sections whose heading mentions 'cast'
            (first column = character, one column per production)
  list      bulleted lines in those sections: 'Character – Actor' or 'Actor as Character'
  wikidata  cast member (P161) statements on the show item, with character role (P453)

Sections about cast *recordings* are albums and are skipped (and counted).
Nothing here is merged into credits.parquet.

Output: data/processed/cast_credits.parquet
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mwparserfromhell as mw
import pandas as pd
from mwparserfromhell.nodes import Tag
from tqdm import tqdm

import config
from src.common import apply_limit, log, parse_args, read_parquet, write_parquet
from src.http_client import CachedClient
from src.wikidata import P, sparql_values_batches, verify_ids
from src.wikitext import TOKEN_RE, Renderer, sections, split_people, strip_markup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module

load_wikitext = import_module("03_fetch_wikitext").load_wikitext

CAST_HEADING = re.compile(r"\bcast", re.I)
SKIP_HEADING = re.compile(r"recording|album|discograph|casting|broadcast", re.I)
NOT_ORIGINAL = re.compile(r"revival|tour|london|west end|film|movie|television|\btv\b|concert|encores|"
                          r"off-broadway|replacement|austria|germany|japan|australia|uk\b|toronto|"
                          r"other|notable|subsequent|later", re.I)
DASH_SPLIT = re.compile(r"\s+[–—-]\s+|\s*:\s+")
AS_SPLIT = re.compile(r"\s+as\s+")

CAST_QUERY = f"""
SELECT ?show ?person ?personLabel ?character ?characterLabel ?characterText WHERE {{
  VALUES ?show {{ {{values}} }}
  ?show p:{P('cast_member')} ?st. ?st ps:{P('cast_member')} ?person.
  OPTIONAL {{ ?person rdfs:label ?personLabel FILTER(lang(?personLabel)="en") }}
  OPTIONAL {{ ?st pq:{P('character_role')} ?character.
             OPTIONAL {{ ?character rdfs:label ?characterLabel FILTER(lang(?characterLabel)="en") }} }}
}}"""


def detok(text, links):
    return strip_markup(TOKEN_RE.sub(lambda m: links[int(m.group(1))][1], text))


def original_broadway_flag(label: str, is_column: bool = False):
    """True / False / None (unknown) for a table column header or section heading.

    A column header that names a production without mentioning Broadway or
    'original' ('Budapest 2007') is some other production, so False; a section
    heading like that ('United States') stays unknown."""
    low = (label or "").lower()
    if "original broadway" in low:
        return True
    if NOT_ORIGINAL.search(low):
        return False
    if "broadway" in low:
        return True
    if is_column and low.strip() and "original" not in low:
        return False
    return None


def _span(cell, attr):
    try:
        return max(1, int(str(cell.get(attr).value).strip().strip("'\"")))
    except (ValueError, AttributeError):
        return 1


def table_grid(table: Tag):
    """Expand a wikitable into rows of (is_header, rendered_text, links) cells,
    honouring colspan/rowspan."""
    # A header row not preceded by '|-' is parsed as loose cells outside any <tr>;
    # treat such runs of cells as an implicit row.
    rows, loose = [], []
    for n in table.contents.nodes:
        if not isinstance(n, Tag):
            continue
        if str(n.tag) in ("th", "td"):
            loose.append(n)
        elif str(n.tag) == "tr":
            if loose:
                rows.append(loose)
                loose = []
            rows.append([c for c in n.contents.nodes if isinstance(c, Tag) and str(c.tag) in ("th", "td")])
    if loose:
        rows.append(loose)
    grid, pending = [], {}  # pending: col -> [rows_left, cell]
    for cells in rows:
        rendered = []
        for c in cells:
            r = Renderer()
            rendered.append((str(c.tag) == "th", r.render(c.contents), r.links, _span(c, "colspan"), _span(c, "rowspan")))
        out, col, i = [], 0, 0
        max_pending = max(pending) if pending else -1
        while i < len(rendered) or col <= max_pending:
            if col in pending:
                left, cell = pending[col]
                out.append(cell)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col][0] -= 1
                col += 1
                continue
            if i >= len(rendered):
                col += 1
                continue
            is_h, text, links, cs, rs = rendered[i]
            i += 1
            for _ in range(cs):
                if rs > 1:
                    pending[col] = [rs - 1, (is_h, text, links)]
                out.append((is_h, text, links))
                col += 1
        if out:
            grid.append(out)
    return grid


def parse_table(show_id, section, table):
    grid = table_grid(table)
    header_rows = []
    for row in grid:
        if all(is_h for is_h, *_ in row):
            header_rows.append(row)
        else:
            break
    body = grid[len(header_rows):]
    ncol = max((len(r) for r in grid), default=0)
    labels = []
    for j in range(ncol):
        parts = []
        for hr in header_rows:
            if j < len(hr):
                t = detok(hr[j][1], hr[j][2]).replace("\n", " ")
                if t and t not in parts:
                    parts.append(t)
        labels.append(" ".join(parts))
    out = []
    first_broadway_col = next((j for j in range(1, ncol) if original_broadway_flag(labels[j], True)), None)
    for row in body:
        if len(row) < 2:
            continue
        character = detok(row[0][1], row[0][2]).replace("\n", " ")
        for j in range(1, len(row)):
            _, text, links = row[j]
            orig = original_broadway_flag(labels[j], True) if j < len(labels) else None
            if orig and j != first_broadway_col and "original" not in labels[j].lower():
                orig = False  # a later Broadway production
            for e in split_people(text, links):
                out.append({"show_id": show_id, "character": character or None,
                            "person_name": e["person_name"], "person_link": e["person_link"],
                            "is_linked": e["is_linked"], "is_plausible_name": e["is_plausible_name"],
                            "note": e["annotation"],
                            "production_label": labels[j] if j < len(labels) else None,
                            "is_original_broadway": orig,
                            "extraction": "table", "section": section})
    return out


def parse_list(show_id, section, sec_code):
    r = Renderer(skip_tables=True)
    text = r.render(sec_code)
    out = []
    orig = original_broadway_flag(section)
    for line in text.split("\n"):
        line = line.strip()
        if not line or not TOKEN_RE.search(line) and not re.search(r"[–—:]| as ", line):
            continue
        if AS_SPLIT.search(line) and not DASH_SPLIT.search(line):
            actor_part, char_part = AS_SPLIT.split(line, maxsplit=1)
            pattern = "actor as character"
        else:
            parts = DASH_SPLIT.split(line, maxsplit=1)
            if len(parts) != 2:
                continue
            char_part, actor_part = parts
            pattern = "character – actor"
        character = detok(char_part, r.links)
        for e in split_people(actor_part, r.links):
            out.append({"show_id": show_id, "character": character or None,
                        "person_name": e["person_name"], "person_link": e["person_link"],
                        "is_linked": e["is_linked"], "is_plausible_name": e["is_plausible_name"],
                        "note": e["annotation"], "production_label": section,
                        "is_original_broadway": orig, "extraction": f"list ({pattern})", "section": section})
    return out


def main():
    args = parse_args(__doc__.splitlines()[0])
    client = CachedClient(refresh=args.refresh)
    shows = apply_limit(read_parquet(config.DATA_INTERIM / "shows.parquet"), args.limit)
    index = read_parquet(config.DATA_INTERIM / "wikitext_index.parquet")
    index = index[index["show_id"].isin(shows["show_id"])]

    rows, skipped_sections = [], 0
    for show_id, title in tqdm(list(zip(index["show_id"], index["enwiki_title"])), desc="casts"):
        rec = load_wikitext(title)
        if not rec or not rec.get("wikitext"):
            continue
        code = mw.parse(rec["wikitext"])
        for section, _, sec in sections(code):
            leaf = section.split(" > ")[-1]
            if not CAST_HEADING.search(section):
                continue
            if SKIP_HEADING.search(leaf):
                skipped_sections += 1
                continue
            # only this section's own content, not nested subsections (they are visited separately)
            for t in sec.filter_tags(recursive=True, matches=lambda n: str(n.tag) == "table"):
                rows += parse_table(show_id, section, t)
            rows += parse_list(show_id, section, sec)

    # Wikidata cast statements
    verify_ids(client, ["cast_member", "character_role"])
    wd = sparql_values_batches(client, CAST_QUERY, shows["wikidata_qid"].dropna().unique(), "cast")
    if not wd.empty:
        qid_to_show = dict(zip(shows["wikidata_qid"], shows["show_id"]))
        for _, w in wd.iterrows():
            rows.append({"show_id": qid_to_show.get(w["show"]),
                         "character": w.get("characterLabel") or w.get("character"),
                         "person_name": w.get("personLabel") or w["person"], "person_link": None,
                         "person_qid": w["person"] if str(w["person"]).startswith("Q") else None,
                         "is_linked": True, "is_plausible_name": True, "note": None,
                         "production_label": None, "is_original_broadway": None,
                         "extraction": "wikidata", "section": None})

    cast = pd.DataFrame(rows)
    if cast.empty:
        log.warning("No cast data found")
        return
    if "person_qid" not in cast:
        cast["person_qid"] = None
    cast["source"] = (cast["extraction"] == "wikidata").map({True: "wikidata", False: "wikipedia"})
    cast["is_original_broadway"] = cast["is_original_broadway"].astype("boolean")
    cast = cast.drop_duplicates().reset_index(drop=True)
    write_parquet(cast, config.DATA_PROCESSED / "cast_credits.parquet")

    n_shows = len(shows)
    with_cast = cast["show_id"].nunique()
    log.info("Shows with any cast data: %d / %d (%.0f%%); recording sections skipped: %d",
             with_cast, n_shows, 100 * with_cast / max(n_shows, 1), skipped_sections)
    log.info("Rows by extraction:\n%s", cast["extraction"].value_counts().to_string())
    log.info("Original-Broadway flag: %s", cast["is_original_broadway"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()
