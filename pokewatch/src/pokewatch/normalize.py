"""Cross-retailer product matching -> canonical product catalog.

Conservative by design: a wrong merge (e.g. Pokémon Center ETB vs regular ETB)
is worse than a missed one, so hard conflicts veto a match outright.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .classify import Features, classify, slug
from .db.models import Product, RetailerListing
from .domain import Category


def normalize_gtin(upc: str | None) -> str | None:
    if not upc:
        return None
    digits = re.sub(r"\D", "", upc)
    if len(digits) not in (8, 12, 13, 14):
        return None
    return digits.zfill(14)


@dataclass
class MatchResult:
    score: float
    method: str
    veto: str | None = None


def score_match(a: Features, a_upc: str | None, b: Features, b_upc: str | None,
                a_release: date | None = None, b_release: date | None = None) -> MatchResult:
    ga, gb = normalize_gtin(a_upc), normalize_gtin(b_upc)
    if ga and gb:
        return MatchResult(0.99, "upc") if ga == gb else MatchResult(0.0, "upc", veto="different UPC")

    if a.category != b.category:
        return MatchResult(0.0, "features", veto="category differs")
    if a.pack_count and b.pack_count and a.pack_count != b.pack_count:
        return MatchResult(0.0, "features", veto="pack count differs")
    if a.exclusive_to != b.exclusive_to:
        return MatchResult(0.0, "features", veto="exclusivity differs")
    if a.set_name and b.set_name and a.set_name != b.set_name:
        return MatchResult(0.0, "features", veto="set differs")
    if a_release and b_release and abs((a_release - b_release).days) > 60:
        return MatchResult(0.0, "features", veto="release date differs")

    ta, tb = a.variant_tokens, b.variant_tokens
    jacc = 1.0 if not ta and not tb else len(ta & tb) / max(1, len(ta | tb))
    if (ta or tb) and jacc < 0.5:
        return MatchResult(min(0.5, 0.3 + 0.4 * jacc), "features", veto="variant differs")

    score = 0.5
    if a.set_name and b.set_name:
        score += 0.3
    elif not a.set_name and not b.set_name:
        score += 0.1
    score += 0.2 * jacc
    if a.category == Category.OTHER_SEALED:
        score -= 0.15  # too generic to trust
    return MatchResult(round(min(score, 0.98), 3), "features")


def canonical_key(f: Features, upc: str | None) -> str:
    g = normalize_gtin(upc)
    if g:
        return f"upc:{g}"
    if not f.set_name:
        # unknown set: never let two vague titles share a key
        return f"title:{slug(f.title)[:250]}"
    parts = [slug(f.set_name), slug(f.category.value), str(f.pack_count or ""), f.exclusive_to or "",
             "-".join(sorted(f.variant_tokens))]
    return "set:" + "|".join(parts)


def _features_of(p: Product) -> Features:
    f = classify(p.name)
    # stored fields win over re-derived ones
    f.category = Category(p.category) if p.category in Category._value2member_map_ else f.category
    f.set_name = p.set_name
    f.pack_count = p.pack_count
    f.exclusive_to = p.exclusive_to
    f.variant_tokens = frozenset((p.variant_tokens or "").split()) if p.variant_tokens is not None else f.variant_tokens
    return f


def link_listing(session: Session, listing: RetailerListing, auto_threshold: float = 0.85,
                 review_threshold: float = 0.6) -> Product | None:
    """Attach a listing to a canonical product, creating one if needed."""
    f = classify(listing.title)
    if not f.is_tcg:
        return None
    gtin = normalize_gtin(listing.upc)

    product = None
    method, conf = None, None
    if gtin:
        product = session.scalar(select(Product).where(Product.upc == gtin))
        if product:
            method, conf = "upc", 0.99
    if product is None:
        key = canonical_key(f, listing.upc)
        product = session.scalar(select(Product).where(Product.canonical_key == key))
        if product:
            method, conf = "canonical_key", 0.95 if gtin is None else 0.9
            if gtin and product.upc and product.upc != gtin:
                product = None  # same features, different UPC -> separate SKU
    if product is None:
        best, best_score = None, 0.0
        candidates = session.scalars(select(Product).where(Product.category == f.category.value)).all()
        for cand in candidates:
            r = score_match(f, listing.upc, _features_of(cand), cand.upc, listing.release_date, cand.release_date)
            if r.veto is None and r.score > best_score:
                best, best_score = cand, r.score
        if best is not None and best_score >= review_threshold:
            product, method, conf = best, "fuzzy", best_score
            if best_score < auto_threshold:
                product.needs_review = True
            if gtin and not product.upc:
                product.upc = gtin

    if product is None:
        product = Product(
            canonical_key=canonical_key(f, listing.upc), name=listing.title, set_name=f.set_name,
            category=f.category.value, pack_count=f.pack_count, exclusive_to=f.exclusive_to,
            variant_tokens=" ".join(sorted(f.variant_tokens)), upc=gtin, release_date=listing.release_date,
            image_url=listing.image_url, priority=listing.priority,
        )
        session.add(product)
        session.flush()
        method, conf = "new", 1.0
    else:
        product.image_url = product.image_url or listing.image_url
        product.release_date = product.release_date or listing.release_date

    listing.product_id = product.id
    listing.match_method, listing.match_confidence = method, conf
    return product
