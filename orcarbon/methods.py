"""The calculation methods compared in the Literature Review (Chapter 3, Table 8 and Table 11).

All methods share the same principle:  carbon footprint = activity data x emission factor
(CF = Q x EF). They differ in WHAT the activity data are and WHERE the emission factor comes from:

  Method A  product-level LCA  (Tier 2)   CF = quantity x [kg CO2e per product, from a published LCA]
  Method B  material-based     (Tier 3)   CF = sum(mass_i x EF_material_i) + total mass x EF_waste_route
  Method C  spend-based        (Tier 4)   CF = price (converted to USD of the factor's year) x EF [kg CO2e per USD]
  Gases     anaesthetic agents            CF = mass of agent released x GWP100

Every result keeps the steps of its calculation and the sources it used, so it can be explained and checked.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .data import Database

TIER_LABEL = {
    "A1": "Tier 1 - footprint of this exact product (manufacturer, EPD or MedZero)",
    "A": "Tier 2 - published LCA of an equivalent product",
    "B": "Tier 3 - material-based estimate (lower bound)",
    "C": "Tier 4 - spend-based estimate",
}


@dataclass
class MethodResult:
    method: str                      # "A", "B", "C" or "GAS"
    name: str
    available: bool
    kg_co2e: float | None = None
    tier: str = ""
    steps: list[str] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)   # kg CO2e by part
    coverage: float | None = None    # share of the product mass that had a factor (method B)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def g_co2e(self) -> float | None:
        return None if self.kg_co2e is None else self.kg_co2e * 1000


def _not_available(method: str, name: str, reason: str) -> MethodResult:
    return MethodResult(method=method, name=name, available=False, tier=TIER_LABEL.get(method, ""), warnings=[reason])


# ---------------------------------------------------------------- Method A
def product_lca(db: Database, product_id: str, quantity: float = 1) -> MethodResult:
    name = "A. Product-level LCA"
    row = db.product_lca.get(product_id)
    if row is None:
        return _not_available("A", name, "No published LCA of this product or an equivalent one is in the database.")
    ef = row["kg_co2e_per_unit"]
    cf = quantity * ef
    tier = TIER_LABEL["A1"] if row["tier"] == "1" else TIER_LABEL["A"]
    return MethodResult(
        method="A", name=name, available=True, kg_co2e=cf, tier=tier,
        steps=[
            f"Emission factor of the product: {ef * 1000:g} g CO2e per {db.products[product_id]['unit']} "
            f"({row['life_cycle_scope']}).",
            f"CF = quantity x EF = {quantity:g} x {ef:g} kg = {cf:.4f} kg CO2e.",
        ],
        breakdown={"whole life cycle (published)": cf},
        sources=[row["source_id"]],
    )


# ---------------------------------------------------------------- Method B
def material_based(db: Database, product_id: str, quantity: float = 1,
                   include_disposal: bool = True, waste_route: str | None = None) -> MethodResult:
    name = "B. Material-based"
    comps = db.components.get(product_id)
    if not comps:
        return _not_available("B", name, "The mass and material of this product are not known.")
    steps, warnings, sources = [], [], []
    production = 0.0
    matched_mass = total_mass = 0.0
    for c in comps:
        total_mass += c["mass_g"]
        sources.append(c["source_id"])
        f = db.material_factor.get(c["material"])
        if f is None:
            warnings.append(f"No emission factor for '{c['material']}' ({c['component']}, {c['mass_g']:g} g); "
                            f"this part is left out of production emissions.")
            continue
        kg = c["mass_g"] / 1000 * f["value"]
        production += kg
        matched_mass += c["mass_g"]
        sources.append(f["source_id"])
        steps.append(f"{c['component']}: {c['mass_g']:g} g {c['material'].replace('_', ' ')} x {f['value']:.3f} kg CO2e/kg "
                     f"= {kg * 1000:.2f} g CO2e")
    breakdown = {"material production": production * quantity}

    if include_disposal:
        route = waste_route or db.products[product_id]["default_waste_route"]
        w = db.waste_factor[route]
        disposal = total_mass / 1000 * w["value"]
        breakdown["disposal"] = disposal * quantity
        sources.append(w["source_id"])
        steps.append(f"disposal ({route.replace('_', ' ')}): {total_mass:g} g x {w['value']:.3f} kg CO2e/kg "
                     f"= {disposal * 1000:.2f} g CO2e")

    cf = sum(breakdown.values())
    steps.append(f"CF = {quantity:g} x ({' + '.join(f'{v / quantity * 1000:.2f}' for v in breakdown.values())}) g "
                 f"= {cf * 1000:.2f} g CO2e")
    warnings.append("Manufacturing energy, transport and packaging are not included, so this is a lower bound.")
    return MethodResult(
        method="B", name=name, available=True, kg_co2e=cf, tier=TIER_LABEL["B"], steps=steps,
        breakdown=breakdown, coverage=matched_mass / total_mass, warnings=warnings,
        sources=list(dict.fromkeys(sources)),
    )


# ---------------------------------------------------------------- Method C
def to_factor_dollars(db: Database, price: float, currency: str, price_year: int) -> tuple[float, list[str]]:
    """Convert a price to US dollars of 2022, the currency and year of the EPA factors."""
    steps = []
    usd = price
    if currency == "CAD":
        fx = db.economics[f"CAD_PER_USD_{price_year}"]
        usd = price / fx
        steps.append(f"currency: {price:.3f} CAD / {fx} CAD per USD = {usd:.4f} USD ({price_year})")
    elif currency != "USD":
        raise ValueError(f"No exchange rate for {currency}")
    if price_year != 2022:
        cpi_from, cpi_to = db.economics[f"CPI_U_{price_year}"], db.economics["CPI_U_2022"]
        usd = usd * cpi_to / cpi_from
        steps.append(f"price year: x CPI 2022 / CPI {price_year} = x {cpi_to}/{cpi_from} = {usd:.4f} USD (2022)")
    return usd, steps


def spend_based(db: Database, product_id: str, quantity: float = 1, price: float | None = None,
                currency: str | None = None, price_year: int | None = None) -> MethodResult:
    """Spend-based estimate. A custom price (e.g. Soroka's purchase price) can replace the stored one."""
    name = "C. Spend-based"
    p = db.prices.get(product_id)
    if price is None and p is None:
        return _not_available("C", name, "No price is available for this product.")
    price = p["price"] if price is None else price
    currency = (p["currency"] if p else "USD") if currency is None else currency
    price_year = (p["price_year"] if p else 2022) if price_year is None else price_year
    naics = db.products[product_id]["naics"]
    f = db.spend_factor[naics]
    usd2022, steps = to_factor_dollars(db, price, currency, price_year)
    cf = quantity * usd2022 * f["value"]
    steps.insert(0, f"price: {price:.3f} {currency} per unit ({price_year})")
    steps.append(f"CF = {quantity:g} x {usd2022:.4f} USD x {f['value']} kg CO2e/USD (NAICS {naics}) = {cf * 1000:.2f} g CO2e")
    warnings = ["The factor is an average for the whole industry, so the result follows the price, not the material."]
    sources = [f["source_id"], "NAICS_339113", "BOC_FX", "BLS_CPI"]
    if p:
        sources.insert(0, p["source_id"])
        if p["match_quality"] != "same product type":
            warnings.append(f"Price is for a {p['match_quality']}.")
    return MethodResult(method="C", name=name, available=True, kg_co2e=cf, tier=TIER_LABEL["C"], steps=steps,
                        breakdown={"supply chain (economic average)": cf}, warnings=warnings, sources=sources)


# ---------------------------------------------------------------- Anaesthetic gases
def anaesthetic_gas(db: Database, agent: str, grams: float | None = None, ml_liquid: float | None = None,
                    bottles: float | None = None) -> MethodResult:
    """CF = mass of agent released x GWP100 (assumes all the agent used is released to the air)."""
    a = db.agents[agent]
    steps = []
    if bottles is not None:
        ml_liquid = bottles * a["bottle_ml"]
        steps.append(f"{bottles:g} bottle(s) x {a['bottle_ml']:g} mL = {ml_liquid:g} mL of liquid {agent}")
    if ml_liquid is not None:
        grams = ml_liquid * a["specific_gravity"]
        steps.append(f"mass = {ml_liquid:g} mL x {a['specific_gravity']} g/mL = {grams:.1f} g")
    if grams is None:
        raise ValueError("Give grams, ml_liquid or bottles")
    cf = grams / 1000 * a["gwp100"]
    steps.append(f"CF = {grams:.1f} g x GWP100 {a['gwp100']:g} = {cf:.2f} kg CO2e")
    sources = [a["gwp_source_id"]] + ([a["label_source_id"]] if a["label_source_id"] else [])
    return MethodResult(method="GAS", name=f"Anaesthetic gas: {agent}", available=True, kg_co2e=cf, tier="direct emission",
                        steps=steps, breakdown={agent: cf}, sources=sources,
                        warnings=["Assumes no capture of waste anaesthetic gas."])


# ---------------------------------------------------------------- Comparison and hybrid choice
def compare(db: Database, product_id: str, quantity: float = 1, waste_route: str | None = None) -> list[MethodResult]:
    """Run the three methods on the same product."""
    return [product_lca(db, product_id, quantity), material_based(db, product_id, quantity, waste_route=waste_route),
            spend_based(db, product_id, quantity)]


def hybrid(db: Database, product_id: str, quantity: float = 1, waste_route: str | None = None) -> MethodResult:
    """Choose the best available estimate in tier order (Literature Review, Table 11):
    A (Tier 1-2), then B (Tier 3), then C (Tier 4). One estimate per item, never a sum of methods."""
    for r in compare(db, product_id, quantity, waste_route):
        if r.available:
            return r
    raise LookupError(f"No method can estimate {product_id}")
