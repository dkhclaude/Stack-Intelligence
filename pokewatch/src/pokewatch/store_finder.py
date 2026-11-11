"""Check whether an online store can be monitored with the Shopify connector.

`pokewatch check-store <url>` answers, using only requests the store permits:
  1. Is it a Shopify storefront with the public products feed?
  2. Does its robots.txt allow PokéWatch to read that feed?
  3. Which collection holds its Pokémon products (smaller, faster checks)?
  4. How many sealed Pokémon TCG listings can we actually see there?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .classify import classify
from .config import DEFAULT_RUNTIME, Settings
from .connectors.shopify import ShopifyConnector
from .domain import StockState
from .http import BlockedError, DisallowedError, FetchError, PoliteClient

POKEMON_COLLECTION = re.compile(r"pok[eé]mon", re.I)


@dataclass
class StoreCheck:
    domain: str
    ok: bool = False
    is_shopify: bool = False
    problem: str | None = None
    collections: list[tuple[str, str, int | None]] = field(default_factory=list)  # (handle, title, count)
    chosen_collection: str | None = None
    tcg_listings: int = 0
    in_stock: int = 0
    samples: list[str] = field(default_factory=list)

    @property
    def config_line(self) -> str | None:
        if not self.ok:
            return None
        name = self.domain.split(".")[0].replace("-", " ").title()
        return f"{name}|{self.domain}|{self.chosen_collection or 'all'}"


def normalize_domain(url: str) -> str:
    d = re.sub(r"^https?://", "", url.strip()).split("/")[0].lower()
    return d


def check_store(url: str, settings: Settings, transport=None, sleep=None) -> StoreCheck:
    domain = normalize_domain(url)
    res = StoreCheck(domain=domain)
    kw = {"transport": transport}
    if sleep is not None:
        kw["sleep"] = sleep
    client = PoliteClient(domain, settings.user_agent, requests_per_minute=10, timeout_s=settings.http_timeout_s,
                          max_retries=1, respect_robots=True, **kw)
    with client as c:
        # 1+2: Shopify products feed, robots.txt enforced by the client
        try:
            r = c.get(f"https://{domain}/products.json", params={"limit": 1})
        except DisallowedError:
            res.problem = "The store's robots.txt doesn't allow automated reading of its product feed (or it couldn't be read)."
            return res
        except BlockedError:
            res.problem = "The store blocks automated requests (bot protection). PokéWatch won't work around that."
            return res
        except FetchError as e:
            res.problem = f"Couldn't reach the store: {e}"
            return res
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code != 200 or not isinstance(data, dict) or not isinstance(data.get("products"), list):
            res.problem = "Not a Shopify store (no public products feed), so PokéWatch can't monitor it yet."
            return res
        res.is_shopify = True

        # 3: find a Pokémon collection
        try:
            r = c.get(f"https://{domain}/collections.json", params={"limit": 250})
            cols = ((r.json() or {}).get("collections") or []) if r.status_code == 200 else []
        except (FetchError, ValueError):
            cols = []
        for col in cols:
            title, handle = col.get("title") or "", col.get("handle") or ""
            if POKEMON_COLLECTION.search(title) or POKEMON_COLLECTION.search(handle):
                res.collections.append((handle, title, col.get("products_count")))
        # prefer a sealed / TCG collection, then the largest Pokémon one
        def rank(cand):
            text = f"{cand[0]} {cand[1]}".lower()
            score = 2 if "sealed" in text else 1 if ("tcg" in text or "card" in text) else 0
            return (score, cand[2] or 0)
        if res.collections:
            res.chosen_collection = sorted(res.collections, key=rank, reverse=True)[0][0]

    # 4: run the real connector once against that collection
    conn = ShopifyConnector(domain, domain, res.chosen_collection or "all", settings, DEFAULT_RUNTIME, **kw)
    result = conn.discover([])
    if result.fatal:
        res.problem = f"Feed check failed: {result.fatal.message}"
        return res
    for s in result.snapshots:
        f = classify(s.title, s.category_hint)
        if f.tcg_confidence >= DEFAULT_RUNTIME["alerts"]["min_tcg_confidence"]:
            res.tcg_listings += 1
            res.in_stock += s.state in (StockState.IN_STOCK, StockState.PREORDER)
            if len(res.samples) < 5:
                res.samples.append(f"{s.state.value:12} {('$' + str(s.price)) if s.price else '-':>9}  {s.title[:70]}")
    if res.tcg_listings == 0:
        res.problem = "The store's feed works, but no sealed Pokémon TCG products were found in it."
        return res
    res.ok = True
    return res


def add_to_env(line: str, env_path) -> str:
    """Append a store to SHOPIFY_STORES in .env (creating the key if needed). Returns the new value."""
    from pathlib import Path
    p = Path(env_path)
    lines = p.read_text().splitlines() if p.exists() else []
    domain = line.split("|")[1]
    for i, ln in enumerate(lines):
        if ln.startswith("SHOPIFY_STORES="):
            current = ln.split("=", 1)[1].strip().strip('"')
            stores = [s for s in current.split(";") if s.strip()]
            stores = [s for s in stores if s.split("|")[1:2] != [domain]] + [line]
            lines[i] = "SHOPIFY_STORES=" + ";".join(stores)
            break
    else:
        lines.append("SHOPIFY_STORES=" + line)
    p.write_text("\n".join(lines) + "\n")
    return [ln for ln in lines if ln.startswith("SHOPIFY_STORES=")][0].split("=", 1)[1]
