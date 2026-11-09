"""Verification tests (Literature Review, Table 12, level 1: 'calculation engine').

Each test recomputes a value that was published, or checks a rule of the method, from the data files.
Run:  python -m pytest -q
"""
import math

import pytest

import orcarbon as oc
import orcarbon.data


@pytest.fixture(scope="module")
def db():
    return oc.load()


# ---- reproduce published values -------------------------------------------------------------
def test_method_a_reproduces_rizan_per_item_values(db):
    # Rizan et al.: 26 g per nitrile glove, 20 g per Type IIR mask, 905 g per single-use gown
    assert oc.product_lca(db, "GLOVE_NITRILE").g_co2e == pytest.approx(26)
    assert oc.product_lca(db, "MASK_IIR").g_co2e == pytest.approx(20)
    assert oc.product_lca(db, "GOWN_SURGICAL").g_co2e == pytest.approx(905)


def test_method_b_reproduces_waters_drapes_total(db):
    # Waters et al.: 93.9 kg of polypropylene drapes in 159 operations = 292 kg CO2e (production only)
    r = oc.material_based(db, "DRAPES_GYN_CASE", quantity=159, include_disposal=False)
    assert r.kg_co2e == pytest.approx(292, rel=0.005)   # 291.5 kg: within 0.5%


def test_waters_implied_factor_matches_uk_pp_factor(db):
    implied = 292 / 93.9                                 # Literature Review, worked example 3
    assert implied == pytest.approx(db.material_factor["polypropylene"]["value"], rel=0.005)


def test_gas_desflurane_bottle(db):
    # 240 mL x 1.465 g/mL = 351.6 g;  x GWP100 2590 = 910.6 kg CO2e
    r = oc.anaesthetic_gas(db, "desflurane", bottles=1)
    assert r.kg_co2e == pytest.approx(0.3516 * 2590)


def test_gas_literature_review_worked_example_4(db):
    # 20 g of desflurane: 0.02 x ~2,500 = ~50 kg CO2e (Literature Review uses the rounded GWP)
    assert oc.anaesthetic_gas(db, "desflurane", grams=20).kg_co2e == pytest.approx(51.8)


# ---- rules of the methods -------------------------------------------------------------------
def test_material_based_is_lower_bound_of_full_lca(db):
    # Method B leaves out manufacturing energy, transport and packaging, so it must be below Method A
    for p in ["GLOVE_NITRILE", "MASK_IIR", "GOWN_SURGICAL"]:
        assert oc.material_based(db, p).kg_co2e < oc.product_lca(db, p).kg_co2e


def test_coverage_reports_missing_material(db):
    r = oc.material_based(db, "MASK_IIR")                # 0.2 g aluminium has no factor
    assert r.coverage == pytest.approx(2.9 / 3.1)
    assert any("aluminium" in w for w in r.warnings)


def test_spend_based_currency_and_year_conversion(db):
    r = oc.spend_based(db, "GLOVE_NITRILE")
    usd2022 = 0.231 / 1.3497 * 292.655 / 304.702
    assert r.kg_co2e == pytest.approx(usd2022 * 0.14)


def test_spend_based_accepts_a_local_price(db):
    # e.g. a future Soroka purchase price in USD of 2022
    assert oc.spend_based(db, "GLOVE_NITRILE", price=0.10, currency="USD", price_year=2022).kg_co2e == pytest.approx(0.014)


def test_quantity_scales_linearly(db):
    for f in (oc.product_lca, oc.material_based, oc.spend_based):
        one, ten = f(db, "GOWN_SURGICAL", 1).kg_co2e, f(db, "GOWN_SURGICAL", 10).kg_co2e
        assert ten == pytest.approx(10 * one)


def test_hybrid_follows_tier_order(db):
    assert oc.hybrid(db, "GLOVE_NITRILE").method == "A"     # published LCA exists
    assert oc.hybrid(db, "DRAPES_GYN_CASE").method == "B"   # no LCA, falls back to material


def test_case_unused_items(db):
    res = oc.case_footprint(db, [("GLOVE_NITRILE", 10, 4)], gas=("sevoflurane", 10))
    assert res["unused_kg"] == pytest.approx(4 * 0.026)
    assert res["gas_kg"] == pytest.approx(0.010 * 195)
    assert res["total_kg"] == pytest.approx(10 * 0.026 + 1.95)


def test_unused_cannot_exceed_opened(db):
    with pytest.raises(ValueError):
        oc.case_footprint(db, [("GLOVE_NITRILE", 2, 3)])


def test_every_number_has_a_source(db):
    for f in db.factors.values():
        assert f["source_id"] in db.sources
    assert all(not math.isnan(f["value"]) for f in db.factors.values())


def test_tier1_product_data_is_labelled_and_preferred(tmp_path):
    # A manufacturer/MedZero value for the exact product (tier 1) is used first by the hybrid choice.
    import shutil
    for f in oc.data.DATA_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    with open(tmp_path / "product_lca.csv", "a", encoding="utf-8") as f:
        f.write("DRAPES_GYN_CASE,1,1.5,example,no,WATERS_DRAPES\n")
    db1 = oc.load(tmp_path)
    r = oc.hybrid(db1, "DRAPES_GYN_CASE")
    assert r.method == "A" and r.tier.startswith("Tier 1")


# ---- tier shares (Section 7.1) and sensitivity analysis (Table 12, level 4) -----------------
CASE = [("GLOVE_NITRILE", 20, 4), ("MASK_IIR", 6, 1), ("GOWN_SURGICAL", 4, 1), ("DRAPES_GYN_CASE", 1, 0)]


def test_tier_shares_add_up(db):
    res = oc.case_footprint(db, CASE)
    assert sum(res["tier_share"].values()) == pytest.approx(1)
    assert res["tier_kg"][3] == pytest.approx(oc.material_based(db, "DRAPES_GYN_CASE").kg_co2e)  # drapes: tier 3
    assert res["tier_kg"][4] == 0                                                             # nothing on tier 4


def test_sensitivity_moves_only_the_affected_items(db):
    drapes_production = 0.590566 * 3.10472699
    mat = next(r for r in oc.sensitivity(db, CASE) if r["parameter"].startswith("Tier 3: material"))
    assert mat["high_kg"] - mat["low_kg"] == pytest.approx(0.6 * drapes_production)
    spend = next(r for r in oc.sensitivity(db, CASE) if r["parameter"].startswith("Tier 4"))
    assert spend["range_kg"] == pytest.approx(0)          # no item in this case uses tier 4


def test_tier1_example_top_glove(db):
    # Top Glove press release (2024): 0.0277 kg CO2e per 3.5 g glove, raw material extraction to disposal
    r = oc.hybrid(db, "GLOVE_TOPGLOVE")
    assert r.tier.startswith("Tier 1") and r.g_co2e == pytest.approx(27.7)
