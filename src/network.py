"""Person-show table and per-window collaboration graphs, shared by the method steps (11, 15).

The graphs are the same as step 08's edges_by_window.parquet: people are linked if they share a
show in the training window [T - W, T), within one mode (strict or loose).
"""
import json
import sys
from itertools import combinations

import numpy as np
import pandas as pd

import config
from src.common import display_path, read_parquet

PERSON_SHOW = config.DATA_PROCESSED / "network" / "person_show.parquet"
VIZ_DATA = config.ROOT / "viz" / "data"
COMMUNITIES_DIR = config.DATA_PROCESSED / "communities"


def load_person_show(source="auto"):
    """One row per person-show pair: person_id, show_id, year, in_strict, in_loose.

    source: 'parquet' (step 08), 'json' (viz/data/credits.json from step 13, same rows and flags),
    or 'auto' (parquet if it exists, else json). Returns (table, description of the source).
    """
    cols = ["person_id", "show_id", "year", "in_strict", "in_loose"]
    if source == "parquet" or (source == "auto" and PERSON_SHOW.exists()):
        ps = read_parquet(PERSON_SHOW).rename(columns={"show_year": "year"})
        return ps[cols], display_path(PERSON_SHOW)
    path = VIZ_DATA / "credits.json"
    if not path.exists():
        sys.exit(f"Missing {path}. Run step 13, or step 08 and use --source parquet.")
    ps = pd.DataFrame(json.loads(path.read_text())).rename(columns={
        "person": "person_id", "show": "show_id", "strict": "in_strict", "loose": "in_loose"})
    return ps[cols], display_path(path)


def load_names():
    path = VIZ_DATA / "people.json"
    if not path.exists():
        return {}
    return {p["id"]: p["name"] for p in json.loads(path.read_text())}


def in_mode(ps, mode):
    return ps[ps[f"in_{mode}"]]


def pair_counts(ps):
    """Shows shared per unordered pair (person_a < person_b) in a person-show table."""
    counts = {}
    for _, g in ps.groupby("show_id"):
        for pair in combinations(sorted(g["person_id"].unique()), 2):
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def window_graph(ps, mode, cutoff):
    """People (sorted), boolean adjacency matrix and the window's person-show rows for [T - W, T)."""
    W = config.NETWORK_WINDOW_YEARS
    m = in_mode(ps, mode)
    sub = m[(m["year"] >= cutoff - W) & (m["year"] < cutoff)]
    pairs = pair_counts(sub)
    people = sorted({p for pair in pairs for p in pair})
    idx = {p: i for i, p in enumerate(people)}
    A = np.zeros((len(people), len(people)), dtype=bool)
    for a, b in pairs:
        A[idx[a], idx[b]] = A[idx[b], idx[a]] = True
    return people, A, sub[sub["person_id"].isin(idx)]
