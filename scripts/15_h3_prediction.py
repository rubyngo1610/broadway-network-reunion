"""Step 15: H3 prediction test: do communities learned before a team disperses predict who reunites?

Time splits as in step 08: for each mode and cutoff T, the candidates are the pairs who shared a
show in the training window [T - W, T), and the label is whether they share a show again in
[T, T + H). Every score uses only the training window; BigCLAM comes from step 11, fitted on the
same window.

Scores per pair (a, b):
  shows_together      shows shared in the training window (the heuristic H3 has to beat)
  bigclam             F_a . F_b from step 11 (P(edge) = 1 - exp(-F_a . F_b) ranks the same)
  shared_communities  communities both belong to (F >= delta)
  common_neighbors    people both worked with in the window
  adamic_adar         common neighbours weighted by 1 / log(degree)
  activity            min(shows of a, shows of b) in the window (are both still working?)

Fixed before looking at results (WORKLOG 2026-11-12):
  primary    strict mode, AUC pooled over the 18 cutoffs, bigclam vs shows_together
  secondary  the same among pairs who shared exactly one show (about 95% of pairs), where
             shows_together cannot rank at all (AUC 0.5), so bigclam is tested against 0.5 and
             against common_neighbors
  95% intervals: bootstrap over pairs within each cutoff (1,000 draws). Pairs share people and
  windows overlap by 5 years, so the intervals are somewhat too narrow.

Outputs
  data/processed/h3/pair_scores.parquet   one row per mode x cutoff x pair: scores and label
  outputs/tables/h3_by_window.csv         AUC and average precision per score and window
  outputs/tables/h3_summary.csv           pooled results with bootstrap intervals
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from src.common import display_path, log, parse_args, read_parquet, write_parquet
from src.network import COMMUNITIES_DIR, in_mode, load_person_show, pair_counts, window_graph

OUT_DIR = config.DATA_PROCESSED / "h3"
MODES = ["strict", "loose"]
SCORES = ["shows_together", "bigclam", "shared_communities", "common_neighbors", "adamic_adar", "activity"]
N_BOOT = 1000


# --- Scores -----------------------------------------------------------------------------------

def window_pairs(ps, mode, T, aff, comm):
    """All training-window pairs of one (mode, cutoff) with their scores and reunion label."""
    W, H = config.NETWORK_WINDOW_YEARS, config.NETWORK_HORIZON_YEARS
    people, A, sub = window_graph(ps, mode, T)
    idx = {p: i for i, p in enumerate(people)}
    together = pair_counts(sub)
    m = in_mode(ps, mode)
    future = pair_counts(m[(m["year"] >= T) & (m["year"] < T + H)])

    F = (aff.pivot_table(index="person_id", columns="community_id", values="f", fill_value=0.0)
         .reindex(people, fill_value=0.0).to_numpy())
    M = (comm.assign(v=1).pivot_table(index="person_id", columns="community_id", values="v", fill_value=0)
         .reindex(people, fill_value=0).to_numpy())
    Ai = A.astype(float)
    deg = A.sum(1)
    inv_log = np.where(deg > 1, 1.0 / np.log(np.maximum(deg, 2)), 0.0)
    CN, AA, FF, MM = Ai @ Ai, (Ai * inv_log) @ Ai, F @ F.T, M @ M.T
    shows = sub.groupby("person_id")["show_id"].nunique()

    rows = []
    for (a, b), w in together.items():
        i, j = idx[a], idx[b]
        rows.append({"mode": mode, "cutoff": T, "person_a": a, "person_b": b,
                     "shows_together": w, "bigclam": FF[i, j], "shared_communities": int(MM[i, j]),
                     "common_neighbors": int(CN[i, j]), "adamic_adar": AA[i, j],
                     "activity": int(min(shows[a], shows[b])),
                     "reunion_shows": future.get((a, b), 0)})
    df = pd.DataFrame(rows)
    df["reunited"] = df["reunion_shows"] > 0
    return df


# --- Metrics ----------------------------------------------------------------------------------

def auc(y, s):
    """Area under the ROC curve (Mann-Whitney; ties count half)."""
    y = np.asarray(y, dtype=bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(s).rank().to_numpy()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def average_precision(y, s):
    """Average precision with tied scores taken as one threshold (as in scikit-learn)."""
    y = np.asarray(y, dtype=bool)
    if y.sum() == 0:
        return np.nan
    d = pd.DataFrame({"y": y, "s": s}).groupby("s", sort=True)["y"].agg(["sum", "size"]).iloc[::-1]
    tp, n = d["sum"].cumsum(), d["size"].cumsum()
    return float(((d["sum"] / y.sum()) * (tp / n)).sum())


def bootstrap(df, stat, rng):
    """Percentile 95% interval: resample pairs within each cutoff."""
    groups = [g.index.to_numpy() for _, g in df.groupby("cutoff")]
    vals = []
    for _ in range(N_BOOT):
        take = np.concatenate([rng.choice(g, len(g)) for g in groups])
        vals.append(stat(df.loc[take]))
    return np.nanpercentile(vals, [2.5, 97.5])


def summarize(pairs, mode, subset, rng):
    d = pairs[pairs["mode"] == mode]
    if subset == "one_show":
        d = d[d["shows_together"] == 1]
    d = d.reset_index(drop=True)
    row = {"mode": mode, "pairs": subset, "n_pairs": len(d), "n_reunited": int(d["reunited"].sum()),
           "base_rate": round(d["reunited"].mean(), 4)}
    for s in SCORES:
        row[f"auc_{s}"] = round(auc(d["reunited"], d[s]), 4)
        row[f"ap_{s}"] = round(average_precision(d["reunited"], d[s]), 4)
    lo, hi = bootstrap(d, lambda x: auc(x["reunited"], x["bigclam"]), rng)
    row["auc_bigclam_ci"] = f"{lo:.3f}-{hi:.3f}"
    for other in ["shows_together", "common_neighbors"]:
        diff = lambda x, o=other: auc(x["reunited"], x["bigclam"]) - auc(x["reunited"], x[o])
        lo, hi = bootstrap(d, diff, rng)
        row[f"diff_vs_{other}"] = round(row["auc_bigclam"] - row[f"auc_{other}"], 4)
        row[f"diff_vs_{other}_ci"] = f"{lo:.3f}-{hi:.3f}"
    return row


def main():
    def extra(p):
        p.add_argument("--source", choices=["auto", "parquet", "json"], default="auto")
    args = parse_args(__doc__.splitlines()[0], extra)

    ps, source = load_person_show(args.source)
    log.info("Input: %s (%d person-show rows)", source, len(ps))
    aff = read_parquet(COMMUNITIES_DIR / "affiliations.parquet")
    comm = read_parquet(COMMUNITIES_DIR / "communities.parquet")

    windows = pd.read_csv(config.OUTPUT_TABLES / "network_windows.csv")
    parts = []
    for mode in MODES:
        for T in config.NETWORK_CUTOFFS:
            a = aff[(aff["mode"] == mode) & (aff["cutoff"] == T)]
            if a.empty:
                sys.exit(f"No step 11 communities for {mode} {T}. Run scripts/11_bigclam.py on all windows.")
            df = window_pairs(ps, mode, T, a, comm[(comm["mode"] == mode) & (comm["cutoff"] == T)])
            ref = windows[(windows["mode"] == mode) & (windows["cutoff"] == T)].iloc[0]
            if (len(df), int(df["reunited"].sum())) != (ref["n_edges"], ref["n_reunited"]):
                log.warning("%s %d: %d pairs / %d reunited, but step 08 has %d / %d", mode, T, len(df),
                            df["reunited"].sum(), ref["n_edges"], ref["n_reunited"])
            parts.append(df)
    pairs = pd.concat(parts, ignore_index=True)
    write_parquet(pairs, OUT_DIR / "pair_scores.parquet")

    by_window = []
    for (mode, T), d in pairs.groupby(["mode", "cutoff"]):
        row = {"mode": mode, "cutoff": T, "n_pairs": len(d), "n_reunited": int(d["reunited"].sum())}
        for s in SCORES:
            row[f"auc_{s}"] = round(auc(d["reunited"], d[s]), 3)
        one = d[d["shows_together"] == 1]
        row["auc_bigclam_one_show"] = round(auc(one["reunited"], one["bigclam"]), 3)
        by_window.append(row)
    by_window = pd.DataFrame(by_window)
    by_window.to_csv(config.OUTPUT_TABLES / "h3_by_window.csv", index=False)

    rng = np.random.default_rng(config.RANDOM_SEED)
    summary = pd.DataFrame([summarize(pairs, mode, subset, rng) for mode in MODES for subset in ["all", "one_show"]])
    summary.to_csv(config.OUTPUT_TABLES / "h3_summary.csv", index=False)
    log.info("Wrote %s and %s", display_path(config.OUTPUT_TABLES / "h3_by_window.csv"),
             display_path(config.OUTPUT_TABLES / "h3_summary.csv"))

    for mode in MODES:
        w = by_window[by_window["mode"] == mode]
        log.info("%s: bigclam beats shows_together in %d of %d windows; mean AUC %.3f vs %.3f",
                 mode, int((w["auc_bigclam"] > w["auc_shows_together"]).sum()), len(w),
                 w["auc_bigclam"].mean(), w["auc_shows_together"].mean())
    cols = ["mode", "pairs", "n_pairs", "n_reunited"] + [f"auc_{s}" for s in SCORES] + [
        "auc_bigclam_ci", "diff_vs_shows_together", "diff_vs_shows_together_ci",
        "diff_vs_common_neighbors", "diff_vs_common_neighbors_ci"]
    log.info("Summary (AUC):\n%s", summary[cols].to_string(index=False))


if __name__ == "__main__":
    main()
