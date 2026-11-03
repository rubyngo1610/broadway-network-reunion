"""Step 06: coverage audit - which roles and person attributes each source supports.

Every table is computed for two show sets (column show_set):
  core            plausible Broadway musicals: drops pages found only in per-show subcategories
                  shows with a year before config.CORE_MIN_YEAR, and shows with no year (see src/filters.py)
  all_candidates  every row of shows.parquet

Outputs
  outputs/tables/show_set.csv                  every show with its exclusion reason (empty = core)
  outputs/tables/coverage_by_role_decade.csv   show_set x scope x source x role x decade
  outputs/tables/people_coverage.csv           person attributes by decade of first credit
  outputs/tables/cast_coverage.csv             shows with any cast data, by decade (if 04b ran)
  outputs/figures/coverage_heatmap.png         core set: roles x decades, one panel per source
  outputs/figures/coverage_heatmap_all_candidates.png
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

import config
from src.common import log, parse_args, read_parquet
from src.filters import show_exclusion_reason
from src.roles import ROLE_VOCAB

SOURCES = ["wikidata", "wikipedia", "either"]
SHOW_SETS = ["core", "all_candidates"]
# Sequential single-hue ramp (light = near zero), from the dataviz reference palette
CMAP = LinearSegmentedColormap.from_list(
    "coverage", ["#f4f7fb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
INK, INK_ON_DARK, MUTED = "#1f1f1e", "#ffffff", "#6b6a66"


def decade_label(year):
    return f"{int(year) // 10 * 10}s" if pd.notna(year) else "unknown"


def role_coverage(credits, shows):
    shows = shows.assign(decade=shows["year"].map(decade_label))
    n_by_decade = shows.groupby("decade").size()
    c = credits.merge(shows[["show_id", "decade"]], on="show_id")
    c["in_wikidata"] = c["source"].str.contains("wikidata")
    c["in_wikipedia"] = c["source"].str.contains("wikipedia")
    rows = []
    for scope, sub in [("all", c), ("original_only", c[c["is_original_production"].fillna(False)])]:
        for source in SOURCES:
            s = sub if source == "either" else sub[sub[f"in_{source}"]]
            have = s.groupby(["role", "decade"])["show_id"].nunique()
            have_all = s.groupby("role")["show_id"].nunique()
            for role in ROLE_VOCAB:
                for decade, n in list(n_by_decade.items()) + [("all", len(shows))]:
                    k = have_all.get(role, 0) if decade == "all" else have.get((role, decade), 0)
                    rows.append({"scope": scope, "source": source, "role": role, "decade": decade,
                                 "n_shows_with_role": int(k), "n_shows": int(n),
                                 "pct_shows": round(100 * k / n, 1) if n else np.nan})
    return pd.DataFrame(rows)


def people_coverage(people, credits, shows):
    first = credits[["show_id", "person_id"]].merge(shows[["show_id", "year"]], on="show_id").groupby("person_id")["year"].min()
    p = people.assign(first_year=people["person_id"].map(first))
    p["decade_first_credit"] = p["first_year"].map(decade_label)
    rows = []
    for group, sub in [("all people", p), ("humans with QID", p[p["is_human"].fillna(False)])]:
        for decade, g in list(sub.groupby("decade_first_credit")) + [("all", sub)]:
            rows.append({"group": group, "decade_first_credit": decade, "n_people": len(g),
                         "pct_with_qid": round(100 * g["qid"].notna().mean(), 1),
                         "pct_birthplace": round(100 * g["birthplace"].notna().mean(), 1),
                         "pct_coordinates": round(100 * g["lat"].notna().mean(), 1),
                         "pct_citizenship": round(100 * g["citizenship"].notna().mean(), 1),
                         "pct_birth_year": round(100 * g["birth_year"].notna().mean(), 1)})
    return pd.DataFrame(rows)


def heatmap(cov, path, label):
    cov = cov[(cov["scope"] == "all") & (cov["decade"] != "all")]
    decades = sorted(d for d in cov["decade"].unique() if d != "unknown") + \
        (["unknown"] if "unknown" in set(cov["decade"]) else [])
    n_shows = cov.drop_duplicates("decade").set_index("decade")["n_shows"]
    either = cov[cov["source"] == "either"].groupby("role")["n_shows_with_role"].sum()
    roles = [r for r in ROLE_VOCAB if either.get(r, 0) > 0]  # drop roles with no credits at all
    if not roles:
        log.warning("No credits to plot")
        return
    fig_h = 1.2 + len(SOURCES) * (0.32 * len(roles) + 0.6)
    fig, axes = plt.subplots(len(SOURCES), 1, figsize=(max(7, 0.62 * len(decades) + 3), fig_h),
                             sharex=True, constrained_layout=True)
    for ax, source in zip(np.atleast_1d(axes), SOURCES):
        grid = (cov[cov["source"] == source].pivot(index="role", columns="decade", values="pct_shows")
                .reindex(index=roles, columns=decades))
        im = ax.imshow(grid.values, cmap=CMAP, vmin=0, vmax=100, aspect="auto")
        for i in range(len(roles)):
            for j in range(len(decades)):
                v = grid.values[i, j]
                if np.isnan(v):
                    continue
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color=INK_ON_DARK if v >= 55 else (MUTED if v == 0 else INK))
        ax.set_yticks(range(len(roles)), [r.replace("_", " ") for r in roles], fontsize=8)
        ax.set_title(f"Source: {source}", loc="left", fontsize=9, color=INK)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks(np.arange(len(decades) + 1) - 0.5, minor=True)
        ax.set_yticks(np.arange(len(roles) + 1) - 0.5, minor=True)
        ax.grid(which="minor", color="white", linewidth=2)  # 2px surface gap between cells
    last = np.atleast_1d(axes)[-1]
    last.set_xticks(range(len(decades)), [f"{d}\nn={n_shows.get(d, 0)}" for d in decades], fontsize=7)
    cb = fig.colorbar(im, ax=axes, shrink=0.5, pad=0.01)
    cb.set_label("% of shows with ≥1 credit in role", fontsize=8)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7, length=0)
    fig.suptitle(f"Creative-role coverage by decade of opening, {label} (credits from all productions)",
                 fontsize=10, x=0.02,
                 ha="left", color=INK)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def summarize(cov):
    e = cov[(cov["scope"] == "all") & (cov["source"] == "either")]
    orig = cov[(cov["scope"] == "original_only") & (cov["source"] == "either") & (cov["decade"] == "all")]
    overall = e[e["decade"] == "all"].set_index("role")["pct_shows"].sort_values(ascending=False)
    overall = overall[overall > 0]
    good = overall[overall >= 50]
    log.info("Well covered (>=50%% of shows, either source): %s",
             ", ".join(f"{r} {v:.0f}%" for r, v in good.items()) or "none")
    log.info("Thin (<50%%): %s", ", ".join(f"{r} {v:.0f}%" for r, v in overall[overall < 50].items()) or "none")
    by_src = cov[(cov["scope"] == "all") & (cov["decade"] == "all")].pivot(
        index="role", columns="source", values="pct_shows").reindex(overall.index)
    by_src["original_only"] = orig.set_index("role")["pct_shows"]
    log.info("Overall %% of shows by source (original_only = either source, original production):\n%s",
             by_src.to_string())
    dec = e[~e["decade"].isin(["all", "unknown"]) & (e["n_shows"] >= 5)]  # ignore tiny decades
    for role in good.index:
        d = dec[dec["role"] == role].set_index("decade")["pct_shows"].sort_index()
        low = d[d < 0.5 * good[role]]
        if len(low):
            log.info("  %s drops below half its overall rate in: %s", role,
                     ", ".join(f"{k} ({v:.0f}%)" for k, v in low.items()))


def cast_coverage(cast, shows):
    s = shows.assign(decade=shows["year"].map(decade_label))
    s["has_cast"] = s["show_id"].isin(cast["show_id"])
    s["has_original_broadway_cast"] = s["show_id"].isin(cast.loc[cast["is_original_broadway"].fillna(False), "show_id"])
    cc = s.groupby("decade").agg(n_shows=("show_id", "size"), pct_any_cast=("has_cast", "mean"),
                                 pct_original_broadway_cast=("has_original_broadway_cast", "mean"))
    cc[["pct_any_cast", "pct_original_broadway_cast"]] = (100 * cc[["pct_any_cast", "pct_original_broadway_cast"]]).round(1)
    return cc


def main():
    parse_args(__doc__.splitlines()[0])
    credits = read_parquet(config.DATA_PROCESSED / "credits.parquet")
    shows = read_parquet(config.DATA_PROCESSED / "shows.parquet")
    people = read_parquet(config.DATA_PROCESSED / "people.parquet")
    cast = read_parquet(config.DATA_PROCESSED / "cast_credits.parquet", required=False)

    shows["exclusion_reason"] = show_exclusion_reason(shows)
    shows[["show_id", "title", "year", "year_source", "ibdb_id", "enwiki_title", "wp_category_depth",
           "n_credits", "exclusion_reason"]].to_csv(config.OUTPUT_TABLES / "show_set.csv", index=False)
    log.info("Show sets: %d candidates -> %d core (excluded: %s)",
             len(shows), shows["exclusion_reason"].isna().sum(),
             shows["exclusion_reason"].value_counts().to_dict())

    covs, pcs, ccs = [], [], []
    for show_set in SHOW_SETS:
        s = shows[shows["exclusion_reason"].isna()] if show_set == "core" else shows
        c = credits[credits["show_id"].isin(s["show_id"])]
        cov = role_coverage(c, s)
        covs.append(cov.assign(show_set=show_set))
        pcs.append(people_coverage(people[people["person_id"].isin(c["person_id"])], c, s).assign(show_set=show_set))
        name = "coverage_heatmap.png" if show_set == "core" else f"coverage_heatmap_{show_set}.png"
        heatmap(cov, config.OUTPUT_FIGURES / name, "core show set" if show_set == "core" else "all candidate shows")
        if cast is not None:
            ccs.append(cast_coverage(cast, s).assign(show_set=show_set).reset_index())

    cov = pd.concat(covs)
    cov = cov[["show_set"] + [x for x in cov.columns if x != "show_set"]]
    cov.to_csv(config.OUTPUT_TABLES / "coverage_by_role_decade.csv", index=False)
    pc = pd.concat(pcs)
    pc = pc[["show_set"] + [x for x in pc.columns if x != "show_set"]]
    pc.to_csv(config.OUTPUT_TABLES / "people_coverage.csv", index=False)
    log.info("Wrote outputs/tables/show_set.csv, coverage_by_role_decade.csv, people_coverage.csv, "
             "figures/coverage_heatmap.png (core), coverage_heatmap_all_candidates.png")

    if ccs:
        cc = pd.concat(ccs)
        cc = cc[["show_set"] + [x for x in cc.columns if x != "show_set"]]
        cc.to_csv(config.OUTPUT_TABLES / "cast_coverage.csv", index=False)
        log.info("Cast coverage by decade (core set):\n%s",
                 cc[cc["show_set"] == "core"].drop(columns="show_set").set_index("decade").to_string())

    log.info("--- Core show set ---")
    summarize(cov[cov["show_set"] == "core"])
    core_pc = pc[(pc["show_set"] == "core") & (pc["decade_first_credit"] == "all")]
    log.info("People coverage, core set (all decades):\n%s",
             core_pc.set_index("group").drop(columns=["show_set", "decade_first_credit"]).to_string())
    e = cov[(cov["scope"] == "all") & (cov["source"] == "either") & (cov["decade"] == "all")]
    cmp = e.pivot(index="role", columns="show_set", values="pct_shows")[SHOW_SETS]
    log.info("%% of shows with role, core vs all candidates (either source):\n%s",
             cmp[cmp.max(axis=1) > 0].sort_values("core", ascending=False).to_string())


if __name__ == "__main__":
    main()
