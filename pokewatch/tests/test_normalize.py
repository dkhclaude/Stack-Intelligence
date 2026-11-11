from sqlalchemy import select

from pokewatch.classify import classify
from pokewatch.db.models import Product, RetailerConnector, RetailerListing
from pokewatch.db.session import session_scope
from pokewatch.normalize import link_listing, normalize_gtin, score_match


def sm(a, b, ua=None, ub=None):
    return score_match(classify(a), ua, classify(b), ub)


def test_same_product_different_titles_match():
    r = sm("Pokémon - Trading Card Game: Scarlet & Violet Prismatic Evolutions Elite Trainer Box",
           "Pokemon TCG Prismatic Evolutions ETB")
    assert r.veto is None and r.score >= 0.85


def test_pokemon_center_etb_not_merged_with_regular():
    r = sm("Prismatic Evolutions Pokemon Center Elite Trainer Box", "Prismatic Evolutions Elite Trainer Box")
    assert r.veto == "exclusivity differs" and r.score == 0


def test_bundle_vs_box_not_merged():
    assert sm("151 Booster Bundle", "151 Booster Box").veto == "category differs"


def test_pack_count_conflict():
    assert sm("Pokemon Surging Sparks Booster Box 36 packs", "Pokemon Surging Sparks Booster Box 18 packs").veto == "pack count differs"


def test_different_featured_pokemon_not_merged():
    r = sm("Pokémon TCG: Charizard ex Premium Collection", "Pokémon TCG: Pikachu ex Premium Collection")
    assert r.veto == "variant differs" and r.score < 0.6


def test_upc_wins_and_conflicting_upc_vetoes():
    assert sm("anything ETB", "different words ETB", "820650859571", "0820650859571").score == 0.99
    assert sm("Prismatic Evolutions ETB", "Prismatic Evolutions ETB", "820650859571", "820650859572").veto == "different UPC"


def test_gtin_normalization():
    assert normalize_gtin("820650859571") == normalize_gtin("00820650859571")
    assert normalize_gtin("abc") is None


def _listing(s, retailer, pid, title, upc=None):
    if s.get(RetailerConnector, retailer) is None:
        s.add(RetailerConnector(code=retailer, name=retailer, support_level="supported"))
        s.flush()
    l = RetailerListing(retailer=retailer, connector=retailer, retailer_product_id=pid, title=title, url="https://x", upc=upc)
    s.add(l)
    s.flush()
    return l


def test_link_listing_builds_catalog(db):
    with session_scope() as s:
        a = _listing(s, "bestbuy", "1", "Pokémon - Trading Card Game: Prismatic Evolutions Elite Trainer Box", "820650859571")
        b = _listing(s, "shop", "2", "Pokemon TCG Prismatic Evolutions ETB")
        c = _listing(s, "shop", "3", "Pokemon TCG Prismatic Evolutions Pokemon Center Elite Trainer Box")
        d = _listing(s, "shop2", "4", "Prismatic Evolutions Elite Trainer Box", "820650859571")
        pa, pb, pc, pd = (link_listing(s, x) for x in (a, b, c, d))
        assert pa.id == pb.id == pd.id
        assert pc.id != pa.id
        assert d.match_method == "upc"
        assert len(s.scalars(select(Product)).all()) == 2
