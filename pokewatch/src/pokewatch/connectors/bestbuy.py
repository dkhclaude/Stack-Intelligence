"""Best Buy — official Products API (developer.bestbuy.com).

Requires BESTBUY_API_KEY. Documented limits: ~5 req/s and a daily quota per key.
Availability fields come straight from Best Buy's catalog API; they may lag the
website by a few minutes, which is documented in docs/FEASIBILITY.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from ..domain import CheckFailure, CheckResult, CheckStatus, ListingSnapshot, StockState, SupportLevel
from ..http import FetchError
from .base import Connector

API = "https://api.bestbuy.com/v1"
SHOW = ",".join([
    "sku", "name", "upc", "salePrice", "regularPrice", "onlineAvailability", "onlineAvailabilityUpdateDate",
    "inStoreAvailability", "inStoreAvailabilityUpdateDate", "orderable", "releaseDate", "image",
    "largeFrontImage", "url", "marketplace", "sellerName", "preowned", "categoryPath.name", "manufacturer",
])


def _money(v) -> Decimal | None:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01")) if v not in (None, "") else None
    except InvalidOperation:
        return None


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def map_state(p: dict) -> tuple[StockState, bool | None, bool | None, str]:
    """Return (state, ship_available, pickup_available, evidence) from Best Buy fields."""
    orderable = p.get("orderable")
    online = p.get("onlineAvailability")
    instore = p.get("inStoreAvailability")
    ev = f"orderable={orderable} onlineAvailability={online} inStoreAvailability={instore}"
    if orderable == "PreOrder":
        return StockState.PREORDER, bool(online) if online is not None else None, False, ev
    if orderable == "ComingSoon":
        return StockState.COMING_SOON, False, False, ev
    if online is True:
        return StockState.IN_STOCK, True, bool(instore) if instore is not None else None, ev
    if instore is True:
        # some stores have it; not shippable
        return StockState.IN_STOCK, False, True, ev
    if online is False and instore is False:
        return StockState.OUT_OF_STOCK, False, False, ev
    if orderable == "SoldOut":
        return StockState.OUT_OF_STOCK, False, None, ev
    return StockState.UNKNOWN, None, None, ev + " (insufficient fields)"


def to_snapshot(p: dict) -> ListingSnapshot:
    sku = str(p.get("sku"))
    state, ship, pickup, ev = map_state(p)
    cats = p.get("categoryPath") or []
    is_mkt = bool(p.get("marketplace")) if p.get("marketplace") is not None else False
    return ListingSnapshot(
        retailer="bestbuy",
        retailer_product_id=sku,
        title=p.get("name") or f"Best Buy SKU {sku}",
        url=f"https://www.bestbuy.com/site/{sku}.p?skuId={sku}",
        state=state,
        evidence=ev,
        price=_money(p.get("salePrice")),
        regular_price=_money(p.get("regularPrice")),
        image_url=p.get("largeFrontImage") or p.get("image"),
        upc=p.get("upc"),
        sku=sku,
        ship_available=ship,
        pickup_available=pickup,
        is_marketplace=is_mkt,
        seller_name=p.get("sellerName") or ("Best Buy" if not is_mkt else None),
        release_date=_date(p.get("releaseDate")),
        category_hint=" > ".join(c.get("name", "") for c in cats if isinstance(c, dict)) or None,
    )


class BestBuyConnector(Connector):
    code = "bestbuy"
    name = "Best Buy"
    tier = 1
    respect_robots = False  # official API
    status_note = "Official Products API (developer.bestbuy.com)."

    MAX_PAGES = 3
    BATCH = 100

    def configured(self):
        if not self.settings.bestbuy_api_key:
            return False, "Set BESTBUY_API_KEY (free key from developer.bestbuy.com)."
        return True, "ok"

    @property
    def support_level(self) -> SupportLevel:  # type: ignore[override]
        return SupportLevel.SUPPORTED if self.settings.bestbuy_api_key else SupportLevel.NEEDS_CREDENTIALS

    def _query(self, client, filter_expr: str, page: int = 1) -> dict:
        url = f"{API}/products({filter_expr})"
        params = {"apiKey": self.settings.bestbuy_api_key, "format": "json", "show": SHOW,
                  "pageSize": self.BATCH, "page": page}
        r = client.get(url, params=params)
        if r.status_code in (401, 403):
            msg = r.text[:300]
            status = CheckStatus.RATE_LIMITED if ("limit" in msg.lower() or "quota" in msg.lower()) else CheckStatus.NOT_CONFIGURED
            raise FetchError(f"Best Buy API HTTP {r.status_code}: {msg}", status=status, http_status=r.status_code)
        if r.status_code == 400:
            raise FetchError(f"Best Buy API rejected query: {r.text[:300]}", status=CheckStatus.ERROR, http_status=400)
        if r.status_code != 200:
            raise FetchError(f"Best Buy API HTTP {r.status_code}", http_status=r.status_code)
        try:
            data = r.json()
        except ValueError as e:
            raise FetchError("Best Buy API returned non-JSON", status=CheckStatus.INCOMPLETE) from e
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise FetchError("Best Buy API response missing 'products'", status=CheckStatus.INCOMPLETE)
        return data

    @staticmethod
    def search_expr(query: str) -> str:
        words = [w for w in query.replace("é", "e").split() if w.isalnum()]
        return "&".join(f"search={w}" for w in words)

    def discover(self, queries: list[str]) -> CheckResult:
        res = CheckResult(self.code)
        ok, why = self.configured()
        if not ok:
            res.fatal = CheckFailure(None, CheckStatus.NOT_CONFIGURED, why)
            return res
        seen: set[str] = set()
        with self.client() as c:
            try:
                for q in queries:
                    page, total_pages = 1, 1
                    while page <= min(total_pages, self.MAX_PAGES):
                        data = self._query(c, self.search_expr(q), page)
                        total_pages = int(data.get("totalPages") or 1)
                        for p in data["products"]:
                            if str(p.get("sku")) in seen:
                                continue
                            seen.add(str(p.get("sku")))
                            res.snapshots.append(to_snapshot(p))
                        page += 1
            except FetchError as e:
                res.fatal = CheckFailure(None, e.status, str(e))
            finally:
                res.requests_made = c.requests_made
        return res

    def check(self, product_ids: list[str]) -> CheckResult:
        res = CheckResult(self.code)
        ok, why = self.configured()
        if not ok:
            res.fatal = CheckFailure(None, CheckStatus.NOT_CONFIGURED, why)
            return res
        ids = [i for i in product_ids if i.isdigit()]
        for bad in set(product_ids) - set(ids):
            res.failures.append(CheckFailure(bad, CheckStatus.ERROR, "invalid Best Buy SKU"))
        with self.client() as c:
            try:
                for i in range(0, len(ids), self.BATCH):
                    batch = ids[i:i + self.BATCH]
                    data = self._query(c, f"sku in({','.join(batch)})")
                    got = {str(p.get("sku")): p for p in data["products"]}
                    for sku in batch:
                        if sku in got:
                            res.snapshots.append(to_snapshot(got[sku]))
                        else:
                            res.failures.append(CheckFailure(sku, CheckStatus.NOT_FOUND, "SKU absent from API response"))
                    self._local_pickup(c, [s for s in res.snapshots if s.retailer_product_id in got])
            except FetchError as e:
                res.fatal = CheckFailure(None, e.status, str(e))
            finally:
                res.requests_made = c.requests_made
        return res

    def _local_pickup(self, c, snaps: list[ListingSnapshot]) -> None:
        """Optional: per-store pickup near LOCAL_ZIP for items showing store availability."""
        zip_code = self.settings.local_zip or (self.runtime.get("local_store") or {}).get("zip")
        if not zip_code or not self.conf.get("local_pickup_check", False):
            return
        for s in snaps:
            if s.state != StockState.IN_STOCK or not s.pickup_available:
                continue
            try:
                r = c.get(f"{API}/products/{s.retailer_product_id}/stores.json",
                          params={"postalCode": zip_code, "apiKey": self.settings.bestbuy_api_key})
                if r.status_code == 200:
                    stores = (r.json() or {}).get("stores") or []
                    s.pickup_available = len(stores) > 0
                    s.evidence += f" localStores({zip_code})={len(stores)}"
            except (FetchError, ValueError):
                s.evidence += " localStores=unknown"
