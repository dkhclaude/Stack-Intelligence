"""Deterministic product classification from retailer titles.

Cheap and fast: runs on every discovered listing. The optional AI classifier
(pokewatch.ai) is consulted only for low-confidence titles.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .domain import Category

# Known set names used for matching only (never as a source of release claims).
# Extend via config/sets.yaml without code changes.
_BUILTIN_SETS = [
    # Mega Evolution era
    "Mega Evolution", "Phantasmal Flames", "Ascended Heroes",
    # Scarlet & Violet era
    "White Flare", "Black Bolt", "Destined Rivals", "Journey Together", "Prismatic Evolutions",
    "Surging Sparks", "Stellar Crown", "Shrouded Fable", "Twilight Masquerade", "Temporal Forces",
    "Paldean Fates", "Paradox Rift", "151", "Obsidian Flames", "Paldea Evolved", "Scarlet & Violet",
    # Sword & Shield era (still sold / restocked)
    "Crown Zenith", "Silver Tempest", "Lost Origin", "Pokemon GO", "Astral Radiance",
    "Brilliant Stars", "Fusion Strike", "Celebrations", "Evolving Skies", "Chilling Reign",
    "Battle Styles", "Shining Fates", "Vivid Voltage", "Champion's Path", "Hidden Fates",
]


def _load_sets() -> list[str]:
    extra: list[str] = []
    p = Path(__file__).resolve().parents[2] / "config" / "sets.yaml"
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        extra = [s for s in data.get("sets", []) if isinstance(s, str)]
    # longest first so "Scarlet & Violet 151" style titles hit "151" not the base set first
    return sorted({*_BUILTIN_SETS, *extra}, key=len, reverse=True)


KNOWN_SETS = _load_sets()


def norm_text(s: str) -> str:
    s = re.sub(r"[\u2010-\u2015\u2212]", " ", s)  # dashes -> space before ascii folding
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"[—–/|:,()\[\]\"!®™+]", " ", s)
    s = s.replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm_text(s)).strip("-")


_SET_PATTERNS = [(name, re.compile(r"\b" + re.escape(norm_text(name)) + r"\b")) for name in KNOWN_SETS]

# Order matters: more specific first.
_CATEGORY_PATTERNS: list[tuple[Category, re.Pattern]] = [
    (Category.ULTRA_PREMIUM_COLLECTION, re.compile(r"\bultra ?premium collection\b|\bupc\b(?! ?\d)")),
    (Category.ELITE_TRAINER_BOX, re.compile(r"\belite trainer box\b|\betb\b")),
    (Category.BOOSTER_BUNDLE, re.compile(r"\bbooster bundle\b|\bbundle of 6\b")),
    (Category.BOOSTER_BOX, re.compile(r"\bbooster (display )?box\b|\bbooster display\b|\b36 (booster )?packs?\b")),
    (Category.SLEEVED_BOOSTER, re.compile(r"\bsleeved booster\b")),
    (Category.BLISTER, re.compile(r"\bblister\b|\b3 (booster )?pack blister\b|\bcheck ?lane\b")),
    (Category.BUILD_AND_BATTLE, re.compile(r"\bbuild (and )?battle\b")),
    (Category.BINDER_COLLECTION, re.compile(r"\bbinder collection\b")),
    (Category.PREMIUM_COLLECTION, re.compile(r"\bpremium (figure |poster )?collection\b")),
    (Category.SPECIAL_COLLECTION, re.compile(r"\bspecial collection\b|\bsuper premium collection\b")),
    (Category.TIN, re.compile(r"\bmini tins?\b|\btins?\b|\bstacking tin\b")),
    (Category.THEME_DECK, re.compile(r"\b(battle|league battle|theme|starter) deck\b|\bex battle deck\b")),
    (Category.COLLECTION_BOX, re.compile(r"\bcollection( box)?\b|\bgift box\b|\bpin collection\b|\bposter collection\b")),
    (Category.BOOSTER_PACK, re.compile(r"\bbooster pack\b|\bbooster\b")),
]

_NEGATIVE = re.compile(
    r"\b(nintendo switch|switch 2|video game|plush|plushie|figure(?! collection)|funko|lego|t ?shirt|hoodie|costume|"
    r"card sleeves|deck box|playmat|play mat|toploader|card case|binder(?! collection)|portfolio|backpack|"
    r"one piece|magic the gathering|yu gi oh|lorcana|topps|digimon|dragon ball|flesh and blood|"
    r"graded|psa \d+|cgc \d+|bgs \d+|single card|proxy|custom|repack|mystery box|lot of)\b"
)
_TCG_HINT = re.compile(r"\b(tcg|trading card|card game)\b")
_PACK_COUNT = re.compile(r"\b(\d{1,2}) ?(?:x ?)?(?:booster )?(?:packs?|pk)\b")
_EXCLUSIVE = [
    ("pokemon_center", re.compile(r"\bpokemon center\b")),
    ("costco", re.compile(r"\bcostco\b")),
    ("sams_club", re.compile(r"\bsam'?s club\b")),
    ("target", re.compile(r"\btarget exclusive\b")),
    ("walmart", re.compile(r"\bwalmart exclusive\b")),
    ("gamestop", re.compile(r"\bgamestop exclusive\b")),
    ("bestbuy", re.compile(r"\bbest buy exclusive\b")),
]
_STOP = set(
    "pokemon tcg trading card cards game the a an of and with for in on english sealed new factory box boxes "
    "collection exclusive edition item pack packs booster bundle elite trainer premium ultra special set series "
    "sv swsh scarlet violet sword shield mega evolution display blister sleeved tin tins mini count pk x "
    "battle deck build league kit gift product ages 6 up etb bundles official brand".split()
)
_KEEP_SUFFIX = {"ex", "vmax", "vstar", "gx", "v"}


@dataclass
class Features:
    title: str
    normalized: str
    category: Category
    set_name: str | None
    pack_count: int | None
    exclusive_to: str | None
    variant_tokens: frozenset[str]
    tcg_confidence: float
    is_tcg: bool
    reasons: list[str] = field(default_factory=list)


def classify(title: str, category_hint: str | None = None) -> Features:
    t = norm_text(title)
    reasons: list[str] = []
    has_pokemon = "pokemon" in t or "pokémon" in title.lower()

    category = Category.OTHER_SEALED
    for cat, pat in _CATEGORY_PATTERNS:
        if pat.search(t):
            category = cat
            reasons.append(f"category:{cat.value}")
            break

    set_name = next((name for name, pat in _SET_PATTERNS if pat.search(t)), None)
    # Avoid "Scarlet & Violet" base-set false positive when a sub-set is named
    if set_name == "Scarlet & Violet":
        for name, pat in _SET_PATTERNS:
            if name != "Scarlet & Violet" and pat.search(t):
                set_name = name
                break
    if category_hint and "pokemon" in norm_text(category_hint):
        has_pokemon = True

    negative = _NEGATIVE.search(t)
    # "sleeved booster" is TCG product, "card sleeves" is an accessory
    if negative and not (negative.group(0) == "card sleeves" and category == Category.SLEEVED_BOOSTER):
        conf = 0.05
        reasons.append(f"negative:{negative.group(0)}")
    elif not has_pokemon and set_name and not set_name.isdigit() and category != Category.OTHER_SEALED:
        conf = 0.75
        reasons.append("known set + product type, brand word missing")
    elif not has_pokemon:
        conf = 0.0
        reasons.append("no 'pokemon' in title")
    elif _TCG_HINT.search(t) or (category_hint and "trading card" in category_hint.lower()):
        conf = 0.95
    elif category != Category.OTHER_SEALED:
        conf = 0.85
    else:
        conf = 0.4
        reasons.append("pokemon but no product-type keywords")

    pack_count = None
    m = _PACK_COUNT.search(t)
    if m:
        pack_count = int(m.group(1))

    exclusive_to = next((code for code, pat in _EXCLUSIVE if pat.search(t)), None)

    set_words = set(norm_text(set_name).split()) if set_name else set()
    tokens = set()
    for tok in t.split():
        if tok in _KEEP_SUFFIX:
            tokens.add(tok)
        elif tok not in _STOP and tok not in set_words and not tok.isdigit() and len(tok) > 1:
            tokens.add(tok)
    # strip words that are part of category/exclusive phrases
    for phrase in ("center", "costco", "club", "sam's", "sams", "target", "walmart", "gamestop", "best", "buy"):
        tokens.discard(phrase)
    if tokens == {"v"}:
        tokens = set()

    return Features(
        title=title, normalized=t, category=category, set_name=set_name, pack_count=pack_count,
        exclusive_to=exclusive_to, variant_tokens=frozenset(tokens), tcg_confidence=conf,
        is_tcg=conf >= 0.6, reasons=reasons,
    )
