"""Step 11: BigCLAM overlapping communities per time window (for H1/H3 and the cohort view).

For every mode (strict, loose) and cutoff T, the graph links people who shared a show in the
training window [T - W, T): the same edges as step 08's edges_by_window.parquet. Each model fits
a non-negative affiliation matrix F (people x K):

  --weights none (default)  BigCLAM (Yang & Leskovec 2013): P(u, v linked) = 1 - exp(-F_u . F_v).
                            Edges are binary; how often or in how big a team a pair met is not used.
  --weights newman          Weighted BigCLAM, the Poisson form (Ball, Karrer & Newman 2011): the
                            link weight w_uv has mean F_u . F_v. w_uv is Newman's collaboration
                            weight, the sum over shared shows of 1 / (team size - 1), so a duo's
                            show counts 1 and a 20-person revue 1/19; repeat partners add up.
                            Exploratory (after H3; WORKLOG 2026-11-13).

K is chosen per window by BIC: for each K on a grid, keep the best of 5 seeded fits and score
-2 LL + p log(number of pairs), with p = non-zero entries of F. The rule was fixed before any
H3 result. --k-method heldout chooses K by held-out likelihood instead; on these graphs it runs
to about one community per show, so it is kept only for comparison. Seeds are locally minimal
neighbourhoods (lowest-conductance ego networks), as in the paper.

A person belongs to community c when F_uc >= delta, the level at which two members' expected
link reaches the background: delta = sqrt(-log(1 - eps)) with eps the edge density (BigCLAM),
or delta = sqrt(mean link weight over all pairs) (weighted).

Input (--source):
  parquet  data/processed/network/person_show.parquet (step 08)
  json     viz/data/credits.json (step 13: the same rows and strict/loose flags)
  auto     parquet if it exists, else json (default)

Outputs (data/processed/communities/, or communities_weighted/ with --weights newman)
  communities.parquet      mode, cutoff, community_id, person_id, strength (members only: F >= delta)
  affiliations.parquet     mode, cutoff, person_id, community_id, f (all of F above 1e-6; H3 scores F_u . F_v)
  outputs/tables/bigclam[_weighted]_windows.csv       per window: K, sizes, coverage, overlap, show check
  outputs/tables/bigclam[_weighted]_k_selection.csv   BIC (or held-out log-likelihood) per window and K
  outputs/tables/bigclam[_weighted]_case_studies.csv  communities of the case-study people, with names
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from src.common import display_path, log, parse_args, write_parquet
from src.network import COMMUNITIES_DIR, load_names, load_person_show, window_graph

MODES = ["strict", "loose"]
K_GRID = [2, 3, 4, 6, 8, 10, 13, 16, 20, 25, 30, 40, 50, 65, 80, 100, 130]
HOLDOUT_FRAC = 0.2
BIC_NONZERO = 1e-3     # an F entry above this counts as a parameter in BIC
MIN_X = 1e-10          # floor on F_u . F_v so the logs stay finite
CASE_STUDIES = {       # user-study cases (Rodgers; Lerner & Loewe) and the practice case (Comden, Green & Styne)
    "Q269094": "Richard Rodgers", "Q725828": "Lorenz Hart", "Q319693": "Oscar Hammerstein II",
    "Q961893": "Alan Jay Lerner", "Q551678": "Frederick Loewe",
    "Q175078": "Betty Comden", "Q329849": "Adolph Green", "Q587741": "Jule Styne",
}


# --- Models -----------------------------------------------------------------------------------
# Both log-likelihoods sum over the pairs in `mask`, which is symmetric, so each pair counts twice.

class Bernoulli:
    """BigCLAM: binary edges, P(edge) = 1 - exp(-F_u . F_v)."""

    def __init__(self, A):
        self.A = A

    def loglik(self, F, mask):
        X = np.maximum(F @ F.T, MIN_X)
        return np.log(-np.expm1(-X[self.A & mask])).sum() - X[mask & ~self.A].sum()

    def gradient(self, F, mask):
        X = np.maximum(F @ F.T, MIN_X)
        return 2.0 * (np.where(self.A, 1.0 / np.expm1(X), -1.0) * mask) @ F

    def delta(self):
        n = len(self.A)
        return float(np.sqrt(-np.log(1 - self.A.sum() / (n * (n - 1)))))


class Poisson:
    """Weighted BigCLAM: link weight w_uv with mean F_u . F_v (constant -log(w!) terms dropped)."""

    def __init__(self, Wt):
        self.W = Wt

    def loglik(self, F, mask):
        X = np.maximum(F @ F.T, MIN_X)
        return (self.W * np.log(X) - X)[mask].sum()

    def gradient(self, F, mask):
        X = np.maximum(F @ F.T, MIN_X)
        return 2.0 * (np.where(mask, self.W / X - 1.0, 0.0)) @ F

    def delta(self):
        n = len(self.W)
        return float(np.sqrt(self.W.sum() / (n * (n - 1))))


def newman_weights(people, window_ps):
    """w_uv = sum over shows both worked on of 1 / (team size - 1)."""
    idx = {p: i for i, p in enumerate(people)}
    Wt = np.zeros((len(people), len(people)))
    for _, g in window_ps.groupby("show_id"):
        members = [idx[p] for p in g["person_id"].unique()]
        if len(members) > 1:
            Wt[np.ix_(members, members)] += 1.0 / (len(members) - 1)
    np.fill_diagonal(Wt, 0.0)
    return Wt


# --- Fitting ----------------------------------------------------------------------------------

def fit(model, mask, F0, max_iter, tol=1e-6):
    """Projected gradient ascent (F >= 0) with a backtracking step size."""
    F, ll, step = F0.copy(), model.loglik(F0, mask), 1e-3
    for _ in range(max_iter):
        G = model.gradient(F, mask)
        while True:
            F_new = np.maximum(F + step * G, 0.0)
            ll_new = model.loglik(F_new, mask)
            if ll_new > ll or step < 1e-12:
                break
            step *= 0.5
        if ll_new <= ll:
            break
        gain = ll_new - ll
        F, ll, step = F_new, ll_new, step * 1.5
        if gain < tol * abs(ll):
            break
    return F


def seed_matrix(A, K, rng):
    """Initial F: one column per locally minimal ego network (lowest conductance first)."""
    n = len(A)
    deg = A.sum(1)
    vol_all = deg.sum()
    phi, egos = np.ones(n), []
    for u in range(n):
        S = A[u].copy()
        S[u] = True
        vol = deg[S].sum()
        cut = vol - A[np.ix_(S, S)].sum()
        denom = min(vol, vol_all - vol)
        if denom > 0:
            phi[u] = cut / denom
        egos.append(S)
    local_min = [u for u in range(n) if all(phi[u] <= phi[v] for v in np.flatnonzero(A[u]))]
    order = sorted(local_min, key=lambda u: (phi[u], -deg[u])) + list(rng.permutation(n))
    F = 0.01 * rng.random((n, K))
    seen, c = set(), 0
    for u in order:
        key = egos[u].tobytes()
        if key in seen:
            continue
        seen.add(key)
        F[egos[u], c] = 1.0
        c += 1
        if c == K:
            break
    return F


def holdout_masks(A, folds, rng):
    """Per fold: (training mask, held-out mask), hiding HOLDOUT_FRAC of edges and as many non-edges."""
    n = len(A)
    iu, ju = np.triu_indices(n, 1)
    is_edge = A[iu, ju]
    edges, non_edges = np.flatnonzero(is_edge), np.flatnonzero(~is_edge)
    k = max(1, round(HOLDOUT_FRAC * len(edges)))
    off_diag = ~np.eye(n, dtype=bool)
    out = []
    for _ in range(folds):
        pick = np.r_[rng.choice(edges, k, replace=False),
                     rng.choice(non_edges, min(k, len(non_edges)), replace=False)]
        hold = np.zeros((n, n), dtype=bool)
        hold[iu[pick], ju[pick]] = hold[ju[pick], iu[pick]] = True
        out.append((off_diag & ~hold, hold))
    return out


def fit_best_of(model, A, mask, k, restarts, max_iter):
    """Best of several seeded fits: the likelihood surface has many local optima."""
    best, best_ll = None, -np.inf
    for r in range(restarts):
        F = fit(model, mask, seed_matrix(A, k, np.random.default_rng([config.RANDOM_SEED, k, r])), max_iter)
        ll = model.loglik(F, mask)
        if ll > best_ll:
            best, best_ll = F, ll
    return best, best_ll


def choose_k_heldout(model, A, folds, restarts, max_iter, rng):
    """K with the best mean held-out log-likelihood. On co-credit graphs this runs to about one
    community per show (see WORKLOG 2026-11-12), so it is not the default."""
    ks = [k for k in K_GRID if k <= max(2, len(A) // 2)]
    splits = holdout_masks(A, folds, rng)
    rows = []
    for k in ks:
        for f, (train, hold) in enumerate(splits):
            F, _ = fit_best_of(model, A, train, k, restarts, max_iter)
            rows.append({"k": k, "fold": f, "heldout_ll": model.loglik(F, hold) / hold.sum()})
    scores = pd.DataFrame(rows)
    best = int(scores.groupby("k")["heldout_ll"].mean().idxmax())
    F, _ = fit_best_of(model, A, ~np.eye(len(A), dtype=bool), best, restarts, max_iter)
    return best, F, scores, ks


def choose_k_bic(model, A, restarts, max_iter):
    """K with the lowest BIC = -2 LL + p log(N), fitted on all pairs. N = number of node pairs;
    p = number of non-zero entries of F (entries at the F >= 0 boundary are not free parameters).
    Counting all n x K entries instead picks K = 2 in every window tested."""
    n = len(A)
    ks = [k for k in K_GRID if k <= max(2, n // 2)]
    mask = ~np.eye(n, dtype=bool)
    log_pairs = np.log(n * (n - 1) / 2)
    rows, fits = [], {}
    for k in ks:
        F, ll2 = fit_best_of(model, A, mask, k, restarts, max_iter)
        ll, p = ll2 / 2, int((F > BIC_NONZERO).sum())   # loglik counts each pair twice
        fits[k] = F
        rows.append({"k": k, "loglik": round(ll, 2), "n_params": p, "bic": round(-2 * ll + p * log_pairs, 2)})
    scores = pd.DataFrame(rows)
    best = int(scores.loc[scores["bic"].idxmin(), "k"])
    return best, fits[best], scores, ks


# --- Communities and checks -------------------------------------------------------------------

def communities_from_F(F, delta):
    """Threshold F at delta; merge columns with identical members (F summed); order by size
    (largest = 0); drop empty ones. At large K BigCLAM often puts several columns on one clique,
    because each copy pushes that clique's edge probability closer to 1."""
    groups = {}
    for c in range(F.shape[1]):
        groups.setdefault((F[:, c] >= delta).tobytes(), []).append(c)
    member = np.column_stack([np.frombuffer(key, dtype=bool) for key in groups])
    F = np.column_stack([F[:, cols].sum(1) for cols in groups.values()])
    order = np.argsort(-member.sum(0), kind="stable")
    F, member = F[:, order], member[:, order]
    keep = member.sum(0) > 0
    return F[:, keep], member[:, keep]


