"""Step 07: reproducible random sample of creative credits for manual checking.

  python scripts/07_spotcheck_sample.py            # write outputs/tables/spotcheck.csv
  python scripts/07_spotcheck_sample.py --score    # after filling it in: error rates

Fill the 'correct' column with y / n (or 1 / 0) and add notes. Re-running
without --score never overwrites a spotcheck.csv that already has answers
unless --force is given.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from src.common import apply_limit, log, parse_args, read_parquet
from src.names import enwiki_url

OUT = config.OUTPUT_TABLES / "spotcheck.csv"
YES, NO = {"y", "yes", "1", "true", "t", "correct"}, {"n", "no", "0", "false", "f", "wrong", "incorrect"}


def extra(p):
    p.add_argument("--score", action="store_true", help="Compute error rates from a filled-in spotcheck.csv")
    p.add_argument("--force", action="store_true", help="Overwrite a spotcheck.csv that has answers")
    p.add_argument("--n", type=int, default=config.SPOTCHECK_N, help="Sample size")


def wilson(k, n, z=1.96):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def read_answers():
    # Numbers can export the table name as an extra first line; start at the header row
    with open(OUT, encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    skip = next((i for i, line in enumerate(lines[:5]) if line.startswith("show_id,")), None)
    if skip is None:
        sys.exit(f"{OUT}: header row (show_id,...) not found in the first lines; re-export as plain CSV.")
    return pd.read_csv(OUT, dtype=str, skiprows=skip, encoding="utf-8-sig")


def score():
    if not OUT.exists():
        sys.exit(f"{OUT} not found; run without --score first.")
    df = read_answers()
    ans = df["correct"].fillna("").str.strip().str.lower()
    df["ok"] = ans.map(lambda a: True if a in YES else (False if a in NO else None))
    done = df[df["ok"].notna()]
    if done.empty:
        sys.exit("No rows answered yet: fill the 'correct' column with y/n.")
    k_err, n = int((~done["ok"].astype(bool)).sum()), len(done)
    lo, hi = wilson(k_err, n)
    print(f"Answered {n}/{len(df)} rows. Error rate {k_err}/{n} = {k_err / n:.1%} "
          f"(95% Wilson CI {lo:.1%}-{hi:.1%})")
    for col in ["source", "extraction", "role"]:
        g = done.groupby(col)["ok"].agg(n="size", errors=lambda s: int((~s.astype(bool)).sum()))
        g["error_rate"] = (g["errors"] / g["n"]).map("{:.0%}".format)
        print(f"\nBy {col}:\n{g.to_string()}")


def main():
    args = parse_args(__doc__.splitlines()[0], extra)
    if args.score:
        score()
        return
    if OUT.exists() and not args.force:
        prev = read_answers()
        if prev["correct"].fillna("").str.strip().ne("").any():
            sys.exit(f"{OUT} already has answers; use --score, or --force to draw a new sample.")

    credits = read_parquet(config.DATA_PROCESSED / "credits.parquet")
    shows = apply_limit(read_parquet(config.DATA_PROCESSED / "shows.parquet"), args.limit)
    credits = credits[credits["show_id"].isin(shows["show_id"])]
    mentions = read_parquet(config.DATA_INTERIM / "credit_mentions.parquet")
    people = read_parquet(config.DATA_PROCESSED / "people.parquet")

    sample = credits.sample(n=min(args.n, len(credits)), random_state=config.RANDOM_SEED).copy()
    sample = sample.merge(shows[["show_id", "wikidata_qid", "enwiki_title"]], on="show_id", how="left")
    # one piece of evidence per credit: the first prose sentence, if any
    ctx = (mentions.dropna(subset=["context"])
           .groupby(["show_id", "person_id", "role"])["context"].first())
    sample["evidence"] = [ctx.get((s, p, r)) for s, p, r in zip(sample["show_id"], sample["person_id"], sample["role"])]
    sample["show_wikipedia_url"] = sample["enwiki_title"].map(lambda t: enwiki_url(t) if isinstance(t, str) else None)
    sample["show_wikidata_url"] = sample["wikidata_qid"].map(
        lambda q: f"https://www.wikidata.org/wiki/{q}" if isinstance(q, str) else None)
    pmap = people.set_index("person_id")
    sample["person_url"] = [
        enwiki_url(pmap.at[p, "enwiki_title"]) if p in pmap.index and isinstance(pmap.at[p, "enwiki_title"], str)
        else (f"https://www.wikidata.org/wiki/{p}" if p.startswith("Q") else None)
        for p in sample["person_id"]]
    sample["correct"] = ""
    sample["notes"] = ""
    cols = ["show_id", "title", "year", "person_id", "person_name", "role", "role_raw", "source", "extraction",
            "resolution", "is_original_production", "evidence", "show_wikipedia_url", "show_wikidata_url",
            "person_url", "correct", "notes"]
    sample[cols].to_csv(OUT, index=False)
    log.info("Wrote %s: %d credits (seed %d). Fill 'correct' with y/n, then run with --score.",
             OUT.relative_to(config.ROOT), len(sample), config.RANDOM_SEED)
    log.info("Sample mix by source: %s | extraction: %s", sample["source"].value_counts().to_dict(),
             sample["extraction"].value_counts().to_dict())


if __name__ == "__main__":
    main()
