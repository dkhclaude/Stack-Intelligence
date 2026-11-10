"""Generic Shopify storefront connector for reputable hobby / game stores.

Uses the public storefront JSON endpoint (/collections/<handle>/products.json),
which Shopify serves to any visitor. robots.txt is honoured and any bot wall
aborts the check (UNKNOWN), it is never worked around.

Configure with SHOPIFY_STORES="Store Name|store-domain.com|collection-handle;..."
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ..classify import slug
from ..domain import CheckFailure, CheckResult, CheckStatus, ListingSnapshot, StockState
from ..http import FetchError
from .base import Connector

PREORDER_RE = re.compile(r"\bpre[- ]?order\b|\bpreorder\b", re.I)


def parse_store_config(raw: str | None) -> list[tuple[str, str, str]]:
    stores = []
    for chunk in (raw or "").split(";"):
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            domain = re.sub(r"^https?://", "", parts[1]).strip("/")
            stores.append((parts[0], domain, parts[2] if len(parts) > 2 and parts[2] else "all"))
    return stores


def _money(v) -> Decimal | None:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01")) if v not in (None, "") else None
    except InvalidOperation:
        return None


class ShopifyConnector(Connector):
    tier = 2
    respect_robots = True
    config_key = "shopify"
    MAX_PAGES = 4

    def __init__(self, store_name: str, domain: str, collection: str, *a, **kw):
        super().__init__(*a, **kw)
        self.store_name, self.domain, self.collection = store_name, domain, collection
        self.code = f"shopify_{slug(store_name).replace('-', '_')}"[:40]
        self.name = store_name
        self.status_note = f"Shopify storefront JSON: https://{domain}/collections/{collection}"

    def _fetch_all(self, res: CheckResult) -> list[ListingSnapshot]:
        snaps: list[ListingSnapshot] = []
        with self.client() as c:
            try:
                for page in range(1, self.MAX_PAGES + 1):
                    url = f"https://{self.domain}/collections/{self.collection}/products.json"
                    r = c.get(url, params={"limit": 250, "page": page})
                    if r.status_code == 404:
                        raise FetchError(f"collection '{self.collection}' not found", status=CheckStatus.NOT_FOUND)
                    if r.status_code != 200:
                        raise FetchError(f"HTTP {r.status_code}", http_status=r.status_code)
                    try:
                        products = r.json().get("products")
                    except (ValueError, AttributeError) as e:
                        raise FetchError("non-JSON storefront response", status=CheckStatus.INCOMPLETE) from e
                    if not isinstance(products, list):
                        raise FetchError("storefront response missing 'products'", status=CheckStatus.INCOMPLETE)
                    for p in products:
                        snaps.extend(self.to_snapshots(p))
                    if len(products) < 250:
                        break
            except FetchError as e:
                res.fatal = CheckFailure(None, e.status, str(e))
            finally:
                res.requests_made = c.requests_made
        return snaps

    def to_snapshots(self, p: dict) -> list[ListingSnapshot]:
        out = []
        images = p.get("images") or []
        img = images[0].get("src") if images and isinstance(images[0], dict) else None
        tags = p.get("tags") or []
        tags_s = " ".join(tags) if isinstance(tags, list) else str(tags)
        is_pre = bool(PREORDER_RE.search(p.get("title", "")) or PREORDER_RE.search(tags_s))
        variants = p.get("variants") or []
        for v in variants:
            avail = v.get("available")
            if avail is True:
                state = StockState.PREORDER if is_pre else StockState.IN_STOCK
            elif avail is False:
                state = StockState.OUT_OF_STOCK
            else:
                state = StockState.UNKNOWN
            vt = v.get("title") or ""
            title = p.get("title", "") + ("" if vt in ("", "Default Title") else f" — {vt}")
            out.append(ListingSnapshot(
                retailer=self.code, retailer_product_id=str(v.get("id")), title=title,
                url=f"https://{self.domain}/products/{p.get('handle')}?variant={v.get('id')}",
                state=state, evidence=f"variant.available={avail} preorder_marker={is_pre}",
                price=_money(v.get("price")), regular_price=_money(v.get("compare_at_price")),
                image_url=img, sku=v.get("sku") or None, upc=v.get("barcode") or None,
                ship_available=(avail is True) if avail is not None else None, pickup_available=None,
                is_marketplace=False, seller_name=self.store_name, category_hint=p.get("product_type"),
            ))
        return out

    def discover(self, queries: list[str]) -> CheckResult:
        res = CheckResult(self.code)
        res.snapshots = self._fetch_all(res)
        return res

    def check(self, product_ids: list[str]) -> CheckResult:
        res = CheckResult(self.code)
        snaps = self._fetch_all(res)
        if res.fatal:
            return res
        wanted = set(product_ids)
        by_id = {s.retailer_product_id: s for s in snaps}
        res.snapshots = [by_id[i] for i in wanted if i in by_id]
        for i in wanted - by_id.keys():
            # absent from the collection != out of stock (could be unpublished/moved)
            res.failures.append(CheckFailure(i, CheckStatus.NOT_FOUND, "variant absent from collection feed"))
        return res
