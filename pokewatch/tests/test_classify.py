import pytest

from pokewatch.classify import classify
from pokewatch.domain import Category


@pytest.mark.parametrize("title,cat,set_name,packs", [
    ("Pokémon - Trading Card Game: Scarlet & Violet Prismatic Evolutions Elite Trainer Box", Category.ELITE_TRAINER_BOX, "Prismatic Evolutions", None),
    ("Pokemon Scarlet & Violet 151 Booster Bundle (6 Packs)", Category.BOOSTER_BUNDLE, "151", 6),
    ("Pokémon TCG: Mega Evolution—Phantasmal Flames Booster Display Box (36 Packs)", Category.BOOSTER_BOX, "Phantasmal Flames", 36),
    ("Pokemon TCG Surging Sparks Sleeved Booster Pack", Category.SLEEVED_BOOSTER, "Surging Sparks", None),
    ("Pokémon TCG: Charizard ex Ultra-Premium Collection", Category.ULTRA_PREMIUM_COLLECTION, None, None),
    ("Pokémon TCG: Pikachu ex Premium Collection", Category.PREMIUM_COLLECTION, None, None),
    ("Pokemon TCG Destined Rivals 3-Pack Blister", Category.BLISTER, "Destined Rivals", 3),
    ("Pokemon TCG Journey Together Build & Battle Box", Category.BUILD_AND_BATTLE, "Journey Together", None),
])
def test_categories(title, cat, set_name, packs):
    f = classify(title)
    assert f.category == cat
    assert f.set_name == set_name
    assert f.pack_count == packs
    assert f.is_tcg


@pytest.mark.parametrize("title", [
    "Pokémon Scarlet - Nintendo Switch",
    "Ultra PRO Pokemon Card Sleeves 65ct",
    "Pokemon Pikachu Plush 8 inch",
    "One Piece Card Game Booster Box OP-09",
    "Pokemon Charizard PSA 10 graded card",
    "Magic: The Gathering Booster Box",
])
def test_non_tcg_rejected(title):
    assert not classify(title).is_tcg


def test_exclusive_detection():
    assert classify("Prismatic Evolutions Pokemon Center Elite Trainer Box").exclusive_to == "pokemon_center"
    assert classify("Prismatic Evolutions Elite Trainer Box").exclusive_to is None


def test_variant_tokens_distinguish_collections():
    a = classify("Pokémon TCG: Charizard ex Premium Collection").variant_tokens
    b = classify("Pokémon TCG: Pikachu ex Premium Collection").variant_tokens
    assert "charizard" in a and "pikachu" in b and a != b