def show_check(members, window_ps):
    """How far a community reaches beyond a single show's team."""
    team = window_ps.groupby("show_id")["person_id"].apply(set)
    counts = window_ps[window_ps["person_id"].isin(members)].groupby("show_id")["person_id"].nunique()
    best_jaccard = max(len(members & t) / len(members | t) for t in team)
    return {"shows_spanned": int((counts >= 2).sum()),
            "within_one_show": bool(counts.max() == len(members)),
            "best_show_jaccard": round(best_jaccard, 3)}


def main():
    def extra(p):
        p.add_argument("--source", choices=["auto", "parquet", "json"], default="auto")
        p.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
        p.add_argument("--cutoffs", nargs="+", type=int, default=config.NETWORK_CUTOFFS,
                       help="Cutoff years T (default: all from config.NETWORK_CUTOFFS).")
        p.add_argument("--weights", choices=["none", "newman"], default="none",
                       help="none: BigCLAM on binary edges; newman: weighted (Poisson) BigCLAM.")
        p.add_argument("--k-method", choices=["bic", "heldout"], default="bic",
                       help="How K is chosen per window (fixed before H3; see WORKLOG 2026-11-12).")
        p.add_argument("--restarts", type=int, default=5, help="Seeded fits per K; the best is kept.")
        p.add_argument("--folds", type=int, default=3, help="Held-out folds (--k-method heldout only).")
        p.add_argument("--max-iter", type=int, default=500)
    args = parse_args(__doc__.splitlines()[0], extra)

    weighted = args.weights == "newman"
    out_dir = COMMUNITIES_DIR.with_name("communities_weighted") if weighted else COMMUNITIES_DIR
    prefix = "bigclam_weighted" if weighted else "bigclam"

    ps, source = load_person_show(args.source)
    if args.limit:
        keep = sorted(ps["show_id"].unique())[:args.limit]
        ps = ps[ps["show_id"].isin(keep)]
    names = load_names()
    log.info("Input: %s (%d person-show rows); model: %s", source, len(ps),
             "weighted BigCLAM (Newman weights)" if weighted else "BigCLAM")
    partial = args.modes != MODES or args.cutoffs != config.NETWORK_CUTOFFS or args.limit
    if partial:
        log.warning("Partial run: outputs hold only the windows asked for")

    comm_rows, aff_rows, window_rows, k_rows, case_rows = [], [], [], [], []
    for mode in args.modes:
        for T in args.cutoffs:
            people, A, window_ps = window_graph(ps, mode, T)
            n, n_edges = len(people), int(A.sum() // 2)
            if n < 4:
                log.warning("%s %d: only %d people, skipped", mode, T, n)
                continue
            model = Poisson(newman_weights(people, window_ps)) if weighted else Bernoulli(A)
            if args.k_method == "bic":
                k, F, scores, ks = choose_k_bic(model, A, args.restarts, args.max_iter)
            else:
                rng = np.random.default_rng([config.RANDOM_SEED, T, MODES.index(mode)])
                k, F, scores, ks = choose_k_heldout(model, A, args.folds, args.restarts, args.max_iter, rng)
            if k == ks[-1]:
                log.warning("%s %d: best K is the largest tried (%d); consider a larger grid", mode, T, k)
            delta = model.delta()
            F, member = communities_from_F(F, delta)
            k_rows += scores.assign(mode=mode, cutoff=T).to_dict("records")

            checks = []
            for c in range(F.shape[1]):
                idx = np.flatnonzero(member[:, c])
                ids = {people[i] for i in idx}
                checks.append(show_check(ids, window_ps))
                comm_rows += [{"mode": mode, "cutoff": T, "community_id": c, "person_id": people[i],
                               "strength": float(F[i, c])} for i in idx]
            nz = np.argwhere(F > 1e-6)
            aff_rows += [{"mode": mode, "cutoff": T, "person_id": people[i], "community_id": int(c),
                          "f": float(F[i, c])} for i, c in nz]

            sizes = member.sum(0)
            n_memberships = member.sum(1)
            chk = pd.DataFrame(checks)
            window_rows.append({
                "mode": mode, "cutoff": T, "n_people": n, "n_edges": n_edges,
                "n_shows": window_ps["show_id"].nunique(), "k_chosen": k, "n_communities": F.shape[1],
                "delta": round(delta, 4), "pct_people_in_any": round((n_memberships > 0).mean(), 3),
                "pct_people_in_2plus": round((n_memberships > 1).mean(), 3),
                "median_size": float(np.median(sizes)), "max_size": int(sizes.max()),
                "pct_within_one_show": round(chk["within_one_show"].mean(), 3),
                "median_shows_spanned": float(chk["shows_spanned"].median()),
                "median_best_show_jaccard": float(chk["best_show_jaccard"].median()),
            })

            for pid, pname in CASE_STUDIES.items():
                if pid not in people:
                    continue
                i = people.index(pid)
                for c in np.flatnonzero(member[i]):
                    idx = np.flatnonzero(member[:, c])
                    idx = idx[np.argsort(-F[idx, c])]
                    case_rows.append({"mode": mode, "cutoff": T, "person": pname, "community_id": int(c),
                                      "strength": round(float(F[i, c]), 3), "size": len(idx),
                                      **checks[c],
                                      "members": " | ".join(names.get(people[j], people[j]) for j in idx)})
            log.info("%s %d: %d people, %d edges, %d shows -> K=%d, %d communities (%.0f%% within one show)",
                     mode, T, n, n_edges, window_rows[-1]["n_shows"], k, F.shape[1],
                     100 * window_rows[-1]["pct_within_one_show"])

    write_parquet(pd.DataFrame(comm_rows), out_dir / "communities.parquet")
    write_parquet(pd.DataFrame(aff_rows), out_dir / "affiliations.parquet")
    windows = pd.DataFrame(window_rows)
    for name, df in [("windows", windows), ("k_selection", pd.DataFrame(k_rows)),
                     ("case_studies", pd.DataFrame(case_rows))]:
        path = config.OUTPUT_TABLES / f"{prefix}_{name}.csv"
        df.to_csv(path, index=False)
        log.info("Wrote %s", display_path(path))
    log.info("Windows:\n%s", windows.to_string(index=False))


if __name__ == "__main__":
    main()
