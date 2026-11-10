"""Official Pokémon TCG *card set* release dates via the Pokémon TCG API (pokemontcg.io).

Only expansions that the API already lists are returned (status=confirmed,
date_confidence=announced). Sealed-product dates and rumours come from the
curated config/releases.yaml file instead, each with its own source link.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from ..domain import ReleaseInfo
from ..http import FetchError, PoliteClient
from .base import ReleaseSource

API = "https://api.pokemontcg.io/v2/sets"


def _parse_date(v) -> date | None:
    if not v:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            continue
    return None


class PokemonTCGIOSource(ReleaseSource):
    code = "pokemontcg_io"
    name = "Pokémon TCG API (sets)"

    def fetch(self) -> list[ReleaseInfo]:
        headers = {"X-Api-Key": self.settings.pokemontcg_api_key} if self.settings.pokemontcg_api_key else None
        with PoliteClient(self.code, self.settings.user_agent, 10, self.settings.http_timeout_s,
                          respect_robots=False, transport=self.transport, sleep=self.sleep) as c:
            r = c.get(API, params={"orderBy": "-releaseDate", "pageSize": 40}, headers=headers)
            if r.status_code != 200:
                raise FetchError(f"pokemontcg.io HTTP {r.status_code}", http_status=r.status_code)
            data = r.json().get("data")
            if not isinstance(data, list):
                raise FetchError("pokemontcg.io response missing 'data'")
        out = []
        for s in data:
            out.append(ReleaseInfo(
                source_name=self.code, external_id=str(s.get("id")), name=s.get("name", "?"),
                release_date=_parse_date(s.get("releaseDate")), date_confidence="announced", status="confirmed",
                source_url=f"{API}/{s.get('id')}", series=s.get("series"), product_type="Expansion set",
                image_url=(s.get("images") or {}).get("logo"),
            ))
        return out


class CuratedReleaseSource(ReleaseSource):
    """User-maintained config/releases.yaml (sealed products, announcements, rumours)."""

    code = "curated"
    name = "Curated releases (config/releases.yaml)"

    def __init__(self, *a, path: Path | None = None, **kw):
        super().__init__(*a, **kw)
        self.path = path or Path(__file__).resolve().parents[3] / "config" / "releases.yaml"

    def fetch(self) -> list[ReleaseInfo]:
        if not self.path.exists():
            return []
        data = yaml.safe_load(self.path.read_text()) or {}
        out = []
        for i, r in enumerate(data.get("releases") or []):
            if not isinstance(r, dict) or not r.get("name"):
                continue
            status = r.get("status", "rumored")
            if status == "confirmed" and not r.get("source_url"):
                status = "rumored"  # no source, no confirmation
            out.append(ReleaseInfo(
                source_name=self.code, external_id=str(r.get("id") or f"{r['name']}"),
                name=r["name"], release_date=_parse_date(r.get("release_date")),
                date_confidence=r.get("date_confidence", "unconfirmed"), status=status,
                source_url=r.get("source_url"), series=r.get("series"), product_type=r.get("product_type"),
                notes=r.get("notes"),
            ))
        return out
