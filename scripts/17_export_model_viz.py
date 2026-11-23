"""Step 17: export the model results (steps 11 and 15) for the web views, as viz/data/models.json.

The views explain what the models learned, so they need the models' own outputs, in strict mode
(the views' default):

  communities  step 11's members (F >= delta) per cutoff, for plain BigCLAM and the weighted
               variant (--weights newman). The cohort view colours people by community; the
               two methods can be compared there.
  pairs        step 15's candidate pairs per cutoff (shared a show in [T-10, T)) with their scores
               and the outcome (shows together again in [T, T+10)), plus the weighted BigCLAM
               score F_a . F_b from the weighted affiliations. The predict view ranks pairs by
               a score and shows which reunited.

Nothing is refitted here: run scripts/11_bigclam.py (both --weights none and newman) and
scripts/15_h3_prediction.py first. The file is optional for the site: views that need it say so
when it is missing.

Output: viz/data/models.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from src.common import display_path, log, parse_args, read_parquet
from src.network import COMMUNITIES_DIR, VIZ_DATA

MODE = "strict"
WEIGHTED_DIR = config.DATA_PROCESSED / "communities_weighted"
PAIR_SCORES = config.DATA_PROCESSED / "h3" / "pair_scores.parquet"
OUT = VIZ_DATA / "models.json"
SCORES = ["shows_together", "activity", "common_neighbors", "bigclam", "weighted"]


def community_rows(directory):
    c = read_parquet(directory / "communities.parquet")
    c = c[c["mode"] == MODE].sort_values(["cutoff", "community_id", "strength"], ascending=[True, True, False])
    return [[int(r.cutoff), int(r.community_id), r.person_id, round(float(r.strength), 3)] for r in c.itertuples()]


def weighted_scores(pairs):
    """F_a . F_b from the weighted affiliations, per cutoff (0 when either person has no F)."""
    aff = read_parquet(WEIGHTED_DIR / "affiliations.parquet")
    aff = aff[aff["mode"] == MODE]
    out = np.zeros(len(pairs))
    for T, idx in pairs.groupby("cutoff").groups.items():
        F = aff[aff["cutoff"] == T].pivot_table(index="person_id", columns="community_id", values="f", fill_value=0.0)
        rows = {p: i for i, p in enumerate(F.index)}
        M = F.to_numpy()
        zero = np.zeros(M.shape[1])
        sub = pairs.loc[idx]
        out[pairs.index.get_indexer(idx)] = [
            float(M[rows[a]] @ M[rows[b]]) if a in rows and b in rows else 0.0
            for a, b in zip(sub["person_a"], sub["person_b"])]
    return out


def auc(y, s):
    y = np.asarray(y, dtype=bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return None
    r = pd.Series(s).rank().to_numpy()
    return round(float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), 4)


def main():
    parse_args(__doc__.splitlines()[0])
    pairs = read_parquet(PAIR_SCORES)
    pairs = pairs[pairs["mode"] == MODE].reset_index(drop=True)
    pairs["weighted"] = weighted_scores(pairs)

    # AUC per window and pooled, so the views don't recompute them (and match step 15's numbers)
    auc_rows = []
    for T, d in pairs.groupby("cutoff"):
        auc_rows.append([int(T), len(d), int(d["reunited"].sum())] + [auc(d["reunited"], d[s]) for s in SCORES])
    pooled = {s: auc(pairs["reunited"], pairs[s]) for s in SCORES}
    one = pairs[pairs["shows_together"] == 1]
    pooled_one = {s: auc(one["reunited"], one[s]) for s in SCORES}

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "mode": MODE,
        "note": "Scores use only the training window [T-10, T); the outcome is a shared show in [T, T+10). "
                "AUC 0.5 = chance. Steps 11 (BigCLAM, plain and weighted), 15 (scores) and 17 (this export).",
        "scores": SCORES,
        "communities": {
            "columns": ["cutoff", "community_id", "person_id", "strength"],
            "bigclam": community_rows(COMMUNITIES_DIR),
            "weighted": community_rows(WEIGHTED_DIR),
        },
        "pairs": {
            "columns": ["cutoff", "person_a", "person_b", *SCORES, "reunion_shows"],
            "rows": [[int(r.cutoff), r.person_a, r.person_b, int(r.shows_together), int(r.activity),
                      int(r.common_neighbors), round(float(r.bigclam), 4), round(float(r.weighted), 4),
                      int(r.reunion_shows)] for r in pairs.itertuples()],
        },
        "auc": {
            "columns": ["cutoff", "pairs", "reunited", *SCORES],
            "windows": auc_rows,
            "pooled": pooled,
            "pooled_one_show": pooled_one,
        },
    }
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    log.info("Wrote %s (%.0f KB): %d pairs, %d + %d community rows", display_path(OUT), OUT.stat().st_size / 1024,
             len(pairs), len(out["communities"]["bigclam"]), len(out["communities"]["weighted"]))
    log.info("Pooled AUC (all pairs): %s", pooled)
    log.info("Pooled AUC (one-show pairs): %s", pooled_one)


if __name__ == "__main__":
    main()
