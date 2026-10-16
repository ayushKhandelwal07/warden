import hashlib
import json
import re
import time
from pathlib import Path

import httpx

from warden import config

_client = httpx.Client(timeout=60, headers={"User-Agent": "warden-ingest"}, follow_redirects=True)


def now_ms() -> int:
    return int(time.time() * 1000)


def _cache_path(namespace: str, key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:60]
    p = config.CACHE_DIR / namespace / f"{safe}-{h}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def cached_json(namespace: str, key: str, fetch, refresh: bool = False):
    """Return fetch() result, cached on disk under data/raw/cache/<namespace>/."""
    p = _cache_path(namespace, key)
    if p.exists() and not refresh:
        return json.loads(p.read_text(encoding="utf-8"))
    data = fetch()
    p.write_text(json.dumps(data), encoding="utf-8")
    return data


def http_get_json(url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            r = _client.get(url)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def http_post_json(url: str, body: dict, retries: int = 3):
    for attempt in range(retries):
        try:
            r = _client.post(url, json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def version_key(v: str) -> tuple:
    """Loose, ecosystem-agnostic version ordering: numeric parts compare as ints."""
    v = v.strip().lstrip("vV")
    main = re.split(r"[-+]", v, maxsplit=1)
    parts = [int(x) if x.isdigit() else x for x in re.split(r"[.]", main[0])]
    norm = [(0, p) if isinstance(p, int) else (1, p) for p in parts]
    # A pre-release (1.2.3-rc1) sorts before the release (1.2.3).
    pre = (0, main[1]) if len(main) > 1 and not v.startswith(main[0] + "+") else (1, "")
    return tuple(norm) + (pre,)
