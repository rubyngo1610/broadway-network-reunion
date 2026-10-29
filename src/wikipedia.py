"""MediaWiki API helpers: category crawl, title -> QID, batched wikitext."""
import logging

from tqdm import tqdm

import config
from src.common import chunks
from src.names import wiki_title

log = logging.getLogger(__name__)


def _query_all(client, params: dict, subdir: str, cache: bool = True):
    """Yield every page of a continuable action=query request."""
    cont = {}
    while True:
        data = client.mediawiki({"action": "query", **params, **cont}, subdir, cache=cache)
        yield data
        if "continue" not in data:
            return
        cont = data["continue"]


def category_members(client, category: str, max_depth: int, limit: int | None = None,
                     skip_subcat=None):
    """Recursively list main-namespace pages in a category.

    Returns {title: (depth, category_found_in)} and the list of visited
    subcategories as (category, depth, skipped: bool).
    """
    pages, visited = {}, []
    queue, seen = [(category, 0)], {category}
    while queue:
        cat, depth = queue.pop(0)
        visited.append((cat, depth, False))
        for data in _query_all(client, {"list": "categorymembers", "cmtitle": cat,
                                        "cmtype": "page|subcat", "cmlimit": "500"}, "categories"):
            for m in data["query"]["categorymembers"]:
                if m["ns"] == 0:
                    pages.setdefault(m["title"], (depth, cat))
                elif m["ns"] == 14 and depth < max_depth and m["title"] not in seen:
                    seen.add(m["title"])
                    if skip_subcat and skip_subcat(m["title"]):
                        visited.append((m["title"], depth + 1, True))
                    else:
                        queue.append((m["title"], depth + 1))
            if limit and len(pages) >= limit:
                return dict(list(pages.items())[:limit]), visited
    return pages, visited


def resolve_titles(client, titles, subdir: str = "pageprops") -> dict:
    """Map each title to its resolved article and Wikidata QID.

    Follows redirects and normalization. Returns
    {input_title: {"resolved_title", "qid", "pageid", "missing", "redirected"}}.
    """
    out = {}
    titles = sorted({wiki_title(t) for t in titles if t})
    for batch in tqdm(list(chunks(titles, config.MEDIAWIKI_BATCH)), desc="pageprops", leave=False):
        data = client.mediawiki({"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                                 "redirects": "1", "titles": "|".join(batch)}, subdir)
        q = data.get("query", {})
        step = {t: t for t in batch}
        for n in q.get("normalized", []):
            step = {k: (n["to"] if v == n["from"] else v) for k, v in step.items()}
        redirects = {r["from"]: r["to"] for r in q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in batch:
            cur = step[t]
            redirected = cur in redirects
            cur = redirects.get(cur, cur)
            page = pages.get(cur, {})
            out[t] = {
                "resolved_title": cur,
                "qid": page.get("pageprops", {}).get("wikibase_item"),
                "pageid": page.get("pageid"),
                "missing": bool(page.get("missing") or page.get("invalid") or not page),
                "redirected": redirected,
            }
    return out


def fetch_wikitext_batch(client, titles: list[str]) -> dict:
    """Current wikitext for up to 50 titles (redirects resolved).

    Returns {input_title: {"resolved_title", "pageid", "revid", "timestamp",
    "wikitext", "missing", "redirected_from"}}.
    """
    pages, normalized, redirects = {}, {}, {}
    for data in _query_all(client, {"prop": "revisions", "rvprop": "content|ids|timestamp",
                                    "rvslots": "main", "redirects": "1",
                                    "titles": "|".join(titles)}, "wikitext", cache=False):
        q = data.get("query", {})
        normalized.update({n["from"]: n["to"] for n in q.get("normalized", [])})
        redirects.update({r["from"]: r["to"] for r in q.get("redirects", [])})
        for p in q.get("pages", []):
            if p.get("revisions"):  # continuation pages repeat titles without content
                pages[p["title"]] = p
            else:
                pages.setdefault(p["title"], p)
    out = {}
    for t in titles:
        cur = normalized.get(t, t)
        resolved = redirects.get(cur, cur)
        p = pages.get(resolved, {})
        rev = (p.get("revisions") or [{}])[0]
        out[t] = {
            "requested_title": t,
            "resolved_title": resolved,
            "redirected_from": cur if resolved != cur else None,
            "pageid": p.get("pageid"),
            "revid": rev.get("revid"),
            "timestamp": rev.get("timestamp"),
            "wikitext": rev.get("slots", {}).get("main", {}).get("content"),
            "missing": bool(p.get("missing") or not rev),
        }
    return out
