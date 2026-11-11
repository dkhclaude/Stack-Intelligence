"""All retailer connectors, including ones that are deliberately unsupported."""

from __future__ import annotations

from ..config import Settings
from ..domain import SupportLevel
from .base import Connector, ReleaseSource, UnsupportedConnector
from .bestbuy import BestBuyConnector
from .pokemontcg_io import CuratedReleaseSource, PokemonTCGIOSource
from .shopify import ShopifyConnector, parse_store_config


def _unsupported(code: str, name: str, tier: int, level: SupportLevel, note: str) -> type[UnsupportedConnector]:
    return type(f"{code.title()}Connector", (UnsupportedConnector,),
                {"code": code, "name": name, "tier": tier, "support_level": level, "status_note": note})


UNSUPPORTED = [
    _unsupported("target", "Target", 1, SupportLevel.UNSUPPORTED,
                 "No public product/inventory API. Target's internal 'redsky' endpoints are undocumented and "
                 "not licensed for third-party use; site uses bot protection. Use the Target app's own alerts."),
    _unsupported("walmart", "Walmart", 1, SupportLevel.NEEDS_APPROVAL,
                 "Walmart Affiliate (Walmart.io) API provides product lookup with stock & seller fields but "
                 "requires affiliate approval and RSA-signed requests. Planned Phase 3 once approved."),
    _unsupported("costco", "Costco", 1, SupportLevel.UNSUPPORTED,
                 "No public API; site protected by Akamai bot management and its terms prohibit automated "
                 "access. Most Pokémon bundles are members-only/online drops. Use Costco email/app alerts."),
    _unsupported("gamestop", "GameStop", 2, SupportLevel.NEEDS_APPROVAL,
                 "No public API; storefront is bot-protected. A product feed may be available through "
                 "GameStop's affiliate program (requires approval)."),
    _unsupported("pokemon_center", "Pokémon Center", 2, SupportLevel.UNSUPPORTED,
                 "No public API; uses a virtual queue and Imperva bot protection, which PokéWatch will not "
                 "circumvent. Use official Pokémon Center email/app notifications."),
    _unsupported("sams_club", "Sam's Club", 2, SupportLevel.UNSUPPORTED,
                 "No public API; same bot protection as Walmart properties. Use Sam's Club app alerts."),
]


def build_connectors(settings: Settings, runtime: dict, transport=None, sleep=None) -> list[Connector]:
    kw = {"transport": transport}
    if sleep is not None:
        kw["sleep"] = sleep
    conns: list[Connector] = [BestBuyConnector(settings, runtime, **kw)]
    for name, domain, coll in parse_store_config(settings.shopify_stores):
        conns.append(ShopifyConnector(name, domain, coll, settings, runtime, **kw))
    conns.extend(cls(settings, runtime) for cls in UNSUPPORTED)
    return conns


def build_release_sources(settings: Settings, runtime: dict, transport=None, sleep=None) -> list[ReleaseSource]:
    kw = {"transport": transport}
    if sleep is not None:
        kw["sleep"] = sleep
    return [PokemonTCGIOSource(settings, runtime, **kw), CuratedReleaseSource(settings, runtime, **kw)]
