"""pages/6_Special_Cases.py — Special Cases (Ch 21, 22, 30, 32)"""
import streamlit as st
import pandas as pd
import math
from special_cases import (
    eva_valuation, distressed_firm_value,
    financial_firm_excess_returns, normalise_earnings,
    default_probability_from_rating, default_probability_from_industry_age,
    DEFAULT_PROB_BY_RATING, SURVIVAL_BY_INDUSTRY,
    INDUSTRY_NAMES_SC, RATING_NAMES,
)

st.set_page_config(page_title="Special Cases", page_icon="🔬", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box {
    background: #1e293b; border-left: 3px solid #3b82f6;
    border-radius: 0 8px 8px 0; padding: 14px 18px;
    margin: 10px 0 18px 0; font-size: 0.88rem; line-height: 1.7; color: #cbd5e1;
}
.score-pill { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.8rem; font-weight:500; margin-top:6px; }
.score-green  { background:#14532d; color:#86efac; }
.score-yellow { background:#713f12; color:#fde68a; }
.score-red    { background:#7f1d1d; color:#fca5a5; }
.placeholder-badge { font-size:0.72rem; padding:2px 8px; border-radius:4px; background:#3b2a0f; color:#fbbf24; display:inline-block; margin-bottom:6px; }
.warning-box { background:#292524; border:1px solid #78350f; border-radius:8px; padding:12px 16px; color:#fde68a; font-size:0.87rem; margin:8px 0; }
.equiv-box { background:#1e293b; border:1px solid #22c55e; border-radius:8px; padding:12px 16px; color:#86efac; font-size:0.87rem; margin:8px 0; }
</style>
""", unsafe_allow_html=True)

EXPLANATIONS = {
    "eva": {
        "title": "Economic Value Added (EVA)",
        "what": ("EVA measures the dollar value created (or destroyed) in each period. "
                 "It equals NOPAT minus a charge for the capital employed — making the "
                 "opportunity cost of capital explicit."),
        "formula": "EVA = NOPAT − WACC × Capital_Invested\n       = (ROC − WACC) × Capital_Invested",
        "why": ("The EVA framework produces the same firm value as a DCF when applied "
                "consistently. Its advantage: it shows VALUE CREATION period by period. "
                "A firm with positive EVA is earning more than its cost of capital. "
                "A firm with negative EVA is destroying value even if it is profitable."),
        "source": "Damodaran, Ch 32, p.799; fcffeva.xls",
    },
    "distressed": {
        "title": "Distressed Firm Valuation",
        "what": ("Standard DCF assumes the firm operates indefinitely. For distressed firms "
                 "this is wrong — the DCF value must be adjusted for the probability that "
                 "the firm is sold or liquidated at a fire-sale price before reaching steady state."),
        "formula": "Adjusted_Value = GC_Value × (1−p) + Distress_Sale × p",
        "why": ("The distress probability comes from two sources: credit ratings (Moody's "
                "cumulative default rates) or firm age (BLS survival curves). The distress "
                "sale value is typically 50–70% of book asset value — well below going-concern "
                "value. The equity holder often gets nothing in distress because debt has priority."),
        "source": "Damodaran, Ch 22, p.556; Ch 30, p.727; fcffsimpleginzu.xlsx",
    },
    "financial": {
        "title": "Financial Firm Valuation",
        "what": ("Banks and insurers cannot be valued with FCFF because debt is their "
                 "raw material, not their capital source. The excess returns model directly "
                 "values equity: BV of equity + PV of excess returns (ROE above ke)."),
        "formula": "Value = Book_Equity + PV[(ROE − ke) × Book_Equity]\n        = Book_Equity + PV(Excess Returns)",
        "why": ("A bank with ROE = ke is worth its book value. A bank earning ROE > ke "
                "deserves a premium — the amount depends on how long it can sustain excess "
                "returns and how large they are. This is why high-quality banks trade at "
                "PBV > 1 and weak banks at PBV < 1."),
        "source": "Damodaran, Ch 21, p.519",
    },
    "normalise": {
        "title": "Earnings Normalisation",
        "what": ("For cyclical or temporarily-distressed firms, current earnings are "
                 "misleading as a valuation base. Damodaran uses three approaches to "
                 "estimate 'normal' earnings across a business cycle."),
        "formula": "Method 1: Average of last N years' earnings\n"
                   "Method 2: Average margin × current revenue\n"
                   "Method 3: Industry/historical ROA × current assets",
        "why": ("Method 2 (average margin × current revenue) is preferred because it "
                "adjusts for the firm's current scale. Method 1 can be distorted if the "
                "firm has grown significantly. Method 3 is most useful when the firm has "
                "negative earnings throughout the historical period."),
        "source": "Damodaran, Ch 22, p.541",
    },
}

def explain(key):
    e = EXPLANATIONS.get(key, {})
    if not e: return
    with st.expander(f"📖 {e['title']}", expanded=False):
        st.markdown(f"""<div class="explain-box">
<strong>What it is:</strong> {e['what']}<br><br>
<strong>Formula:</strong> <code>{e['formula']}</code><br><br>
<strong>Why it matters:</strong> {e['why']}<br><br>
<div style="font-size:0.72rem;color:#475569">📚 {e['source']}</div>
</div>""", unsafe_allow_html=True)

def badge(score, text, colour):
    short = text[:70] + "…" if len(text) > 70 else text
    return f'<span class="score-pill score-{colour}">Score {score}/10 — {short}</span>'

def score_eva(excess_return_pct):
    if excess_return_pct > 0.10:
        return 9, f"ROC is {excess_return_pct:.1%} above WACC — exceptional value creation", "green"
    elif excess_return_pct > 0.05:
        return 8, f"Healthy {excess_return_pct:.1%} excess return above WACC", "green"
    elif excess_return_pct > 0:
        return 6, f"Marginal excess return of {excess_return_pct:.1%} — just above cost of capital", "yellow"
    elif excess_return_pct > -0.03:
        return 4, f"ROC ≈ WACC — value-neutral growth", "yellow"
    else:
        return 2, f"ROC is {abs(excess_return_pct):.1%} below WACC — growth is destroying value", "red"

def score_distress(p):
    if p < 0.01:
        return 9, f"Negligible distress risk ({p:.2%})", "green"
    elif p < 0.05:
        return 7, f"Low distress probability ({p:.2%})", "green"
    elif p < 0.15:
        return 5, f"Moderate distress risk ({p:.2%}) — meaningful haircut to DCF value", "yellow"
    elif p < 0.35:
        return 3, f"High distress probability ({p:.2%}) — significant value at risk", "red"
    else:
        return 1, f"Very high distress risk ({p:.2%}) — equity may be near-worthless", "red"

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Settings")
    st.markdown('<span class="placeholder-badge">⚠ Placeholder data</span>', unsafe_allow_html=True)
    st.markdown("""<div style='font-size:0.75rem;color:#475569;line-height:1.7;margin-top:8px'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — NI, BV equity<br>
🔵 EDGAR — NOPAT, invested capital<br>
🔵 Module 01 → WACC, ke<br>
🔵 Module 02 → FCFF baseline
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("🔬 Special Cases")
st.markdown("**Chapters 21, 22, 30, 32** · EVA · Distressed firms · Financial firms · Earnings normalisation")
st.warning("⚠ Placeholder inputs throughout. Live data connection coming in the next phase.", icon="⚠️")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 EVA Framework",
    "⚠️ Distressed Firms",
    "🏦 Financial Firms",
    "📉 Normalise Earnings",
])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — EVA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## EVA Framework")
    st.markdown("Prove that DCF = Capital + PV(EVA). Source: `fcffeva.xls`")
    explain("eva")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Current year inputs**")
        init_capital = st.number_input("Initial invested capital ($m)", value=20_000.0, key="ev_ic")
        fcff_ref     = st.number_input("FCFF firm value (DCF cross-check, $m)", value=80_367.5, key="ev_fv",
                                        help="Paste the result from Module 02 to verify equivalence")
        st.markdown("**Terminal period**")
        term_nopat   = st.number_input("Terminal NOPAT ($m)",  value=12_080.0, key="ev_tn")
        term_wacc    = st.number_input("Terminal WACC",         value=0.1216, format="%.4f", key="ev_tw")
        term_roc     = st.number_input("Terminal ROC",          value=0.4169, format="%.4f", key="ev_tr")
        g_stable     = st.number_input("Stable growth rate",    value=0.06,   format="%.3f",  key="ev_g")

    with col2:
        st.markdown("**Year-by-year series** (paste comma-separated)")
        nopat_str   = st.text_area("NOPAT ($m), years 1–10",
            value="2977, 3722, 4652, 5815, 7269, 8517, 9654, 10575, 11181, 11396",
            height=80, key="ev_np")
        capital_str = st.text_area("Ending invested capital ($m), years 1–10",
            value="20314, 20706, 21197, 21810, 22576, 23579, 24782, 26151, 27661, 28975",
            height=80, key="ev_cp")
        wacc_str    = st.text_area("WACC, years 1–10",
            value="0.134, 0.134, 0.134, 0.134, 0.134, 0.131, 0.129, 0.126, 0.124, 0.122",
            height=80, key="ev_wc")

    if st.button("Calculate EVA →", type="primary", key="btn_eva"):
        def parse_floats(s):
            return [float(x.strip()) for x in s.split(",") if x.strip()]
        try:
            nopat_s   = parse_floats(nopat_str)
            capital_s = parse_floats(capital_str)
            wacc_s    = parse_floats(wacc_str)

            r = eva_valuation(
                initial_capital=init_capital,
                nopat_series=nopat_s,
                capital_series=capital_s,
                wacc_series=wacc_s,
                terminal_nopat=term_nopat,
                terminal_wacc=term_wacc,
                terminal_roc=term_roc,
                g_stable=g_stable,
                fcff_firm_value=fcff_ref,
            )

            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Firm Value (EVA)", f"${r.firm_value:,.0f}m")
            c2.metric("FCFF Cross-check", f"${r.fcff_firm_value:,.0f}m")
            diff_pct = abs(r.firm_value - r.fcff_firm_value) / r.fcff_firm_value * 100 if r.fcff_firm_value else 0
            c3.metric("Difference", f"{diff_pct:.2f}%",
                      help="Should be near zero — confirms DCF ≡ EVA")

            if diff_pct < 2:
                st.markdown('<div class="equiv-box">✓ EVA and FCFF values are equivalent — the two frameworks confirm each other.</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown('<div class="warning-box">⚠ Values differ by more than 2% — check that inputs are consistent across both models.</div>',
                            unsafe_allow_html=True)

            st.markdown(f"""<div class="explain-box">
<strong>Decomposition:</strong><br>
Initial invested capital: <strong>${r.initial_capital:,.0f}m</strong><br>
+ PV of explicit period EVAs: <strong>${r.pv_eva_total:,.0f}m</strong><br>
+ PV of terminal EVA: <strong>${r.pv_terminal_eva:,.0f}m</strong><br>
= Firm value: <strong>${r.firm_value:,.0f}m</strong>
</div>""", unsafe_allow_html=True)

            st.markdown("#### Year-by-year EVA")
            df = pd.DataFrame([{
                "Year":        row_y,
                "NOPAT ($m)":  f"{row_n:,.0f}",
                "WACC Charge": f"{row_w:,.0f}",
                "EVA ($m)":    f"{row_e:,.0f}",
                "ROC":         f"{row_r:.2%}",
                "PV(EVA)":     f"{row_p:,.0f}",
            } for row_y, row_n, row_w, row_e, row_r, row_p in zip(
                r.years, r.nopat, r.wacc_charge, r.eva, r.roc, r.pv_eva)])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Score avg EVA
            avg_eva_pct = sum(row_e/row_n for row_e, row_n in zip(r.eva, r.nopat) if row_n > 0) / len(r.eva)
            s, t, c = score_eva(avg_eva_pct * 0.5)  # rough excess return proxy
            st.markdown(badge(s, t, c), unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Distressed firms
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Distressed Firm Valuation")
    explain("distressed")

    sub1, sub2 = st.tabs(["By credit rating", "By firm age (BLS)"])

    with sub1:
        st.markdown("### Approach 1 — Default probability from credit rating")
        st.caption("Source: Moody's cumulative default rates by rating (fcffsimpleginzu.xlsx)")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Going-concern inputs**")
            gc_val   = st.number_input("Going-concern firm value ($m)", value=50_000.0, key="dr_gc")
            debt_d   = st.number_input("Debt outstanding ($m)",         value=35_000.0, key="dr_d")
            cash_d   = st.number_input("Cash ($m)",                     value=2_000.0,  key="dr_c")
            shares_d = st.number_input("Shares outstanding (m)",        value=1_000.0,  key="dr_sh")
            price_d  = st.number_input("Current price ($)",             value=0.0,      key="dr_pr")
        with col2:
            st.markdown("**Distress parameters**")
            rating   = st.selectbox("Current credit rating", RATING_NAMES, index=5, key="dr_rt")
            horizon  = st.slider("Default horizon (years)", 1, 5, 5, key="dr_hz")
            distress_val = st.number_input("Distress sale value ($m)",  value=28_000.0, key="dr_dv",
                                            help="Typical: 50–70% of book asset value")
            st.markdown("**Moody's default probability table**")
            prob_df = pd.DataFrame(
                {f"Year {y+1}": [f"{v:.2%}" for v in probs]
                 for y, probs in enumerate(zip(*DEFAULT_PROB_BY_RATING.values()))},
                index=RATING_NAMES,
            )
            st.dataframe(prob_df, use_container_width=True)

        if st.button("Calculate →", type="primary", key="btn_dr"):
            p = default_probability_from_rating(rating, horizon)
            r = distressed_firm_value(gc_val, debt_d, p, distress_val, shares_d, cash_d, rating, horizon)
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Default Prob", f"{r.distress_probability:.2%}")
            c2.metric("GC Value/Share", f"${r.value_per_share_gc:.2f}")
            c3.metric("Adjusted Value/Share", f"${r.value_per_share_adjusted:.2f}",
                      delta=f"{(r.value_per_share_adjusted/r.value_per_share_gc-1)*100:.1f}%")
            c4.metric("vs Price", f"{(r.value_per_share_adjusted/price_d-1)*100:+.1f}%" if price_d > 0 else "N/A")

            s, t, c = score_distress(p)
            st.markdown(badge(s, t, c), unsafe_allow_html=True)
            st.markdown(f"""<div class="explain-box">
<strong>Distress adjustment:</strong><br>
Going-concern firm value: ${r.going_concern_value:,.0f}m × (1 − {r.distress_probability:.2%}) = ${r.going_concern_value*(1-r.distress_probability):,.0f}m<br>
+ Distress sale proceeds: ${r.distress_sale_proceeds:,.0f}m × {r.distress_probability:.2%} = ${r.distress_sale_proceeds*r.distress_probability:,.0f}m<br>
= Adjusted firm value: <strong>${r.adjusted_value:,.0f}m</strong><br>
− Debt: ${r.debt_outstanding:,.0f}m + Cash: ${cash_d:,.0f}m = Equity: <strong>${r.equity_adjusted:,.0f}m</strong>
</div>""", unsafe_allow_html=True)

    with sub2:
        st.markdown("### Approach 2 — Survival probability from BLS data")
        st.caption("Source: Bureau of Labor Statistics firm survival rates by industry (fcffsimpleginzu.xlsx)")

        col1, col2 = st.columns(2)
        with col1:
            ind_bls  = st.selectbox("Industry", INDUSTRY_NAMES_SC, key="bls_ind")
            firm_age = st.slider("Firm age (years)", 0, 10, 3, key="bls_age")
            gc_bls   = st.number_input("Going-concern firm value ($m)", value=5_000.0, key="bls_gc")
            debt_bls = st.number_input("Debt ($m)", value=3_500.0, key="bls_d")
            cash_bls = st.number_input("Cash ($m)", value=200.0, key="bls_c")
            sh_bls   = st.number_input("Shares (m)", value=200.0, key="bls_sh")
            dv_bls   = st.number_input("Distress sale value ($m)", value=2_000.0, key="bls_dv")
        with col2:
            st.markdown("**BLS survival rates**")
            surv = SURVIVAL_BY_INDUSTRY[ind_bls]
            surv_df = pd.DataFrame({
                "Age (yrs)": list(range(len(surv))),
                "Survival rate": [f"{s:.1%}" for s in surv],
                "Failure rate": [f"{1-s:.1%}" for s in surv],
            })
            st.dataframe(surv_df, use_container_width=True, hide_index=True)

        if st.button("Calculate →", type="primary", key="btn_bls"):
            p_bls = default_probability_from_industry_age(ind_bls, firm_age)
            r_bls = distressed_firm_value(gc_bls, debt_bls, p_bls, dv_bls, sh_bls, cash_bls)
            c1, c2, c3 = st.columns(3)
            c1.metric("Failure prob", f"{p_bls:.2%}")
            c2.metric("GC Value/Share", f"${r_bls.value_per_share_gc:.2f}")
            c3.metric("Adjusted Value/Share", f"${r_bls.value_per_share_adjusted:.2f}",
                      delta=f"{(r_bls.value_per_share_adjusted/r_bls.value_per_share_gc-1)*100:.1f}%" if r_bls.value_per_share_gc > 0 else None)
            s, t, c = score_distress(p_bls)
            st.markdown(badge(s, t, c), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Financial firms
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Financial Firm Valuation")
    st.markdown("Banks, insurers, and other financial firms — valued via excess returns on equity.")
    explain("financial")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Current book equity**")
        bv_eq  = st.number_input("Book equity ($m)",         value=8_000.0, key="ff_bv")
        shares_ff = st.number_input("Shares outstanding (m)", value=500.0,  key="ff_sh")
        price_ff  = st.number_input("Current price ($)",      value=0.0,    key="ff_pr")
        st.markdown("**High-growth period**")
        roe_h  = st.number_input("ROE (high growth)",        value=0.18, format="%.3f", key="ff_rh")
        ke_h   = st.number_input("Cost of equity (high)",   value=0.11, format="%.3f", key="ff_kh")
        g_h    = st.number_input("Growth rate (high)",      value=0.10, format="%.3f", key="ff_gh")
        n_h    = int(st.number_input("High-growth years",   value=5, step=1,             key="ff_n"))
    with col2:
        st.markdown("**Stable period**")
        roe_s  = st.number_input("ROE (stable)",            value=0.12, format="%.3f", key="ff_rs")
        ke_s   = st.number_input("Cost of equity (stable)", value=0.10, format="%.3f", key="ff_ks")
        g_s    = st.number_input("Stable growth rate",      value=0.04, format="%.3f", key="ff_gs")

    if st.button("Calculate →", type="primary", key="btn_ff"):
        try:
            r = financial_firm_excess_returns(
                book_equity=bv_eq, roe_high=roe_h, ke_high=ke_h, g_high=g_h, n_high=n_h,
                roe_stable=roe_s, ke_stable=ke_s, g_stable=g_s, shares=shares_ff,
            )
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Book Equity", f"${r.book_equity:,.0f}m")
            c2.metric("PV Excess Returns", f"${r.pv_excess_returns:,.0f}m")
            c3.metric("Equity Value", f"${r.value_of_equity:,.0f}m")
            c4.metric("Value/Share", f"${r.value_per_share:.2f}",
                      delta=f"{(r.value_per_share/price_ff-1)*100:+.1f}% vs price" if price_ff > 0 else None)

            pbv = r.value_of_equity / r.book_equity
            s, t, c = score_eva(r.excess_return)
            st.markdown(badge(s, t, c), unsafe_allow_html=True)

            st.markdown(f"""<div class="explain-box">
<strong>Excess return:</strong> ROE of {roe_h:.2%} vs ke of {ke_h:.2%} = <strong>{r.excess_return:+.2%}</strong> per year on book equity<br>
<strong>PBV ratio:</strong> {pbv:.2f}× — {"justified by ROE above ke" if r.excess_return > 0 else "ROE is below ke; should trade below book"}<br><br>
{"<strong>Interpretation:</strong> The bank earns <strong>" + f"{r.excess_return:.2%}</strong>" + " above its cost of equity. Investors will pay a premium to book value of <strong>" + f"{pbv:.2f}×</strong>" + " to own this excess return stream." if r.excess_return > 0 else "<strong>Warning:</strong> ROE < ke. The bank destroys value each period. It should trade at a discount to book value."}
</div>""", unsafe_allow_html=True)
        except Exception as e:
            st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Earnings normalisation
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## Earnings Normalisation")
    st.markdown("For cyclical, temporarily-depressed, or negative-earnings firms.")
    explain("normalise")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Current year**")
        curr_earn = st.number_input("Current earnings ($m)",  value=-500.0,   key="nm_ce")
        curr_rev  = st.number_input("Current revenue ($m)",   value=15_000.0, key="nm_cr")
        curr_ast  = st.number_input("Current total assets ($m)", value=40_000.0, key="nm_ca")
        ind_roa   = st.number_input("Industry/historical ROA (optional)", value=0.05,
                                     format="%.3f", key="nm_roa", help="Leave 0 to skip ROA method")
    with col2:
        st.markdown("**Historical series** (comma-separated, oldest first)")
        hist_earn_str = st.text_area("Historical earnings ($m)", height=80, key="nm_he",
                                      value="-200, 100, 400, 600, 800, 1100, 1400, 1600")
        hist_rev_str  = st.text_area("Historical revenues ($m)", height=80, key="nm_hr",
                                      value="8000, 9500, 11000, 12500, 13500, 14000, 14500, 15000")

    if st.button("Normalise →", type="primary", key="btn_nm"):
        def parse_f(s): return [float(x.strip()) for x in s.split(",") if x.strip()]
        try:
            he = parse_f(hist_earn_str)
            hr = parse_f(hist_rev_str) if hist_rev_str.strip() else []
            roa = ind_roa if ind_roa > 0 else None
            result = normalise_earnings(curr_earn, he, curr_rev, hr, curr_ast, roa)

            st.divider()
            rows = [
                {"Method": "Current (reported) earnings",  "Earnings ($m)": f"{result['current_earnings']:,.0f}",  "Note": "May be distorted by cycle position"},
                {"Method": "Average of historical earnings","Earnings ($m)": f"{result.get('average_earnings', 'N/A'):,.0f}" if 'average_earnings' in result else "N/A", "Note": "Simple average — works for same-scale firms"},
                {"Method": "Average margin × current rev",  "Earnings ($m)": f"{result.get('margin_normalised', 'N/A'):,.0f}" if 'margin_normalised' in result else "N/A", "Note": f"Avg margin: {result.get('avg_margin', 0):.2%} × ${curr_rev:,.0f}m"},
                {"Method": "ROA × current assets",          "Earnings ($m)": f"{result.get('roa_normalised', 'N/A'):,.0f}" if 'roa_normalised' in result else "N/A", "Note": f"ROA: {roa:.2%} × ${curr_ast:,.0f}m" if roa else "Not provided"},
            ]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            rec = result['recommended']
            st.markdown(f"""<div class="explain-box">
<strong>Recommended normalised earnings: ${rec:,.0f}m</strong>
{"(average margin method)" if 'margin_normalised' in result else "(average earnings method)"}<br><br>
{"<strong>Note:</strong> Current earnings are negative — using normalised earnings is essential. Valuing this firm on current earnings would give a nonsensical result." if curr_earn < 0 else "<strong>Note:</strong> Current earnings differ from normalised — the firm is above or below its long-run average margin."}
</div>""", unsafe_allow_html=True)
        except Exception as e:
            st.error(str(e))

# Footer
st.divider()
st.markdown("""<div style="font-size:0.75rem;color:#475569;text-align:center;padding:12px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed., Ch 21 (financial firms), Ch 22 (neg. earnings),
Ch 30 (distressed firms), Ch 32 (EVA)<br>
Source files: fcffeva.xls, fcffsimpleginzu.xlsx (Failure Rate worksheet)
</div>""", unsafe_allow_html=True)
