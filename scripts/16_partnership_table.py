"""Step 16: table: past partners work together again; strangers on big teams rarely do.

For every show that opened in 1900-2015 (strict credits by default), each pair of teammates is one
observation: did the two share another show within the next 10 years? Pairs are grouped by team
size and by how many shows the two had done together before. A pair on several shows counts once
per show.

Outputs
  outputs/tables/reunion_by_team_size_history.csv   long form: count, rate and 95% Wilson interval per group
  outputs/tables/reunion_by_team_size_history.md    the readable table: team size x shows together before
"""
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from src.common import display_path, log, parse_args
from src.network import in_mode, load_person_show

YEARS = (1900, 2015)    # shows after 2015 have no full 10-year follow-up in the data
HORIZON = config.NETWORK_HORIZON_YEARS
BANDS = [(2, 3, "2–3"), (4, 5, "4–5"), (6, 8, "6–8"), (9, 10_000, "9+")]
HISTORY = ["first time together", "1 show together before", "2+ shows together before"]
MIN_N = 30              # groups with fewer pairs are flagged as small


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def pair_table(ps, mode):
    m = in_mode(ps, mode)
    year = m.groupby("show_id")["year"].first()
    team = m.groupby("show_id")["person_id"].apply(set)
    shows_of = defaultdict(set)
    for r in m.itertuples():
        shows_of[r.person_id].add(r.show_id)
    rows = []
    for show, people in team.items():
        y, n = year[show], len(people)
        if n < 2 or not YEARS[0] <= y <= YEARS[1]:
            continue
        band = next(lbl for lo, hi, lbl in BANDS if lo <= n <= hi)
        for a, b in combinations(sorted(people), 2):
            both = shows_of[a] & shows_of[b]
            before = sum(year[s] < y for s in both)
            again = any(y < year[s] < y + HORIZON for s in both)
            rows.append((show, y, band, HISTORY[min(before, 2)], again))
    return pd.DataFrame(rows, columns=["show_id", "year", "team_size", "history", "again"])


def summarise(pairs):
    g = pairs.groupby(["team_size", "history"])["again"].agg(n="size", k="sum").reset_index()
    g["rate"] = g["k"] / g["n"]
    g[["lo", "hi"]] = [wilson(k, n) for k, n in zip(g["k"], g["n"])]
    order = {lbl: i for i, (_, _, lbl) in enumerate(BANDS)}
    return g.sort_values(["team_size", "history"], key=lambda s: s.map(order) if s.name == "team_size"
                         else s.map({h: i for i, h in enumerate(HISTORY)})).reset_index(drop=True)


def markdown(table, pairs, mode):
    """Team size x shows together before; each cell is the rate with its number of pairs."""
    cell = {(r.team_size, r.history): f"{r.rate:.0%} ({r.n:,}){' *' if r.n < MIN_N else ''}"
            for r in table.itertuples()}
    lines = [f"# Who works together again ({mode} credits)", "",
             f"Share of teammate pairs who share another Broadway show within {HORIZON} years. Every pair of "
             f"teammates on a musical that opened {YEARS[0]}–{YEARS[1]} ({len(pairs):,} pairs; a pair on several "
             "shows counts once per show). Number of pairs in brackets.", "",
             "| Team size | " + " | ".join(h.capitalize() for h in HISTORY) + " |",
             "|---|" + "---|" * len(HISTORY)]
    for _, _, lbl in BANDS:
        lines.append(f"| {lbl} | " + " | ".join(cell.get((lbl, h), "–") for h in HISTORY) + " |")
    lines += ["", f"\\* fewer than {MIN_N} pairs, so the rate is uncertain. 95% intervals are in "
              "`reunion_by_team_size_history.csv`.", "",
              "Roles: composers, lyricists, book writers, directors and choreographers of original productions. "
              "Source: Wikidata and Wikipedia; written by `scripts/16_partnership_table.py`.", ""]
    return "\n".join(lines)


def main():
    def extra(p):
        p.add_argument("--source", choices=["auto", "parquet", "json"], default="auto")
        p.add_argument("--mode", choices=["strict", "loose"], default="strict")
    args = parse_args(__doc__.splitlines()[0], extra)
    ps, source = load_person_show(args.source)
    log.info("Input: %s; mode %s", source, args.mode)
    pairs = pair_table(ps, args.mode)
    table = summarise(pairs)
    csv = config.OUTPUT_TABLES / "reunion_by_team_size_history.csv"
    table.assign(rate=table["rate"].round(4), lo=table["lo"].round(4), hi=table["hi"].round(4)).to_csv(csv, index=False)
    md = config.OUTPUT_TABLES / "reunion_by_team_size_history.md"
    text = markdown(table, pairs, args.mode)
    md.write_text(text)
    log.info("Wrote %s and %s\n%s", display_path(csv), display_path(md), text)


if __name__ == "__main__":
    main()
