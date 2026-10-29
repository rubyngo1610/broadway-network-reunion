"""CLI, logging and small I/O helpers shared by the pipeline scripts."""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

import config

log = logging.getLogger("pipeline")


def parse_args(description: str, extra=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N shows (quick test).")
    p.add_argument("--refresh", action="store_true",
                   help="Ignore cached raw responses and re-download.")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    if extra:
        extra(p)
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return args


def chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def read_parquet(path: Path, required: bool = True) -> pd.DataFrame | None:
    if not path.exists():
        if required:
            sys.exit(f"Missing input {path}. Run the earlier pipeline steps first.")
        return None
    return pd.read_parquet(path)


def write_parquet(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("Wrote %s (%d rows, %d cols)", display_path(path), len(df), df.shape[1])


def display_path(path: Path) -> str:
    for base in (config.DATA.parent, config.ROOT):
        if path.is_relative_to(base):
            return str(path.relative_to(base))
    return str(path)


def apply_limit(shows: pd.DataFrame, limit: int | None) -> pd.DataFrame:
    """Deterministic subset: the first N shows in show_id order."""
    if limit is None:
        return shows
    log.info("--limit %d: using the first %d of %d shows", limit, min(limit, len(shows)), len(shows))
    return shows.sort_values("show_id").head(limit).reset_index(drop=True)
