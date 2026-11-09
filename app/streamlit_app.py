"""Demo of the calculation methods.  Run from the project folder:  python -m streamlit run app/streamlit_app.py"""
import inspect
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import orcarbon as oc  # noqa: E402
from orcarbon import methods  # noqa: E402

st.set_page_config(page_title="OR Carbon Methods", page_icon="🌿", layout="wide")
db = oc.load()

COLOR = {"A": "#2E6DB4", "B": "#2F9A68", "C": "#C47F22", "GAS": "#8A4FBF"}
SHORT = {"A": "A · Product LCA", "B": "B · Material-based", "C": "C · Spend-based"}

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.card {margin-bottom: 18px; border: 1px solid rgba(128,128,128,.35); border-top: 5px solid var(--c); border-radius: 10px;
       padding: 14px 16px; height: 100%;}
.card .label {font-weight: 700; font-size: 1.02rem;}
.card .tier {opacity: .7; font-size: .82rem; margin-bottom: 6px;}
.card .value {font-size: 2rem; font-weight: 700; color: var(--c); line-height: 1.2;}
.card .na {font-size: 1.1rem; opacity: .6; padding: 10px 0;}
.card .note {font-size: .85rem; opacity: .8; margin-top: 6px;}
.ladder {border-left: 3px solid rgba(128,128,128,.35); padding-left: 12px; margin: 6px 0;}
.ladder div {padding: 3px 0;}
</style>""", unsafe_allow_html=True)


def fmt(kg):
    return f"{kg * 1000:,.1f} g" if kg < 1 else f"{kg:,.2f} kg"


def card(r, note=""):
    c = COLOR.get(r.method, "#666")
    body = (f"<div class='value'>{fmt(r.kg_co2e)} CO₂e</div>" if r.available
            else "<div class='na'>not available</div>")
    st.markdown(f"<div class='card' style='--c:{c}'><div class='label'>{SHORT.get(r.method, r.name)}</div>"
                f"<div class='tier'>{r.tier}</div>{body}<div class='note'>{note}</div></div>",
                unsafe_allow_html=True)


def steps_table(r):
    st.dataframe(pd.DataFrame({"step": range(1, len(r.steps) + 1), "calculation": r.steps}),
                 hide_index=True, width="stretch")


def sources_list(r):
    for s in r.sources:
        st.markdown(f"- **{s}**: {db.cite(s)}")


def show_code(*funcs):
    with st.expander("Show the code"):
        for f in funcs:
            st.code(inspect.getsource(f), language="python")


# ------------------------------------------------------------------ sidebar: inputs
with st.sidebar:
    st.header("Inputs")
    names = {db.products[p]["name"]: p for p in db.products}
    pid = names[st.selectbox("Product", list(names))]
    qty = st.number_input("Quantity", min_value=1, value=1, step=1)
    routes = list(db.waste_factor)
    route = st.selectbox(
        "Waste route (used by method B)", routes,
        index=routes.index(db.products[pid]["default_waste_route"]),
        format_func=lambda k: k.replace("_", " "),
        help="How the used item is treated after the operation. Method B adds: mass × factor of this route "
             "(Rizan et al. 2021, UK hospital). Methods A and C do not use it.")
    st.caption(f"Factor of this route: {db.waste_factor[route]['value'] * 1000:,.0f} kg CO₂e per tonne of waste")
    st.divider()
    own = st.toggle("Use a local price in method C", help="For example, a Soroka purchase price.")
    if own:
        own_price = st.number_input("Price per unit", min_value=0.0, value=0.10, step=0.01, format="%.3f")
        own_cur = st.selectbox("Currency", ["USD", "CAD"])
        own_year = st.selectbox("Price year", [2022, 2023])
    st.divider()
    st.caption("Prototype for demonstration. Every factor comes from a published source (Sources tab). "
               "Hamdan & Sewar · SCE final project · Supervisor: Dr. Hadas Chassidim")

st.title("Carbon footprint of operating-room products")
st.write("Three calculation methods from the Literature Review (Chapter 3, Table 11), run on the same product. "
         "All three compute **CF = Q × EF** (activity data × emission factor); they differ in what Q is and where "
         "EF comes from.")

tab_prod, tab_gas, tab_case, tab_src = st.tabs(["Product", "Anaesthetic gases", "One operation", "Sources"])

# ------------------------------------------------------------------ product
with tab_prod:
    p = db.products[pid]
    st.subheader(f"{p['name']} × {qty}")
    st.caption(f"Unit: {p['unit']}. {p['notes']}")

    rA = oc.product_lca(db, pid, qty)
    rB = oc.material_based(db, pid, qty, waste_route=route)
    rC = (oc.spend_based(db, pid, qty, price=own_price, currency=own_cur, price_year=own_year) if own
          else oc.spend_based(db, pid, qty))
    results = [rA, rB, rC]

    c1, c2, c3 = st.columns(3)
    with c1:
        card(rA, "Published life-cycle result for the product" if rA.available else rA.warnings[0])
    with c2:
        card(rB, f"Lower bound · mass covered: {rB.coverage:.0%}" if rB.available else rB.warnings[0])
    with c3:
        card(rC, "Follows the price, not the material" if rC.available else rC.warnings[0])

    # hybrid decision
    chosen = next(r for r in results if r.available)
    st.markdown("#### Hybrid choice for this product")
    ladder = []
    for r in results:
        if r is chosen:
            ladder.append(f"<div>✅ <b>{SHORT[r.method]}</b>: {r.tier}. <b>Used</b>.</div>")
        elif not r.available:
            ladder.append(f"<div>✖ {SHORT[r.method]}: not available ({r.warnings[0].rstrip('.')}).</div>")
        else:
            ladder.append(f"<div>⏸ {SHORT[r.method]}: available, but lower in the hierarchy.</div>")
    st.markdown("<div class='ladder'>" + "".join(ladder) + "</div>", unsafe_allow_html=True)
    st.caption("Each item gets the best available tier (Literature Review, Sections 3.3 and 7.1): "
               "Tier 1–2 product data first, then the material-based estimate, then the spend-based estimate.")

    rows = [{"method": SHORT[r.method], "part": part, "g": v * 1000}
            for r in results if r.available for part, v in r.breakdown.items()]
    if rows:
        st.altair_chart(
            alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("sum(g):Q", title="g CO₂e"),
                y=alt.Y("method:N", title=None, sort=list(SHORT.values()), axis=alt.Axis(labelLimit=220)),
                color=alt.Color("part:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=320)),
                tooltip=["method", "part", alt.Tooltip("g:Q", title="g CO₂e", format=",.2f")],
            ).properties(height=170), width="stretch")
    av = [r.kg_co2e for r in results if r.available]
    if len(av) > 1:
        st.info(f"For this product the highest estimate is **{max(av) / min(av):.1f}×** the lowest. "
                "This is why the tier of every result is reported.")

    st.markdown("#### How each method works")
    tA, tB, tC, tH = st.tabs([SHORT["A"], SHORT["B"], SHORT["C"], "Hybrid"])
    with tA:
        st.write("Takes the footprint per unit of the product and multiplies it by the quantity. Tier 1 when the "
                 "figure is the manufacturer's own for this exact product (Top Glove, 3.5 g glove); Tier 2 when it "
                 "comes from a published LCA of an equivalent product (Rizan et al.: raw materials to incineration, "
                 "including manufacture, transport and packaging).")
        st.latex(r"CF = Q \times EF_{product}")
        if rA.available:
            steps_table(rA)
            sources_list(rA)
        else:
            st.warning(rA.warnings[0])
        show_code(methods.product_lca)
    with tB:
        st.write("Breaks the product into its materials. Each mass is multiplied by the emission factor of "
                 "producing that material, and the whole mass by the factor of the waste route. Energy for "
                 "manufacturing, transport and packaging are missing, so the result is a lower bound.")
        st.latex(r"CF = Q \times \Big(\sum_i m_i \times EF_{material(i)} + m_{total} \times EF_{waste\ route}\Big)")
        if rB.available:
            steps_table(rB)
            for w in rB.warnings:
                st.caption("⚠ " + w)
            sources_list(rB)
        show_code(methods.material_based)
    with tC:
        st.write("Multiplies the money spent by an average emission factor for the industry (US EPA, kg CO₂e per "
                 "US dollar of 2022). The price is first converted to that currency and year.")
        st.latex(r"CF = Q \times price_{USD\,2022} \times EF_{industry}, \quad "
                 r"price_{USD\,2022} = \frac{price_{CAD}}{FX_{2023}} \times \frac{CPI_{2022}}{CPI_{2023}}")
        if rC.available:
            steps_table(rC)
            for w in rC.warnings:
                st.caption("⚠ " + w)
            sources_list(rC)
        else:
            st.warning(rC.warnings[0])
        show_code(methods.spend_based, methods.to_factor_dollars)
    with tH:
        st.write("The hybrid approach of the Literature Review works at item level: every item is estimated with "
                 "the best source available for it, and an operation combines items from different tiers. "
                 "Each result keeps its tier, so the share of the total that rests on weaker data is visible.")
        st.markdown("1. **Tier 1**: footprint of this exact product (manufacturer, EPD, MedZero). Example: Top Glove 3.5 g glove.\n"
                    "2. **Tier 2**: published LCA of an equivalent product (method A).\n"
                    "3. **Tier 3**: material-based estimate (method B).\n"
                    "4. **Tier 4**: spend-based estimate (method C).")
        show_code(methods.compare, methods.hybrid)

# ------------------------------------------------------------------ gases
with tab_gas:
    st.write("Anaesthetic gases are emitted directly. The liquid volume is converted to mass with the specific "
             "gravity on the product label; all of the agent used is assumed to reach the atmosphere.")
    st.latex(r"CF = m_{agent} \times GWP_{100}, \qquad m = V_{liquid} \times \text{specific gravity}")
    g1, g2, g3 = st.columns(3)
    agent = g1.selectbox("Agent", ["desflurane", "sevoflurane"])
    mode = g2.radio("Amount given as", ["bottles", "mL of liquid", "grams"], horizontal=True)
    amount = g3.number_input("Amount", min_value=0.0, value=1.0 if mode == "bottles" else 20.0)
    kw = {"bottles": {"bottles": amount}, "mL of liquid": {"ml_liquid": amount}, "grams": {"grams": amount}}[mode]
    rg = oc.anaesthetic_gas(db, agent, **kw)
    left, right = st.columns([1, 2])
    with left:
        card(rg, f"GWP100 = {db.agents[agent]['gwp100']:g} (IPCC AR6)")
    with right:
        steps_table(rg)
    comp = pd.DataFrame([{"agent": a, "kg CO₂e per bottle": oc.anaesthetic_gas(db, a, bottles=1).kg_co2e}
                         for a in ["desflurane", "sevoflurane"]])
    st.markdown("#### One full bottle of each agent")
    st.altair_chart(alt.Chart(comp).mark_bar(color=COLOR["GAS"], cornerRadiusEnd=3).encode(
        x=alt.X("kg CO₂e per bottle:Q"), y=alt.Y("agent:N", title=None),
        tooltip=["agent", alt.Tooltip("kg CO₂e per bottle:Q", format=",.1f")]).properties(height=110),
        width="stretch")
    sources_list(rg)
    show_code(methods.anaesthetic_gas)

# ------------------------------------------------------------------ one operation
with tab_case:
    st.write("One operation, with the hybrid choice for every item. Items that were opened but not used are "
             "counted separately (Literature Review, Section 7.2).")
    st.warning("The quantities are illustrative, not measured. The emission factors are the real ones.")
    default = pd.DataFrame([
        {"product": db.products[p]["name"], "opened": o, "unused": u} for p, o, u in
        [("GLOVE_TOPGLOVE", 20, 4), ("MASK_IIR", 6, 1), ("GOWN_SURGICAL", 4, 1), ("DRAPES_GYN_CASE", 1, 0)]])
    left, right = st.columns([3, 2])
    with left:
        edited = st.data_editor(default, num_rows="fixed", hide_index=True, disabled=["product"], width="stretch")
    with right:
        case_agent = st.selectbox("Anaesthetic agent", ["sevoflurane", "desflurane"], key="case_agent")
        case_grams = st.number_input("Grams released", min_value=0.0, value=20.0, key="case_g")
    items = [(names[row["product"]], float(row["opened"]), float(row["unused"])) for _, row in edited.iterrows()]
    try:
        res = oc.case_footprint(db, items, gas=(case_agent, case_grams))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", f"{res['total_kg']:.2f} kg CO₂e")
        m2.metric("Supplies opened", f"{res['supplies_kg']:.2f} kg CO₂e")
        m3.metric("Opened but unused", f"{res['unused_kg']:.2f} kg CO₂e")
        m4.metric("Anaesthetic gas", f"{res['gas_kg']:.2f} kg CO₂e")
        st.caption(f"Unused items are {res['unused_share_of_supplies']:.0%} of the supplies footprint.")
        st.dataframe(pd.DataFrame([{
            "product": l.name, "opened": l.opened, "used": l.used, "unused": l.unused,
            "method": SHORT[l.method], "tier": l.tier_number, "g CO₂e per unit": round(l.kg_per_unit * 1000, 1),
            "kg CO₂e opened": round(l.kg_opened, 3), "kg CO₂e unused": round(l.kg_unused, 3)} for l in res["lines"]]),
            hide_index=True, width="stretch")

        # ---- data quality: share of each tier (Literature Review, Section 7.1)
        st.markdown("#### Data quality: share of the supplies footprint on each tier")
        st.caption("Section 7.1 of the Literature Review: every result reports how much of its CO₂e rests on each "
                   "tier, so the reader can see how much depends on weaker estimates.")
        tiers = pd.DataFrame([{"tier": f"Tier {t}", "share": s, "kg CO₂e": res["tier_kg"][t]}
                              for t, s in res["tier_share"].items()])
        st.altair_chart(alt.Chart(tiers).mark_bar(cornerRadiusEnd=3).encode(
            x=alt.X("share:Q", axis=alt.Axis(format="%"), title="share of supplies footprint",
                    scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("tier:N", title=None),
            color=alt.Color("tier:N", legend=None,
                            scale=alt.Scale(range=["#1F4E8C", COLOR["A"], COLOR["B"], COLOR["C"]])),
            tooltip=["tier", alt.Tooltip("share:Q", format=".0%"), alt.Tooltip("kg CO₂e:Q", format=".2f")],
        ).properties(height=150), width="stretch")

        # ---- sensitivity analysis (Literature Review, Table 12, level 4)
        st.markdown("#### Sensitivity analysis")
        st.caption("Table 12, level 4: the Tier 3 and Tier 4 factors are varied one at a time, and the waste route "
                   "is switched between the three real routes. The ± range is an analysis setting, not a measured "
                   "uncertainty.")
        var = st.slider("Variation of the factors (±)", 0.10, 0.50, 0.30, 0.05, format="%.2f")
        sens = oc.sensitivity(db, items, gas=(case_agent, case_grams), variation=var)
        sdf = pd.DataFrame([{"parameter": s["parameter"], "low": s["low_kg"], "high": s["high_kg"],
                             "base": s["base_kg"], "change": f"{s['range_kg'] / s['base_kg']:.1%}"} for s in sens])
        bars = alt.Chart(sdf).mark_bar(color=COLOR["B"], height=14).encode(
            x=alt.X("low:Q", title="total kg CO₂e of the operation", scale=alt.Scale(zero=False)),
            x2="high:Q", y=alt.Y("parameter:N", title=None, sort=None, axis=alt.Axis(labelLimit=420)),
            tooltip=["parameter", alt.Tooltip("low:Q", format=".2f"), alt.Tooltip("high:Q", format=".2f"), "change"])
        rule = alt.Chart(sdf).mark_rule(strokeDash=[4, 3]).encode(x="base:Q")
        st.altair_chart((bars + rule).properties(height=170), width="stretch")
        st.dataframe(sdf.round(2), hide_index=True, width="stretch")
        if all(l.tier_number != 4 for l in res["lines"]):
            st.caption("No item in this operation uses Tier 4, so varying the spend-based factor changes nothing.")
        show_code(oc.case_footprint, oc.sensitivity)
    except ValueError as e:
        st.error(str(e))

# ------------------------------------------------------------------ sources
with tab_src:
    st.write("Every number in the data files points to one of these sources.")
    st.dataframe(pd.DataFrame(db.sources.values()), hide_index=True, width="stretch",
                 column_config={"url": st.column_config.LinkColumn("link")})
