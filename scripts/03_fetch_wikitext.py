"""Step 03: fetch current wikitext for every show article.

Batched (50 titles per request), redirects resolved. Each article is cached
as one JSON file in data/raw/wikitext/; titles already on disk are skipped
unless --refresh is given.

Outputs: data/raw/wikitext/*.json, data/interim/wikitext_index.parquet
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from tqdm import tqdm

import config
from src.common import apply_limit, chunks, log, parse_args, read_parquet, write_parquet
from src.http_client import CachedClient
from src.wikipedia import fetch_wikitext_batch


def wikitext_path(title: str) -> Path:
    slug = re.sub(r"[^\w\-]+", "_", title)[:80].strip("_")
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
    return config.RAW_WIKITEXT / f"{slug}__{digest}.json"


def load_wikitext(title: str) -> dict | None:
    """Read a cached article (used by steps 04 and 04b)."""
    path = wikitext_path(title)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    args = parse_args(__doc__.splitlines()[0])
    client = CachedClient(refresh=args.refresh)
    shows = apply_limit(read_parquet(config.DATA_INTERIM / "shows.parquet"), args.limit)
    titles = sorted(shows["enwiki_title"].dropna().unique())
    todo = [t for t in titles if args.refresh or not wikitext_path(t).exists()]
    log.info("%d shows have an enwiki article; %d already cached, %d to fetch",
             len(titles), len(titles) - len(todo), len(todo))

    for batch in tqdm(list(chunks(todo, config.MEDIAWIKI_BATCH)), desc="wikitext"):
        fetched_at = datetime.now(timezone.utc).isoformat()
        for title, rec in fetch_wikitext_batch(client, batch).items():
            path = wikitext_path(title)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({**rec, "fetched_at": fetched_at}, f, ensure_ascii=False)
            tmp.replace(path)

    rows = []
    for t in titles:
        rec = load_wikitext(t) or {}
        rows.append({
            "enwiki_title": t,
            "resolved_title": rec.get("resolved_title"),
            "redirected_from": rec.get("redirected_from"),
            "pageid": rec.get("pageid"),
            "revid": rec.get("revid"),
            "rev_timestamp": rec.get("timestamp"),
            "missing": rec.get("missing", True),
            "n_chars": len(rec.get("wikitext") or ""),
            "file": wikitext_path(t).name,
        })
    index = shows[["show_id", "enwiki_title"]].dropna().merge(pd.DataFrame(rows), on="enwiki_title", how="left")
    write_parquet(index, config.DATA_INTERIM / "wikitext_index.parquet")
    log.info("Articles: %d | missing %d | via redirect %d | median length %d chars",
             len(index), index["missing"].sum(), index["redirected_from"].notna().sum(),
             int(index["n_chars"].median()) if len(index) else 0)
    log.info("HTTP: %d network requests", client.n_network)


if __name__ == "__main__":
    main()
