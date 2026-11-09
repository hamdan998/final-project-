"""Footprint of one operation: the items opened (used + unused) and the anaesthetic gas.

This mirrors the method in the Literature Review:
  * Section 7.2, steps 4-6: used = opened - unused;  CF(unused) = sum(Q_unused,i x EF_i)
  * Section 7.1: every item gets the best available tier, and each result reports the share of its CO2e
    that rests on each tier (an indicator of data quality)
  * Table 12, level 4: sensitivity analysis - vary the Tier 3 and Tier 4 factors and a key assumption
    (the waste route) and see how much the result moves
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from .data import Database
from .methods import anaesthetic_gas, hybrid

TIER_NUMBER = {"A": None, "B": 3, "C": 4}   # A is tier 1 or 2, read from its label


@dataclass
class CaseLine:
    product_id: str
    name: str
    opened: float
    unused: float
    method: str
    tier: str
    kg_per_unit: float

    @property
    def used(self) -> float:
        return self.opened - self.unused

    @property
    def kg_opened(self) -> float:
        return self.opened * self.kg_per_unit

    @property
    def kg_unused(self) -> float:
        return self.unused * self.kg_per_unit

    @property
    def tier_number(self) -> int:
        return TIER_NUMBER[self.method] or int(self.tier.split()[1])


def case_footprint(db: Database, items: list[tuple[str, float, float]], gas: tuple[str, float] | None = None,
                   waste_route: str | None = None) -> dict:
    """items: (product_id, opened, unused); gas: (agent, grams released).
    waste_route replaces the default route of every item estimated with the material-based method."""
    lines = []
    for product_id, opened, unused in items:
        if unused > opened:
            raise ValueError(f"{product_id}: unused ({unused}) cannot exceed opened ({opened})")
        r = hybrid(db, product_id, 1, waste_route=waste_route)
        lines.append(CaseLine(product_id, db.products[product_id]["name"], opened, unused, r.method, r.tier, r.kg_co2e))
    supplies = sum(l.kg_opened for l in lines)
    unused = sum(l.kg_unused for l in lines)
    gas_kg = anaesthetic_gas(db, gas[0], grams=gas[1]).kg_co2e if gas else 0.0
    total = supplies + gas_kg

    # share of the supplies footprint that rests on each tier (Section 7.1)
    by_tier = {t: 0.0 for t in (1, 2, 3, 4)}
    for l in lines:
        by_tier[l.tier_number] += l.kg_opened
    tier_share = {t: (kg / supplies if supplies else 0.0) for t, kg in by_tier.items()}

    return {
        "lines": lines,
        "supplies_kg": supplies,
        "unused_kg": unused,
        "gas_kg": gas_kg,
        "total_kg": total,
        "unused_share_of_supplies": unused / supplies if supplies else 0.0,
        "tier_kg": by_tier,
        "tier_share": tier_share,
    }


def _scaled(db: Database, table: str, factor: float) -> Database:
    """A copy of the database with every factor of one table (material, waste or spend) multiplied."""
    d = copy.deepcopy(db)
    for row in getattr(d, table).values():
        row["value"] *= factor
    return d


def sensitivity(db: Database, items: list[tuple[str, float, float]], gas: tuple[str, float] | None = None,
                variation: float = 0.30) -> list[dict]:
    """One-at-a-time sensitivity analysis (Literature Review, Table 12, level 4).

    The +/- variation is an analysis setting chosen by the user, not a measured uncertainty.
    Returns, for each parameter, the total footprint at its low and high value."""
    base = case_footprint(db, items, gas)["total_kg"]
    rows = []
    for label, table in [("Tier 3: material emission factors", "material_factor"),
                         ("Tier 3: waste-route emission factors", "waste_factor"),
                         ("Tier 4: spend-based emission factors", "spend_factor")]:
        low = case_footprint(_scaled(db, table, 1 - variation), items, gas)["total_kg"]
        high = case_footprint(_scaled(db, table, 1 + variation), items, gas)["total_kg"]
        rows.append({"parameter": f"{label} ±{variation:.0%}", "low_kg": low, "high_kg": high})
    # key assumption: the waste route of the material-based items (real alternative factors)
    routes = {r: case_footprint(db, items, gas, waste_route=r)["total_kg"] for r in db.waste_factor}
    rows.append({"parameter": "Waste route: " + " / ".join(r.replace("_", " ") for r in routes),
                 "low_kg": min(routes.values()), "high_kg": max(routes.values())})
    for r in rows:
        r["base_kg"] = base
        r["range_kg"] = r["high_kg"] - r["low_kg"]
    return sorted(rows, key=lambda r: -r["range_kg"])
