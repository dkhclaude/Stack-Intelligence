"""Optional Claude-assisted classification for *ambiguous* listing titles.

Called only when the deterministic classifier is unsure (confidence inside the
configured band) and ANTHROPIC_API_KEY is set. Results are cached per title, so
each distinct title costs at most one API call ever. Never used for stock
state, prices, or anything on the inventory hot path.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import Settings
from .db.models import AIClassificationCache
from .domain import Category

log = logging.getLogger(__name__)

CategoryName = Literal[tuple(c.value for c in Category)]  # type: ignore[valid-type]
FALLBACK_CAPABLE = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5-2")

SYSTEM = (
    "You classify retail product listings for a Pokémon Trading Card Game sealed-product stock tracker. "
    "is_pokemon_tcg_sealed is true only for sealed Pokémon TCG card products (booster packs/boxes/bundles, "
    "Elite Trainer Boxes, collections, tins, blisters, decks). It is false for video games, plush, figures, "
    "accessories (sleeves, binders sold alone, deck boxes), graded or single cards, repacks/mystery boxes and "
    "other card games. Use null for set_name or pack_count when the title does not state them; do not guess."
)


class AIClassification(BaseModel):
    is_pokemon_tcg_sealed: bool
    category: CategoryName
    set_name: str | None = None
    pack_count: int | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str


def _key(title: str) -> str:
    return hashlib.sha256(title.strip().lower().encode()).hexdigest()


class AIClassifier:
    def __init__(self, settings: Settings, max_calls: int = 10, client=None):
        self.settings = settings
        self.remaining = max_calls
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key or self._client)

    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key, max_retries=2, timeout=60)
        return self._client

    def classify(self, session: Session, title: str, category_hint: str | None = None) -> AIClassification | None:
        key = _key(title)
        cached = session.get(AIClassificationCache, key)
        if cached:
            return AIClassification.model_validate(cached.result)
        if not self.available or self.remaining <= 0:
            return None
        self.remaining -= 1
        model = self.settings.ai_model
        kwargs = {}
        if model in FALLBACK_CAPABLE:
            # server-side refusal fallback (opt-in; "default" routes by refusal category)
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            import anthropic
            resp = self.client().beta.messages.parse(
                model=model,
                max_tokens=1024,
                system=SYSTEM,
                output_config={"effort": "low"},
                output_format=AIClassification,
                messages=[{"role": "user", "content": f"Title: {title}\nRetailer category: {category_hint or 'n/a'}"}],
                **kwargs,
            )
        except anthropic.RateLimitError:
            log.warning("AI classifier rate limited; using deterministic result")
            return None
        except anthropic.APIStatusError as e:
            log.warning("AI classifier API error", extra={"status": e.status_code})
            return None
        except anthropic.APIConnectionError:
            log.warning("AI classifier unreachable")
            return None
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            return None
        result = resp.parsed_output
        session.add(AIClassificationCache(title_hash=key, title=title[:2000], result=result.model_dump()))
        session.flush()
        return result
