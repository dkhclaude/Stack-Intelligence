# Phase 1 — Retailer Feasibility Matrix

**Status legend:** ✅ implemented against an official/permitted source · 🔑 implemented, needs your credential ·
📝 needs partner/affiliate approval · 🚫 no permitted automated access (connector registered as *unsupported*)

> **Honesty note.** All connectors were built and tested against **mocked** responses that follow each
> source's documented response format. The development sandbox could not reach any retailer host, so **no
> connector has been verified live yet**. Run `pokewatch verify <connector>` on your own machine or server. Only a
> successful real response marks a connector "LIVE-VERIFIED" in the dashboard.

| Retailer | Tier | Status | Method | Gives us | Limitations | Alternative |
|---|---|---|---|---|---|---|
| **Best Buy** | P1 | 🔑 → ✅ | Official **Products API** (`api.bestbuy.com/v1/products`) | Search + batch lookup by SKU (100/call), `orderable` (Available / PreOrder / ComingSoon / SoldOut), `onlineAvailability`, `inStoreAvailability`, sale/regular price, UPC, release date, images; per-store pickup by ZIP via `/products/{sku}/stores.json` | Free key required. Best Buy has said it **won't issue keys to free email domains (Gmail/Yahoo)**. That policy dates from about 2016 and I couldn't confirm it's still enforced. Catalog availability can lag the website by minutes. Rate-limited (per-second + daily quota). Field names are from the docs and not yet live-verified | If no key: Best Buy's own app alerts |
| **Walmart** | P1 | 📝 | **Walmart Affiliate API** (walmart.io) | Product lookup/search, stock flag, seller info (1P vs marketplace), UPC, price | Requires affiliate approval and RSA-signed request headers. Most Pokémon listings are third-party marketplace sellers. Not implemented until approved | Walmart app "notify me" |
| **Target** | P1 | 🚫 | — | — | No public product or inventory API. The internal "redsky" endpoints are undocumented, not licensed for third-party use, and behind bot protection | Target app alerts; Target Circle notifications |
| **Costco** | P1 | 🚫 | — | — | No public API. Akamai bot management; terms prohibit automated access. Pokémon bundles are typically online-only member drops | Costco email / app notifications |
| **GameStop** | P2 | 📝 | Affiliate product feed (via its affiliate network) | Catalog + price feed (availability granularity varies) | Needs affiliate approval; storefront is bot-protected | GameStop app / PowerUp alerts |
| **Pokémon Center** | P2 | 🚫 | — | — | No public API. Imperva bot protection and a **virtual queue**, which PokéWatch will not circumvent | Official Pokémon Center email / app notifications |
| **Sam's Club** | P2 | 🚫 | — | — | No public API; Walmart-family bot protection | Sam's Club app |
| **Local / hobby stores (Shopify)** | P2 | ✅ | Public storefront JSON (`/collections/<handle>/products.json`), **robots.txt enforced** | Per-variant `available`, price, compare-at price, images, preorder tags | Only stores whose robots.txt allows it; collection must be public; preorder detection relies on titles and tags | — |
| **Release dates (cards)** | — | ✅ | **Pokémon TCG API** (`api.pokemontcg.io/v2/sets`) | Official expansion names and release dates | Card *sets* only, not sealed SKUs. The project is migrating to Scrydex (paid), so the free endpoint's long-term future is uncertain | `config/releases.yaml` (curated; "confirmed" requires a source URL) |

## What this means in practice

* **Realistically automatable today:** Best Buy (with key), Shopify hobby stores, and official set release dates.
* **Possible with approval:** Walmart (affiliate API) and GameStop (affiliate feed). Both are planned for Phase 3 once approved.
* **Not automatable within the rules:** Target, Costco, Pokémon Center, and Sam's Club. They appear in the dashboard as
  *Unsupported* with the reason. PokéWatch never bypasses CAPTCHAs, queues, logins, or bot walls. A blocked response is
  recorded as **UNKNOWN**, never as out of stock, and opens the connector's circuit breaker.

## Recommended first connector: Best Buy

It's the only Priority-1 retailer with an official, documented availability API. It gives explicit preorder and
coming-soon states and UPCs, which make cross-retailer matching reliable. One batched call checks up to 100 SKUs, so
5-minute priority checks fit easily within the quota.

**If Best Buy declines a Gmail-based key**, start with reputable Shopify hobby stores (no key needed), using
`pokewatch check-store <url> --add` to vet each one. To get a Best Buy key later, an address on your own domain
works: a domain costs about $10/year, and free email forwarding (for example Cloudflare Email Routing) delivers
its mail to your existing inbox.
