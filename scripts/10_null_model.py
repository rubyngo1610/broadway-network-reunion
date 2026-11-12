"""Step 10: H1 null model: do creative teams reunite more often than chance?

Observed: for each mode and cutoff T, the pairs who shared a show in the training window
[T - W, T), and how many share a show again in the reunion window [T, T + H) (as in step 08).

Null (Nov 3 update, feedback 5): within each window and each role, reassign people at random
across the role slots of shows. A slot is one person-show credit, and its role is the person's
full role set on that show (e.g. "composer|lyricist"), so people only swap with others who held
the same roles. The training and reunion windows are shuffled independently, for each cutoff.
This keeps each person's number of credits per window and their roles, every show's team size
and date, and breaks who works with whom. A shuffle that puts one person twice on a show is
repaired by swapping with another slot of the same role.

Pair types, from the roles the two people held on a shared training show (first match wins):
  composer_lyricist   one was composer, the other lyricist
  writer_writer       both writers (composer, lyricist, book writer)
  writer_staging      a writer and a director or choreographer
  staging_staging     both director or choreographer

Fixed before looking at results (WORKLOG 2026-11-12):
  primary    strict mode, reunion rate pooled over the 18 cutoffs vs 1,000 shuffles;
             one-sided p = (1 + shuffles with a rate >= observed) / 1,001
  secondary  the same per pair type (H1: strongest for composer-lyricist pairs), loose mode,
             and each cutoff on its own

Outputs
  data/processed/h1/null_draws.parquet     mode, cutoff, draw, pair_type, n_pairs, n_reunited
  data/processed/h1/show_reunions.parquet  per training-window show: reunited pairs vs the null
                                           (for highlighting reunions above chance in the views)
  outputs/tables/h1_by_window.csv          observed vs null per mode, cutoff and pair type
  outputs/tables/h1_summary.csv            pooled over cutoffs per mode and pair type
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from src.common import display_path, log, parse_args, write_parquet
from src.network import in_mode, load_person_show

OUT_DIR = config.DATA_PROCESSED / "h1"
MODES = ["strict", "loose"]
WRITERS = {"composer", "lyricist", "book_writer"}
STAGING = {"director", "choreographer"}
PAIR_TYPES = ["staging_staging", "writer_staging", "writer_writer", "composer_lyricist"]  # priority, low to high


class Window:
    """The credits (slots) of one window, with everything that stays fixed under shuffling."""

    def __init__(self, rows, person_index):
        rows = rows.reset_index(drop=True)
        self.person = rows["person_id"].map(person_index).to_numpy()
        self.show_ids = np.array(sorted(rows["show_id"].unique()))
        self.show = np.searchsorted(self.show_ids, rows["show_id"].to_numpy())
        roles = rows["roles"].str.split("|").map(set)
        # slots of the same role set swap with each other
        self.strata = [g.to_numpy() for _, g in rows.groupby("roles").groups.items()]
        self.stratum_of = np.empty(len(rows), dtype=int)
        for k, g in enumerate(self.strata):
            self.stratum_of[g] = k
        # slot pairs on the same show: fixed, only the people in them change
        ri, rj = [], []
        for s in range(len(self.show_ids)):
            members = np.flatnonzero(self.show == s)
            a, b = np.triu_indices(len(members), 1)
            ri.append(members[a])
            rj.append(members[b])
        self.ri, self.rj = np.concatenate(ri), np.concatenate(rj)
        self.pair_show = self.show[self.ri]
        comp = roles.map(lambda r: "composer" in r).to_numpy()
        lyr = roles.map(lambda r: "lyricist" in r).to_numpy()
        wr = roles.map(lambda r: bool(r & WRITERS)).to_numpy()
        st = roles.map(lambda r: bool(r & STAGING)).to_numpy()
        i, j = self.ri, self.rj
        cl = (comp[i] & lyr[j]) | (lyr[i] & comp[j])
        ww = wr[i] & wr[j]
        ws = (wr[i] & st[j]) | (st[i] & wr[j])
        self.pair_rank = np.select([cl, ww, ws], [3, 2, 1], default=0)

    def shuffle(self, rng):
        p = self.person.copy()
        for g in self.strata:
            p[g] = p[rng.permutation(g)]
        return self.repair(p, rng)

    def repair(self, p, rng):
        """Swap away any person placed twice on the same show (team sizes must not shrink).

        A duplicate slot swaps with a random slot of the same role whose person is not on the
        duplicate's show, and whose show does not already have the duplicate's person."""
        on_show = {}
        for r in range(len(p)):
            on_show.setdefault((self.show[r], p[r]), []).append(r)
        for s, person in list(on_show):
            while len(on_show.get((s, person), [])) > 1:   # earlier swaps may have removed the key
                # move any of the duplicate slots that has a valid partner (a slot whose role set
                # is unique cannot move, but the other copy usually can)
                for r in rng.permutation(on_show[(s, person)]):
                    ok = [o for o in self.strata[self.stratum_of[r]]
                          if self.show[o] != s and (s, p[o]) not in on_show
                          and (self.show[o], person) not in on_show]
                    if ok:
                        break
                else:
                    raise RuntimeError(f"cannot repair a shuffle: no valid swap on show {s}")
                o = rng.choice(ok)
                q = p[o]
                on_show[(s, person)].remove(r)
                on_show[(self.show[o], q)].remove(o)
                if not on_show[(self.show[o], q)]:
                    del on_show[(self.show[o], q)]
                p[r], p[o] = q, person
                on_show[(s, q)] = [r]
                on_show[(self.show[o], person)] = [o]
        return p

    def pair_codes(self, p, n_people):
        a, b = p[self.ri], p[self.rj]
        return np.minimum(a, b) * n_people + np.maximum(a, b)


def evaluate(train, future, tp, fp, n_people):
    """Per pair type: (training pairs, reunited pairs); and per training show: reunited slot pairs."""
    codes = train.pair_codes(tp, n_people)
    future_codes = np.unique(future.pair_codes(fp, n_people))
    order = np.argsort(codes, kind="stable")
    uniq, start = np.unique(codes[order], return_index=True)
    rank = np.maximum.reduceat(train.pair_rank[order], start)
    reunited = np.isin(uniq, future_codes)
    by_type = {t: (int((rank == k).sum()), int((reunited & (rank == k)).sum())) for k, t in enumerate(PAIR_TYPES)}
    by_type["all"] = (len(uniq), int(reunited.sum()))
    per_show = np.bincount(train.pair_show, weights=np.isin(codes, future_codes),
                           minlength=len(train.show_ids))
    return by_type, per_show


def p_value(null, observed):
    null = np.asarray(null)
    return (1 + np.sum(null >= observed)) / (len(null) + 1)


def main():
    def extra(p):
        p.add_argument("--source", choices=["auto", "parquet", "json"], default="auto")
        p.add_argument("--draws", type=int, default=1000, help="Shuffles per mode and cutoff.")
    args = parse_args(__doc__.splitlines()[0], extra)

    ps, source = load_person_show(args.source)
    log.info("Input: %s (%d person-show rows); %d shuffles per window", source, len(ps), args.draws)
    W, H = config.NETWORK_WINDOW_YEARS, config.NETWORK_HORIZON_YEARS
    reference = pd.read_csv(config.OUTPUT_TABLES / "network_windows.csv")

    draws, obs_rows, show_rows = [], [], []
    for mode in MODES:
        m = in_mode(ps, mode)
        for T in config.NETWORK_CUTOFFS:
            tr = m[(m["year"] >= T - W) & (m["year"] < T)]
            fu = m[(m["year"] >= T) & (m["year"] < T + H)]
            people = sorted(set(tr["person_id"]) | set(fu["person_id"]))
            index = {p: i for i, p in enumerate(people)}
            train, future = Window(tr, index), Window(fu, index)
            n = len(people)

            obs, obs_show = evaluate(train, future, train.person, future.person, n)
            ref = reference[(reference["mode"] == mode) & (reference["cutoff"] == T)].iloc[0]
            if obs["all"] != (ref["n_edges"], ref["n_reunited"]):
                log.warning("%s %d: observed %s, but step 08 has %d / %d", mode, T, obs["all"],
                            ref["n_edges"], ref["n_reunited"])
            for t, (n_pairs, n_re) in obs.items():
                obs_rows.append({"mode": mode, "cutoff": T, "pair_type": t, "n_pairs": n_pairs, "n_reunited": n_re})

            rng = np.random.default_rng([config.RANDOM_SEED, T, MODES.index(mode)])
            null_show = np.empty((args.draws, len(train.show_ids)))
            for d in range(args.draws):
                res, null_show[d] = evaluate(train, future, train.shuffle(rng), future.shuffle(rng), n)
                for t, (n_pairs, n_re) in res.items():
                    draws.append((mode, T, d, t, n_pairs, n_re))

            team = np.bincount(train.show, minlength=len(train.show_ids))
            for s, sid in enumerate(train.show_ids):
                show_rows.append({"mode": mode, "cutoff": T, "show_id": sid, "team_size": int(team[s]),
                                  "slot_pairs": int(team[s] * (team[s] - 1) // 2),
                                  "reunited_pairs": int(obs_show[s]),
                                  "null_mean": round(float(null_show[:, s].mean()), 3),
                                  "p_value": round(p_value(null_show[:, s], obs_show[s]), 4)})
            log.info("%s %d: %d pairs, %d reunited (%.1f%%); null mean %.1f%%", mode, T, obs["all"][0],
                     obs["all"][1], 100 * obs["all"][1] / obs["all"][0],
                     100 * np.mean([r[5] / r[4] for r in draws[-len(res) * args.draws:] if r[3] == "all"]))

    draws = pd.DataFrame(draws, columns=["mode", "cutoff", "draw", "pair_type", "n_pairs", "n_reunited"])
    observed = pd.DataFrame(obs_rows)
    write_parquet(draws, OUT_DIR / "null_draws.parquet")
    write_parquet(pd.DataFrame(show_rows), OUT_DIR / "show_reunions.parquet")

    def compare(obs_g, null_g, keys):
        rate = obs_g["n_reunited"].sum() / obs_g["n_pairs"].sum() if obs_g["n_pairs"].sum() else np.nan
        totals = null_g.groupby("draw")[["n_pairs", "n_reunited"]].sum()
        null_rate = (totals["n_reunited"] / totals["n_pairs"].where(totals["n_pairs"] > 0)).to_numpy()
        lo, hi = np.nanpercentile(null_rate, [2.5, 97.5])
        mean = np.nanmean(null_rate)
        return {**keys, "n_pairs": int(obs_g["n_pairs"].sum()), "n_reunited": int(obs_g["n_reunited"].sum()),
                "observed_rate": round(rate, 4), "null_mean": round(mean, 4),
                "null_95": f"{lo:.4f}-{hi:.4f}", "ratio": round(rate / mean, 2) if mean else np.nan,
                "p_value": round(p_value(null_rate[~np.isnan(null_rate)], rate), 4)}

    by_window, summary = [], []
    for (mode, t), og in observed.groupby(["mode", "pair_type"]):
        ng = draws[(draws["mode"] == mode) & (draws["pair_type"] == t)]
        summary.append(compare(og, ng, {"mode": mode, "pair_type": t}))
        for T, ogt in og.groupby("cutoff"):
            by_window.append(compare(ogt, ng[ng["cutoff"] == T], {"mode": mode, "cutoff": T, "pair_type": t}))
    order = {t: i for i, t in enumerate(["all"] + PAIR_TYPES[::-1])}
    summary = pd.DataFrame(summary).sort_values(["mode", "pair_type"], key=lambda s: s.map(order) if s.name == "pair_type" else s.map({"strict": 0, "loose": 1}))
    by_window = pd.DataFrame(by_window).sort_values(["mode", "pair_type", "cutoff"])
    summary.to_csv(config.OUTPUT_TABLES / "h1_summary.csv", index=False)
    by_window.to_csv(config.OUTPUT_TABLES / "h1_by_window.csv", index=False)
    log.info("Wrote %s and %s", display_path(config.OUTPUT_TABLES / "h1_summary.csv"),
             display_path(config.OUTPUT_TABLES / "h1_by_window.csv"))
    log.info("Summary:\n%s", summary.to_string(index=False))
    allw = by_window[by_window["pair_type"] == "all"]
    for mode in MODES:
        w = allw[allw["mode"] == mode]
        log.info("%s: observed above the null 95%% interval in %d of %d cutoffs (p < 0.05 in %d)", mode,
                 int((w["observed_rate"] > w["null_95"].str.split("-").str[1].astype(float)).sum()), len(w),
                 int((w["p_value"] < 0.05).sum()))


if __name__ == "__main__":
    main()
