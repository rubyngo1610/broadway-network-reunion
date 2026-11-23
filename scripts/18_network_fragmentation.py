"""Step 18: does Broadway's collaboration network break into islands over time, and who held it together?

For every 10-year window [T-10, T) (the network windows of steps 08-15), people are linked when
they shared a show (strict credits by default). Per window:

  giant_share        share of the window's people in the largest connected piece ("one big bunch")
  components         number of separate pieces; second_largest is the size of the runner-up
  avg_team           average team size (people per show)
  people_per_show    distinct people / shows: how many new faces each show brings
  repeat_pair_share  share of linked pairs who did 2+ shows together inside the window
  share_3plus        share of people with 3+ shows in the window (the prolific core)
  glue_1..3          the three people whose removal shrinks the giant piece the most, with the
                     drop in giant_share (percentage points) and their shows in the window

Junk "people" (placeholders and title fragments, see viz/js/data.js) are left out.

Outputs
  outputs/tables/network_fragmentation.csv   one row per window
  outputs/tables/network_fragmentation.md    the readable table
"""
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import display_path, log, parse_args
from src.network import in_mode, load_names, load_person_show

W = config.NETWORK_WINDOW_YEARS
CUTOFFS = range(1920, 2030, 5)          # windows 1910-1919 ... 2015-2024
# not people; the same list as JUNK_IDS / NOT_A_PERSON in viz/js/data.js
JUNK = {"Q918727", "name:filipino", "name:if", "name:earth", "name:wind", "name:panama", "name:he",
        "name:act", "name:warriors", "name:the ham tree", "name:gentlemen prefer blondes"}


def components(nodes, adj, removed=None):
    """Sizes of the connected pieces, largest first (BFS; `removed` is left out)."""
    seen = {removed} if removed else set()
    sizes = []
    for v in nodes:
        if v in seen:
            continue
        seen.add(v)
        stack, n = [v], 0
        while stack:
            u = stack.pop()
            n += 1
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        sizes.append(n)
    return sorted(sizes, reverse=True)


def window_row(sub, names, T):
    teams = sub.groupby("show_id")["person_id"].apply(lambda s: sorted(set(s)))
    adj, pairs = defaultdict(set), Counter()
    for team in teams:
        for p in team:
            adj[p]
        for a, b in combinations(team, 2):
            adj[a].add(b)
            adj[b].add(a)
            pairs[(a, b)] += 1
    people = sorted(adj)
    n = len(people)
    sizes = components(people, adj)
    shows_per = sub.groupby("person_id")["show_id"].nunique()
    # glue: removing a person from the giant piece; how much smaller does it get (share of the others)?
    giant = set()
    for v in people:   # find the members of the largest piece
        stack, comp, seen = [v], {v}, {v}
        while stack:
            u = stack.pop()
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    comp.add(w)
                    stack.append(w)
        if len(comp) == sizes[0]:
            giant = comp
            break
    glue = []
    for p in giant:
        after = components(giant, adj, removed=p)
        glue.append((sizes[0] / n - (after[0] if after else 0) / (n - 1), p))
    glue.sort(reverse=True)
    row = {
        "window": f"{T - W}-{T - 1}", "cutoff": T, "people": n, "shows": len(teams),
        "giant_share": round(sizes[0] / n, 3), "components": len(sizes),
        "second_largest": sizes[1] if len(sizes) > 1 else 0,
        "avg_team": round(teams.map(len).mean(), 2), "people_per_show": round(n / len(teams), 2),
        "repeat_pair_share": round(sum(v >= 2 for v in pairs.values()) / max(1, len(pairs)), 3),
        "share_3plus": round(float((shows_per >= 3).mean()), 3),
    }
    for i, (drop, p) in enumerate(glue[:3], 1):
        row[f"glue_{i}"] = names.get(p, p)
        row[f"glue_{i}_drop_pp"] = round(100 * drop, 1)
        row[f"glue_{i}_shows"] = int(shows_per[p])
    return row


def main():
    def extra(p):
        p.add_argument("--mode", default="strict", choices=["strict", "loose"])
        p.add_argument("--source", default="auto", choices=["auto", "parquet", "json"],
                       help="step 08's person_show.parquet or viz/data/credits.json (auto: parquet if present)")
    args = parse_args(__doc__.splitlines()[0], extra)
    ps, src = load_person_show(args.source)
    names = load_names()
    ps = in_mode(ps, args.mode)
    ps = ps[~ps["person_id"].isin(JUNK) & ~ps["person_id"].map(lambda p: names.get(p, "")).str.lower().str.startswith("various")]
    log.info("Person-show rows (%s, %s): %d", args.mode, src, len(ps))

    rows = [window_row(ps[(ps["year"] >= T - W) & (ps["year"] < T)], names, T) for T in CUTOFFS]
    out = pd.DataFrame(rows)
    csv = config.OUTPUT_TABLES / "network_fragmentation.csv"
    out.to_csv(csv, index=False)

    md = ["# Does the network break into islands? (strict credits)", "",
          "Per 10-year window: people linked by a shared show. **Big bunch** = share of the window's people in "
          "the largest connected piece. **Glue** = the people whose removal shrinks that piece the most "
          "(drop in percentage points; shows in the window).", "",
          "| Window | People | Big bunch | Pieces | Repeat pairs | 3+ shows | Top glue |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        glue = "; ".join(f"{r[f'glue_{i}']} (−{r[f'glue_{i}_drop_pp']} pp, {r[f'glue_{i}_shows']})" for i in (1, 2, 3) if f"glue_{i}" in r)
        md.append(f"| {r['window']} | {r['people']} | {100 * r['giant_share']:.0f}% | {r['components']} | "
                  f"{100 * r['repeat_pair_share']:.1f}% | {100 * r['share_3plus']:.0f}% | {glue} |")
    md += ["", f"Source: `{src}`; written by `scripts/18_network_fragmentation.py`."]
    (config.OUTPUT_TABLES / "network_fragmentation.md").write_text("\n".join(md) + "\n")
    log.info("Wrote %s and .md", display_path(csv))


if __name__ == "__main__":
    main()
