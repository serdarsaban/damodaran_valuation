"""
pages/2_Cash_Flows.py
Damodaran Ch 9–10, 14–15: FCFF and FCFE valuation models
"""

import streamlit as st
import pandas as pd
import math
from fcff_models import (
    fcff_stable, fcff_2stage, fcff_3stage,
    fcfe_stable, fcfe_2stage, fcfe_3stage,
    FCFFValuationResult, FCFEValuationResult,
)

st.set_page_config(page_title="Cash Flow Valuation", page_icon="💵", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box {
    background: #1e293b; border-left: 3px solid #3b82f6;
    border-radius: 0 8px 8px 0; padding: 14px 18px;
    margin: 10px 0 18px 0; font-size: 0.88rem;
    line-height: 1.7; color: #cbd5e1;
}
.score-pill {
    display: inline-block; padding: 3px 12px;
    border-radius: 20px; font-size: 0.8rem; font-weight: 500; margin-top: 8px;
}
.score-green  { background: #14532d; color: #86efac; }
.score-yellow { background: #713f12; color: #fde68a; }
.score-red    { background: #7f1d1d; color: #fca5a5; }
.placeholder-badge {
    font-size: 0.72rem; padding: 2px 8px; border-radius: 4px;
    background: #3b2a0f; color: #fbbf24; display: inline-block; margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Explanations
# ─────────────────────────────────────────────────────────────────────────────

EXPLANATIONS = {
    "fcff": {
        "title": "Free Cash Flow to Firm (FCFF)",
        "what": ("The cash the business generates from operations after all "
                 "reinvestment, before any payments to debt or equity holders. "
                 "It belongs to everyone who has a claim on the firm."),
        "formula": "FCFF = EBIT × (1−t)  −  (CapEx − Depreciation)  −  ΔWorking Capital",
        "alt":     "= NOPAT  −  Net Capital Expenditure  −  ΔWorking Capital",
        "why": ("Because FCFF belongs to the whole firm, you discount it at WACC "
                "to get firm value, then subtract debt to get equity value. Works "
                "for any capital structure."),
        "source": "Damodaran, Ch 9–10, p.226–247",
    },
    "fcfe": {
        "title": "Free Cash Flow to Equity (FCFE)",
        "what": ("Cash left for equity holders after operating expenses, taxes, "
                 "reinvestment, and debt service (interest + principal − new borrowings)."),
        "formula": "FCFE = Net Income  −  (1−δ) × (CapEx − Depr)  −  (1−δ) × ΔWorking Capital",
        "alt": "where δ = debt financing ratio (new debt / total reinvestment)",
        "why": ("FCFE is discounted at ke. Gives equity value directly. "
                "Preferred when leverage is stable and predictable."),
        "source": "Damodaran, Ch 14, p.355",
    },
    "nopat": {
        "title": "NOPAT — Net Operating Profit After Tax",
        "what": ("EBIT × (1 − tax rate). The after-tax operating profit before "
                 "any financing effects. This is the cash available to reinvest and distribute."),
        "formula": "NOPAT = EBIT × (1 − t)",
        "why": "Starting point for all FCFF calculations.",
        "source": "Damodaran, Ch 9, p.228",
    },
    "reinvestment": {
        "title": "Reinvestment Rate",
        "what": ("The fraction of NOPAT the firm must reinvest to sustain growth. "
                 "A firm growing fast with a low reinvestment rate has a high-quality model."),
        "formula": "RIR = (Net CapEx + ΔWorking Capital) / NOPAT = g / ROC",
        "why": ("In the stable period, Damodaran always derives RIR from fundamentals: "
                "RIR = g_stable / ROC_stable. Growth is only valuable if ROC > WACC."),
        "source": "Damodaran, Ch 11, p.280",
    },
    "terminal_value": {
        "title": "Terminal Value",
        "what": ("The value of all cash flows beyond the explicit forecast period, "
                 "captured as a growing perpetuity. Typically 60–80% of total firm value."),
        "formula": "TV = FCFF_{n+1} / (WACC − g_stable)",
        "why": ("Small changes in g or WACC have enormous impact on terminal value. "
                "g_stable must be ≤ long-run GDP growth (~3–4% for developed markets). "
                "ROC_stable should converge toward WACC in a competitive economy."),
        "source": "Damodaran, Ch 12, p.303",
    },
    "model_choice": {
        "title": "When to use FCFF vs FCFE",
        "what": ("Both give the same equity value when consistently applied. "
                 "The choice is practical."),
        "formula": "Equity(FCFF) = [Σ PV(FCFF) + PV(TV)] − Debt + Cash",
        "alt":     "Equity(FCFE) = Σ PV(FCFE) + PV(TV) + Cash",
        "why": ("Use FCFF: leverage is changing, highly leveraged, or cyclical firm. "
                "Use FCFE: stable leverage, financial institutions, simple capital structure."),
        "source": "Damodaran, Ch 15, p.384",
    },
}

def explain(key):
    e = EXPLANATIONS.get(key, {})
    if not e: return
    with st.expander(f"📖 What is {e['title']}?", expanded=False):
        st.markdown(f"""
<div class="explain-box">
<strong>What it is:</strong> {e['what']}
<br><br>
<strong>Formula:</strong> <code>{e['formula']}</code>
{"<br><em>" + e.get('alt','') + "</em>" if e.get('alt') else ""}
<br><br>
<strong>Why it matters:</strong> {e['why']}
<br><br>
<div style="font-size:0.72rem;color:#475569">📚 {e['source']}</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def score_tv_pct(tv_pct):
    if tv_pct < 0.50:
        return 9, "Low TV dependence — most value from near-term cash flows. High confidence.", "green"
    elif tv_pct < 0.65:
        return 7, "Moderate TV dependence — typical for stable businesses.", "green"
    elif tv_pct < 0.80:
        return 5, "High TV dependence. Small changes in g or WACC have large impact.", "yellow"
    else:
        return 3, "Very high TV dependence (>80%). Valuation highly sensitive to stable-growth assumptions.", "red"

def score_reinvestment(rir):
    if rir < 0.2:
        return 9, "Very capital-efficient — low reinvestment needed for growth.", "green"
    elif rir < 0.4:
        return 7, "Moderate reinvestment. Good balance between growth and cash generation.", "green"
    elif rir < 0.6:
        return 5, "High reinvestment — significant capital needed to sustain growth.", "yellow"
    elif rir < 0.8:
        return 3, "Very high reinvestment. Free cash flows are thin relative to earnings.", "yellow"
    else:
        return 1, "Reinvestment rate > 80%. Nearly all earnings reinvested; minimal free cash.", "red"

def score_margin_of_safety(price, value):
    if price <= 0 or value <= 0:
        return 5, "Enter a price to compute margin of safety.", "yellow"
    ratio = value / price
    if ratio > 1.5:
        return 10, f"Large margin of safety — value is {ratio:.1f}× the price. Potentially deeply undervalued.", "green"
    elif ratio > 1.2:
        return 8, f"Good margin of safety — value is {ratio:.1f}× price.", "green"
    elif ratio > 0.9:
        return 6, f"Fairly valued — value and price broadly aligned ({ratio:.1f}×).", "yellow"
    elif ratio > 0.7:
        return 4, f"Mild overvaluation — price is {1/ratio:.1f}× intrinsic value.", "yellow"
    else:
        return 2, f"Significant overvaluation — price is {1/ratio:.1f}× intrinsic value.", "red"

def badge(score, interp, colour):
    short = interp[:65] + "…" if len(interp) > 65 else interp
    return f'<span class="score-pill score-{colour}">Score {score}/10 — {short}</span>'

# ─────────────────────────────────────────────────────────────────────────────
# Result renderers
# ─────────────────────────────────────────────────────────────────────────────

def render_fcff_result(r, price=0, shares=1):
    tv_pct = r.pv_terminal_value / r.value_of_firm if r.value_of_firm > 0 else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Value of Firm",   f"${r.value_of_firm:,.0f}m")
    c2.metric("Value of Equity", f"${r.value_of_equity:,.0f}m")
    c3.metric("Value / Share",   f"${r.value_per_share:,.2f}",
              delta=f"{(r.value_per_share/price-1)*100:+.1f}% vs price" if price > 0 else None)
    c4.metric("Terminal Value %", f"{tv_pct:.0%}")

    if price > 0:
        s, interp, col = score_margin_of_safety(price, r.value_per_share)
        st.markdown(badge(s, interp, col), unsafe_allow_html=True)
    s_tv, interp_tv, col_tv = score_tv_pct(tv_pct)
    st.markdown(badge(s_tv, interp_tv, col_tv), unsafe_allow_html=True)

    st.markdown(
        '<div class="explain-box">' +
        "<strong>Value bridge:</strong><br>" +
        f"PV high-growth FCFFs: <strong>${r.pv_fcff_highgrowth:,.0f}m</strong><br>" +
        f"PV terminal value: <strong>${r.pv_terminal_value:,.0f}m</strong> ({tv_pct:.0%} of firm value)<br>" +
        f"= Firm value: <strong>${r.value_of_firm:,.0f}m</strong><br>" +
        (f"− Debt: ${r.debt_mv:,.0f}m<br>" if r.debt_mv else "") +
        (f"+ Cash: ${r.cash:,.0f}m<br>" if r.cash else "") +
        (f"− Options: ${r.options_value:,.0f}m<br>" if r.options_value else "") +
        f"= Equity: <strong>${r.value_of_equity:,.0f}m</strong> ÷ {r.shares:,.0f}m shares" +
        f" = <strong>${r.value_per_share:,.2f} / share</strong></div>",
        unsafe_allow_html=True
    )
    explain("terminal_value")

    if len(r.yearly) > 1:
        st.markdown("#### Year-by-year cash flows")
        df = pd.DataFrame([{
            "Year":        row.year,
            "EBIT ($m)":   f"{row.ebit:,.0f}",
            "NOPAT ($m)":  f"{row.nopat:,.0f}",
            "Net CapEx":   f"{row.net_capex:,.0f}",
            "ΔWC ($m)":   f"{row.delta_wc:,.0f}",
            "RIR":         f"{row.reinvestment_rate:.1%}",
            "FCFF ($m)":   f"{row.fcff:,.0f}",
            "WACC":        f"{row.wacc:.2%}",
            "PV ($m)":     f"{row.pv_fcff:,.0f}",
        } for row in r.yearly])
        st.dataframe(df, use_container_width=True, hide_index=True)
        avg_rir = sum(row.reinvestment_rate for row in r.yearly) / len(r.yearly)
        s_r, interp_r, col_r = score_reinvestment(avg_rir)
        st.markdown(badge(s_r, f"Avg RIR {avg_rir:.0%} — {interp_r}", col_r), unsafe_allow_html=True)
    explain("reinvestment")


def render_fcfe_result(r, price=0):
    tv_pct = r.pv_terminal_value / r.value_of_equity_ops if r.value_of_equity_ops > 0 else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity (ops)",  f"${r.value_of_equity_ops:,.0f}m")
    c2.metric("Equity",        f"${r.value_of_equity:,.0f}m")
    c3.metric("Value / Share", f"${r.value_per_share:,.2f}",
              delta=f"{(r.value_per_share/price-1)*100:+.1f}% vs price" if price > 0 else None)
    if price > 0:
        s, interp, col = score_margin_of_safety(price, r.value_per_share)
        st.markdown(badge(s, interp, col), unsafe_allow_html=True)
    s_tv, interp_tv, col_tv = score_tv_pct(tv_pct)
    st.markdown(badge(s_tv, interp_tv, col_tv), unsafe_allow_html=True)

    st.markdown(
        '<div class="explain-box">' +
        "<strong>Value bridge:</strong><br>" +
        f"PV high-growth FCFEs: <strong>${r.pv_fcfe_highgrowth:,.0f}m</strong><br>" +
        f"PV terminal value: <strong>${r.pv_terminal_value:,.0f}m</strong> ({tv_pct:.0%})<br>" +
        f"= Equity (ops): <strong>${r.value_of_equity_ops:,.0f}m</strong><br>" +
        (f"+ Cash: ${r.cash:,.0f}m<br>" if r.cash else "") +
        f"= Equity: <strong>${r.value_of_equity:,.0f}m</strong> ÷ {r.shares:,.0f}m" +
        f" = <strong>${r.value_per_share:,.2f} / share</strong></div>",
        unsafe_allow_html=True
    )
    explain("terminal_value")
    if len(r.yearly) > 1:
        st.markdown("#### Year-by-year cash flows")
        df = pd.DataFrame([{
            "Year":        row.year,
            "Net Inc ($m)": f"{row.net_income:,.0f}",
            "Net CapEx":   f"{row.net_capex:,.0f}",
            "ΔWC ($m)":   f"{row.delta_wc:,.0f}",
            "Net Debt":    f"{row.net_debt_issued:,.0f}",
            "Eq. RIR":     f"{row.equity_reinv_rate:.1%}",
            "FCFE ($m)":   f"{row.fcfe:,.0f}",
            "ke":          f"{row.ke:.2%}",
            "PV ($m)":     f"{row.pv_fcfe:,.0f}",
        } for row in r.yearly])
        st.dataframe(df, use_container_width=True, hide_index=True)
    explain("reinvestment")

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Model settings")
    st.markdown('<span class="placeholder-badge">⚠ Placeholder data</span>', unsafe_allow_html=True)
    model_family = st.radio("Model type",
                             ["FCFF (firm → equity)", "FCFE (equity directly)"])
    is_fcff = "FCFF" in model_family
    stage = st.selectbox("Growth stages",
                         ["Stable (1-stage)",
                          "High growth + Stable (2-stage)",
                          "High growth + Transition + Stable (3-stage)"])
    st.markdown("---")
    price  = st.number_input("Current stock price ($)", value=0.0, min_value=0.0)
    shares = st.number_input("Shares outstanding (m)",  value=1_000.0)
    st.markdown("---")
    st.markdown("""<div style='font-size:0.75rem;color:#475569;line-height:1.7'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — NI, EBIT, CapEx, WC<br>
🔵 EDGAR 10-K — detailed cash flows<br>
🔵 Step 1 WACC — discount rates
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("💵 Cash Flow Valuation")
st.markdown(f"**{'FCFF' if is_fcff else 'FCFE'} Model — {stage}** · Damodaran Ch 9–10, 14–15")
st.warning("⚠ Showing placeholder inputs. Wire up EDGAR + yfinance for live data.", icon="⚠️")
explain("fcff" if is_fcff else "fcfe")
explain("model_choice")
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Input forms + Calculate
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Inputs")

if is_fcff:
    if "Stable" in stage and "2" not in stage and "3" not in stage:
        st.caption("Single-stage model — firm already in steady state")
        c1, c2, c3 = st.columns(3)
        ebit  = c1.number_input("EBIT ($m)",             value=1_535.0)
        tax   = c1.number_input("Tax rate",               value=0.36, format="%.2f")
        capex = c2.number_input("CapEx ($m)",             value=550.0)
        depr  = c2.number_input("Depreciation ($m)",      value=400.0)
        dwc   = c3.number_input("ΔWorking Capital ($m)",value=160.0)
        wacc  = c3.number_input("WACC",                   value=0.108, format="%.3f")
        g     = c3.number_input("Stable growth rate",     value=0.05,  format="%.3f")
        c1b, c2b = st.columns(2)
        debt_mv = c1b.number_input("Debt MV ($m)", value=0.0)
        cash_v  = c2b.number_input("Cash ($m)",    value=0.0)
        explain("nopat"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcff_stable(ebit=ebit, tax_rate=tax, capex=capex, depreciation=depr,
                            delta_wc=dwc, wacc=wacc, g=g,
                            debt_mv=debt_mv, cash=cash_v, shares=shares)
            st.divider(); st.markdown("## Results")
            render_fcff_result(r, price, shares)

    elif "2-stage" in stage:
        st.caption("High-growth period then stable terminal value")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Current financials**")
            ebit  = st.number_input("EBIT ($m)",             value=5_186.0)
            tax   = st.number_input("Tax rate",              value=0.285, format="%.3f")
            capex = st.number_input("CapEx ($m)",            value=2_152.0)
            depr  = st.number_input("Depreciation ($m)",     value=1_228.0)
            dwc   = st.number_input("ΔWC ($m)",          value=499.0)
            rev   = st.number_input("Revenues ($m)",         value=16_701.0)
            debt_mv     = st.number_input("Debt MV ($m)",    value=1_822.0)
            cash_v      = st.number_input("Cash ($m)",       value=500.0)
            options_val = st.number_input("Options ($m)",    value=1_500.0)
        with col2:
            st.markdown("**Growth & discount rates**")
            wacc_h = st.number_input("WACC (high growth)", value=0.0962, format="%.4f")
            g_high = st.number_input("Growth rate (high)", value=0.106,  format="%.3f")
            n_high = int(st.number_input("High-growth years", value=5, step=1))
            g_stab = st.number_input("Stable growth rate",  value=0.06,  format="%.3f")
            wacc_s = st.number_input("WACC (stable)",       value=0.0962,format="%.4f")
            roc_s  = st.number_input("Stable ROC",          value=0.12,  format="%.3f")
            wc_pct = st.number_input("WC as % of revenues", value=0.225, format="%.3f")
        explain("nopat"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcff_2stage(ebit=ebit, tax_rate=tax, capex=capex, depreciation=depr,
                            delta_wc=dwc, revenues=rev,
                            wacc_high=wacc_h, g_high=g_high, n_high=n_high,
                            g_stable=g_stab, wacc_stable=wacc_s, stable_roc=roc_s,
                            wc_pct_rev=wc_pct, debt_mv=debt_mv, cash=cash_v,
                            shares=shares, options_value=options_val)
            st.divider(); st.markdown("## Results")
            render_fcff_result(r, price, shares)

    else:
        st.caption("High growth → linear transition → stable. For high-growth firms with improving margins.")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Current financials**")
            rev    = st.number_input("Revenues ($m)",           value=12_406.0)
            ebit   = st.number_input("EBIT ($m)",               value=855.0)
            tax    = st.number_input("Tax rate",                 value=0.36,  format="%.2f")
            capex  = st.number_input("CapEx ($m)",              value=233.0)
            depr   = st.number_input("Depreciation ($m)",       value=298.0)
            dwc    = st.number_input("ΔWC ($m)",            value=115.0)
            wc_pct = st.number_input("WC as % of revenues",     value=0.075, format="%.3f")
            debt_mv     = st.number_input("Debt MV ($m)",       value=0.0)
            cash_v      = st.number_input("Cash ($m)",          value=850.0)
            options_val = st.number_input("Options ($m)",       value=1_500.0)
        with col2:
            st.markdown("**Growth & margin assumptions**")
            rev_g_h    = st.number_input("Revenue growth (high)",    value=0.30,  format="%.2f")
            cur_margin = st.number_input("Current EBIT margin",      value=0.069, format="%.3f")
            tgt_margin = st.number_input("Target EBIT margin",       value=0.30,  format="%.2f")
            stab_margin= st.number_input("Stable EBIT margin",       value=0.25,  format="%.2f")
            n_high     = int(st.number_input("High-growth years",    value=5, step=1))
            n_trans    = int(st.number_input("Transition years",     value=5, step=1))
            wacc_h     = st.number_input("WACC (high growth)",       value=0.134, format="%.3f")
            wacc_s     = st.number_input("WACC (stable)",            value=0.122, format="%.3f")
            g_stab     = st.number_input("Stable growth rate",       value=0.06,  format="%.3f")
            roc_s      = st.number_input("Stable ROC",               value=0.12,  format="%.3f")
        explain("nopat"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcff_3stage(revenues=rev, ebit=ebit, capex=capex, depreciation=depr,
                            delta_wc=dwc, tax_rate=tax, rev_growth_high=rev_g_h,
                            current_ebit_margin=cur_margin, target_ebit_margin=tgt_margin,
                            stable_ebit_margin=stab_margin,
                            n_high=n_high, n_transition=n_trans,
                            wacc_high=wacc_h, wacc_stable=wacc_s,
                            g_stable=g_stab, stable_roc=roc_s, wc_pct_rev=wc_pct,
                            debt_mv=debt_mv, cash=cash_v, shares=shares,
                            options_value=options_val)
            st.divider(); st.markdown("## Results")
            render_fcff_result(r, price, shares)

else:
    if "Stable" in stage and "2" not in stage and "3" not in stage:
        st.caption("Single-stage equity model")
        c1, c2, c3 = st.columns(3)
        ni     = c1.number_input("Net Income ($m/share)", value=5.45)
        capex  = c1.number_input("CapEx ($m/share)",      value=2.0)
        depr   = c2.number_input("Depreciation",          value=1.747)
        dwc    = c2.number_input("ΔWorking Capital",  value=0.6)
        debt_r = c2.number_input("Debt ratio (δ)",   value=0.30, format="%.2f")
        ke     = c3.number_input("Cost of equity (ke)",   value=0.1305, format="%.4f")
        g      = c3.number_input("Stable growth rate",    value=0.06, format="%.3f")
        roe    = c3.number_input("ROE (0 = use inputs)",  value=0.12, format="%.3f")
        cash_v = c1.number_input("Cash ($m)",             value=0.0)
        explain("fcfe"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcfe_stable(net_income=ni, capex=capex, depreciation=depr,
                            delta_wc=dwc, debt_ratio=debt_r, ke=ke, g=g,
                            roe=roe if roe > 0 else None,
                            cash=cash_v, shares=shares)
            st.divider(); st.markdown("## Results")
            render_fcfe_result(r, price)

    elif "2-stage" in stage:
        st.caption("2-stage FCFE")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Current financials**")
            ni     = st.number_input("Net Income ($m)",         value=457.41)
            capex  = st.number_input("CapEx ($m)",              value=315.5)
            depr   = st.number_input("Depreciation ($m)",       value=255.5)
            dwc    = st.number_input("ΔWC ($m)",            value=106.0)
            debt_r = st.number_input("Debt ratio (δ)",     value=0.209, format="%.3f")
            cash_v = st.number_input("Cash ($m)",               value=398.8)
            opts   = st.number_input("Options ($m)",            value=0.0)
        with col2:
            st.markdown("**Growth & rates**")
            ke_h   = st.number_input("ke (high growth)",        value=0.0956, format="%.4f")
            g_h    = st.number_input("Growth rate (high)",      value=0.098,  format="%.3f")
            n_h    = int(st.number_input("High-growth years",   value=10, step=1))
            roe_h  = st.number_input("ROE (high growth)",       value=0.326,  format="%.3f")
            g_s    = st.number_input("Stable growth rate",      value=0.04,   format="%.3f")
            ke_s   = st.number_input("ke (stable)",             value=0.0956, format="%.4f")
            roe_s  = st.number_input("ROE (stable)",            value=0.10,   format="%.3f")
        explain("fcfe"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcfe_2stage(net_income=ni, capex=capex, depreciation=depr,
                            delta_wc=dwc, debt_ratio=debt_r,
                            ke_high=ke_h, g_high=g_h, n_high=n_h,
                            g_stable=g_s, ke_stable=ke_s,
                            roe_stable=roe_s, roe_high=roe_h,
                            cash=cash_v, shares=shares, options_value=opts)
            st.divider(); st.markdown("## Results")
            render_fcfe_result(r, price)

    else:
        st.caption("3-stage FCFE — for high-growth firms with declining ROE")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Current financials**")
            ni     = st.number_input("Net Income ($m)",         value=700.0)
            capex  = st.number_input("CapEx ($m)",              value=400.0)
            depr   = st.number_input("Depreciation ($m)",       value=250.0)
            dwc    = st.number_input("ΔWC ($m)",            value=120.0)
            debt_r = st.number_input("Debt ratio (δ)",     value=0.20, format="%.2f")
            cash_v = st.number_input("Cash ($m)",               value=200.0)
        with col2:
            st.markdown("**Growth & rates**")
            ke_h   = st.number_input("ke (high growth)",        value=0.12,  format="%.3f")
            g_h    = st.number_input("Growth rate (high)",      value=0.15,  format="%.3f")
            n_h    = int(st.number_input("High-growth years",   value=5, step=1))
            n_tr   = int(st.number_input("Transition years",    value=5, step=1))
            roe_h  = st.number_input("ROE (high growth)",       value=0.25,  format="%.3f")
            g_s    = st.number_input("Stable growth rate",      value=0.04,  format="%.3f")
            ke_s   = st.number_input("ke (stable)",             value=0.09,  format="%.3f")
            roe_s  = st.number_input("ROE (stable)",            value=0.10,  format="%.3f")
        explain("fcfe"); explain("reinvestment")
        if st.button("Calculate →", type="primary"):
            r = fcfe_3stage(net_income=ni, capex=capex, depreciation=depr,
                            delta_wc=dwc, debt_ratio=debt_r,
                            ke_high=ke_h, g_high=g_h, n_high=n_h,
                            n_transition=n_tr, g_stable=g_s, ke_stable=ke_s,
                            roe_high=roe_h, roe_stable=roe_s,
                            cash=cash_v, shares=shares)
            st.divider(); st.markdown("## Results")
            render_fcfe_result(r, price)

st.divider()
st.markdown("""<div style="font-size:0.75rem;color:#475569;text-align:center;padding:12px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed., Ch 9–10 (FCFF), Ch 14–15 (FCFE)<br>
Source files: fcffst.xls, fcff2st.xls, fcff3st.xls, fcfest.xls, fcfeginzu.xls
</div>""", unsafe_allow_html=True)
