# OR carbon footprint: calculation methods (prototype)

Hamdan & Sewar · SCE final project · Supervisor: Dr. Hadas Chassidim

A small prototype that implements the carbon-footprint calculation methods compared in the Literature Review
(Chapter 3, Tables 7–8 and 11) and runs them on real operating-room products. **It is a demonstration, not a
validated tool:** the emission factors and product data are real and sourced, the case quantities are illustrative.

| Method | Formula | Data used |
|---|---|---|
| A. Product-level LCA (Tier 1–2) | quantity × kg CO₂e per unit | Tier 1: Top Glove (manufacturer, 2024); Tier 2: Rizan et al., cradle-to-grave LCA of PPE |
| B. Material-based (Tier 3, lower bound) | Σ mass × material factor + mass × waste-route factor | Rizan et al. (masses), UK conversion factors (polypropylene), ICM (synthetic rubber), Rizan et al. 2021 (waste) |
| C. Spend-based (Tier 4) | price in USD 2022 × kg CO₂e per USD | Alberta Health Services prices, Bank of Canada, BLS CPI, US EPA factors (NAICS 339113) |
| Anaesthetic gases | mass released × GWP100 | IPCC AR6 GWP100, FDA labels (density, bottle size) |

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

python -m pytest                 # 18 verification tests
python -m streamlit run app/streamlit_app.py   # interactive demo (or double-click run_app.bat)
python -m notebook notebooks/calculation_methods.ipynb   # step-by-step explanation (or run_notebook.bat)
```

## Structure

```
data/            every number, with the id of its source (sources.csv holds the full citations and links)
orcarbon/        calculation engine
  data.py        loads the CSV files and checks that every number has a source
  methods.py     methods A, B, C, anaesthetic gases, comparison and hybrid (tier) choice
  case.py        one operation: opened, used and unused items, share of each tier, sensitivity analysis
tests/           verification tests (reproduce published values, check the rules of each method)
notebooks/       step-by-step explanation with results and charts
app/             Streamlit demo
```

## Results on the example products (one unit)

| Product | A. LCA | B. Material | C. Spend |
|---|---|---|---|
| Nitrile glove, Top Glove 3.5 g (A = Tier 1, manufacturer) | 27.7 g | 15.7 g | 23.0 g |
| Nitrile examination glove (A = Tier 2, Rizan) | 26 g | 14.5 g | 23.0 g |
| Surgical mask (Type IIR) | 20 g | 12.5 g | 93.2 g |
| Single-use surgical gown | 905 g | 598 g | 367 g* |
| Drapes of one gynecological operation | – | 2.47 kg | – |

\* The only public price is for an isolation gown, a different product.

Method B with the UK polypropylene factor reproduces the 292 kg CO₂e that Waters et al. reported for 93.9 kg of drapes (291.5 kg, within 0.5%).

## Limitations

- Factors are from the UK, USA, Canada and Australia; Israeli factors and Soroka's prices and waste routes are still needed.
- Rizan et al. (PPE) is a preprint. The polypropylene, synthetic-rubber and EPA factors were read from Climatiq's copies of the original data sets.
- Method B leaves out manufacturing energy, transport and packaging, and has no factor for aluminium (0.2 g in the mask).
- The EPA factors use IPCC AR5 GWPs; the gas calculation uses AR6.

To use a Soroka price in method C: `spend_based(db, "GLOVE_NITRILE", price=..., currency="USD", price_year=2022)`
(or the "Use a local price" option in the app). Prices in shekels need an exchange rate added to `data/economics.csv`.
