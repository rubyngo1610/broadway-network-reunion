"""Polite, caching HTTP client for the Wikidata SPARQL endpoint and the
English Wikipedia MediaWiki API.

Every response is written to data/raw/ as JSON, keyed by a hash of the
request. A cached response is returned without touching the network unless
refresh=True.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)

ALLOWED_HOSTS = {config.WIKIDATA_SPARQL, config.MEDIAWIKI_API}


class FetchError(RuntimeError):
    pass


def _cache_key(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


class CachedClient:
    def __init__(self, refresh: bool = False):
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self._last_call = {}  # url -> monotonic time of last request
        self.n_network = 0
        self.n_cached = 0
        if not config.CONTACT_EMAIL:
            log.warning("CONTACT_EMAIL is not set in config.py / BROADWAY_CONTACT_EMAIL; "
                        "Wikimedia may throttle anonymous-looking clients.")

    # -- public API ---------------------------------------------------------
    def sparql(self, query: str, subdir: str = "misc") -> dict:
        """Run a SPARQL query (POST) and return the parsed JSON results."""
        payload = {"endpoint": config.WIKIDATA_SPARQL, "query": query}
        return self._cached(
            payload, config.RAW_SPARQL / subdir,
            lambda: self._request(
                "POST", config.WIKIDATA_SPARQL, config.SLEEP_SPARQL,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"}),
        )

    def mediawiki(self, params: dict, subdir: str = "misc", cache: bool = True) -> dict:
        """Call the MediaWiki action API. 'format' and 'formatversion' are set here.

        cache=False skips the response cache, for callers that store the
        result themselves (e.g. per-article wikitext files)."""
        params = {**params, "format": "json", "formatversion": "2"}
        if not cache:
            self.n_network += 1
            return self._mediawiki_checked(params)
        payload = {"endpoint": config.MEDIAWIKI_API, "params": params}
        return self._cached(
            payload, config.RAW_MEDIAWIKI / subdir,
            lambda: self._mediawiki_checked(params),
        )

    # -- internals ----------------------------------------------------------
    def _mediawiki_checked(self, params: dict) -> dict:
        data = self._request("POST", config.MEDIAWIKI_API, config.SLEEP_MEDIAWIKI, data=params)
        if "error" in data:
            raise FetchError(f"MediaWiki API error: {data['error']}")
        return data

    def _cached(self, payload: dict, cache_dir: Path, fetch) -> dict:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{_cache_key(payload)}.json"
        if path.exists() and not self.refresh:
            self.n_cached += 1
            with open(path, encoding="utf-8") as f:
                return json.load(f)["response"]
        response = fetch()
        self.n_network += 1
        record = {
            "request": payload,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "response": response,
        }
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        tmp.replace(path)  # atomic: a crash never leaves a half-written cache file
        return response

    def _throttle(self, url: str, sleep_s: float):
        last = self._last_call.get(url)
        if last is not None:
            wait = sleep_s - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[url] = time.monotonic()

    def _request(self, method: str, url: str, sleep_s: float, **kwargs) -> dict:
        if url not in ALLOWED_HOSTS:
            raise FetchError(f"Refusing to contact non-allowlisted URL: {url}")
        for attempt in range(config.MAX_RETRIES + 1):
            self._throttle(url, sleep_s)
            try:
                resp = self.session.request(method, url, timeout=config.REQUEST_TIMEOUT, **kwargs)
            except requests.RequestException as e:
                wait = config.BACKOFF_BASE * 2 ** attempt
                log.warning("Network error (%s); retry %d in %.0fs", e, attempt + 1, wait)
                time.sleep(wait)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = config.BACKOFF_BASE * 2 ** attempt
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), config.MAX_RETRY_AFTER))
                log.warning("HTTP %d from %s; retry %d/%d in %.0fs",
                            resp.status_code, url, attempt + 1, config.MAX_RETRIES, wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise FetchError(f"HTTP {resp.status_code} from {url}: {resp.text[:500]}")
            # Some MediaWiki errors (e.g. maxlag) come back as 200 + JSON error
            try:
                return resp.json()
            except ValueError as e:
                raise FetchError(f"Non-JSON response from {url}: {resp.text[:300]}") from e
        raise FetchError(f"Gave up on {url} after {config.MAX_RETRIES} retries")
