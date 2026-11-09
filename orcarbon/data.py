"""Load the reference data (emission factors, products, prices, sources) from the CSV files in /data.

Every number used by the calculators lives in these files, next to the id of the source it came from,
so that each result can be traced back to a publication (see data/sources.csv).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read(name: str, data_dir: Path) -> list[dict]:
    with open(data_dir / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(value: str) -> float | None:
    return float(value) if value not in ("", None) else None


@dataclass
class Database:
    sources: dict[str, dict] = field(default_factory=dict)
    factors: dict[str, dict] = field(default_factory=dict)           # factor_id -> row
    material_factor: dict[str, dict] = field(default_factory=dict)   # material -> row
    waste_factor: dict[str, dict] = field(default_factory=dict)      # treatment route -> row
    spend_factor: dict[str, dict] = field(default_factory=dict)      # NAICS code -> row
    products: dict[str, dict] = field(default_factory=dict)
    components: dict[str, list[dict]] = field(default_factory=dict)  # product_id -> components
    product_lca: dict[str, dict] = field(default_factory=dict)
    prices: dict[str, dict] = field(default_factory=dict)
    economics: dict[str, float] = field(default_factory=dict)
    agents: dict[str, dict] = field(default_factory=dict)

    def cite(self, source_id: str) -> str:
        return self.sources[source_id]["citation"]


def load(data_dir: Path | str = DATA_DIR) -> Database:
    data_dir = Path(data_dir)
    db = Database()
    db.sources = {r["source_id"]: r for r in _read("sources.csv", data_dir)}

    for r in _read("emission_factors.csv", data_dir):
        r["value"] = float(r["value"])
        db.factors[r["factor_id"]] = r
        target = {"material": db.material_factor, "waste": db.waste_factor, "spend": db.spend_factor}[r["kind"]]
        key = r["key"].replace("NAICS_", "")
        target[key] = r

    db.products = {r["product_id"]: r for r in _read("products.csv", data_dir)}
    for r in _read("components.csv", data_dir):
        r["mass_g"] = float(r["mass_g"])
        db.components.setdefault(r["product_id"], []).append(r)
    for r in _read("product_lca.csv", data_dir):
        r["kg_co2e_per_unit"] = float(r["kg_co2e_per_unit"])
        db.product_lca[r["product_id"]] = r
    for r in _read("prices.csv", data_dir):
        r["price"] = float(r["price"])
        r["price_year"] = int(r["price_year"])
        db.prices[r["product_id"]] = r
    db.economics = {r["key"]: float(r["value"]) for r in _read("economics.csv", data_dir)}
    for r in _read("anaesthetic_agents.csv", data_dir):
        r["gwp100"] = float(r["gwp100"])
        r["specific_gravity"] = _num(r["specific_gravity"])
        r["bottle_ml"] = _num(r["bottle_ml"])
        db.agents[r["agent"]] = r

    _check_sources(db)
    return db


def _check_sources(db: Database) -> None:
    """Fail fast if any number points to a source that is not in sources.csv."""
    used = [r["source_id"] for r in db.factors.values()]
    used += [c["source_id"] for cs in db.components.values() for c in cs]
    used += [r["source_id"] for r in db.product_lca.values()]
    used += [r["source_id"] for r in db.prices.values()]
    used += [r["gwp_source_id"] for r in db.agents.values()]
    used += [r["label_source_id"] for r in db.agents.values() if r["label_source_id"]]
    missing = sorted(set(u for u in used if u not in db.sources))
    if missing:
        raise ValueError(f"Data points to unknown sources: {missing}")
