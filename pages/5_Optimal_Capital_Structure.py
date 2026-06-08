"""pages/5_Optimal_Capital_Structure.py — Optimal Capital Structure (Ch 15)"""
import streamlit as st
import pandas as pd
from optimal_capital_structure import (
    optimal_capital_structure, OptimalCapitalStructureResult,
    _TABLE_NAMES,
)

st.set_page_config(page_title="Optimal Capital Structure", page_icon="🏗️", layout="wide")

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
.result-card { background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:20px 24px; margin-bottom:12px; }
.result-label { font-size:0.7rem; text-transform:uppercase; letter-spacing:2px; color:#64748b; margin-bottom:4px; }
.result-value { font-size:2rem; font-family:'DM Serif Display',serif; color:#f1f5f9; }
.optimal-row { background:#14532d !important; }
.current-row { background:#1e3a5f !important; }
</style>
""", unsafe_allow_html=True)

EXPLANATIONS = {
    "optimal_cs": {
        "title": "Optimal Capital Structure",
        "what": ("The debt ratio that minimises the weighted average cost of capital (WACC) "
                 "and therefore maximises firm value. Every dollar of debt adds a tax shield "
                 "benefit but also increases the probability of financial distress."),
        "formula": "Optimal D/(D+E) = argmin WACC = argmax [FCFF × (1+g) / (WACC − g)]",
        "why": ("Damodaran's method sweeps debt ratios from 0% to 90%, computing a new "
                "synthetic rating and WACC at each level. The optimal is where firm value "
                "peaks — not necessarily where WACC is lowest, because indirect bankruptcy "
                "costs can reduce EBITDA as the rating falls."),
        "source": "Damodaran, Ch 15, p.395; capstru.xlsx",
    },
    "bankruptcy_costs": {
        "title": "Indirect Bankruptcy Costs",
        "what": ("As the credit rating falls, customers become reluctant to sign long-term "
                 "contracts, suppliers demand shorter payment terms, and employees leave. "
                 "This reduces operating income — even before any actual default."),
        "formula": "Adjusted_EBITDA = Base_EBITDA × (1 + drop_pct_for_rating)",
        "why": ("The EBITDA haircuts by rating band (from capstru.xlsx): "
                "A− = −2%, BBB = −10%, BB+/BB/B+/B = −20%, B− = −25%, "
                "CCC/CC/C = −40%, D = −50%. "
                "These are Damodaran's estimates of operating income loss from financial "
                "distress perception — distinct from the direct costs of bankruptcy."),
        "source": "Damodaran, capstru.xlsx → Default Spreads and Ratios sheet",
    },
    "interest_limit": {
        "title": "Interest Deduction Constraint",
        "what": ("Under US tax rules (TCJA 2017), interest deductions are capped at 30% "
                 "of EBITDA. When a firm's interest expense exceeds this, the marginal "
                 "tax benefit of additional debt is reduced."),
        "formula": "Max_deductible_interest = 30% × EBITDA; effective_t = t × (max_deductible / interest)",
        "why": ("This constraint makes high-leverage strategies less tax-efficient than "
                "classic Modigliani-Miller theory suggests. At very high debt levels, the "
                "incremental tax shield can approach zero."),
        "source": "Damodaran, capstru.xlsx → Inputs sheet, row 30–32",
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

def score_debt_position(current_dr, optimal_dr):
    gap = abs(current_dr - optimal_dr)
    direction = "over-levered" if current_dr > optimal_dr else "under-levered"
    if gap < 0.03:
        return 9, f"Near-optimal — current debt ratio within 3% of optimal", "green"
    elif gap < 0.08:
        return 7, f"Modestly {direction} — {gap:.0%} away from optimal", "yellow"
    elif gap < 0.15:
        return 5, f"Noticeably {direction} — {gap:.0%} from optimal, meaningful cost of capital impact", "yellow"
    else:
        return 2, f"Significantly {direction} — {gap:.0%} from optimal, large value leakage", "red"

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Settings")
    st.markdown('<span class="placeholder-badge">⚠ Disney 2023 placeholder</span>', unsafe_allow_html=True)
    firm_type = st.selectbox("Firm type", [1, 2, 3],
                              format_func=lambda x: _TABLE_NAMES[x])
    apply_bc = st.checkbox("Include indirect bankruptcy costs", value=False)
    apply_il = st.checkbox("Apply interest deduction limit (30% EBITDA)", value=False)
    st.markdown("---")
    steps = st.selectbox("Debt ratio step size", [5, 10, 20],
                          format_func=lambda x: f"{x}% steps", index=1)
    st.markdown("---")
    st.markdown("""<div style='font-size:0.75rem;color:#475569;line-height:1.7'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — equity MV, beta<br>
🔵 EDGAR — EBITDA, debt, interest<br>
🔵 Module 01 → rf, ERP, kd
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("🏗️ Optimal Capital Structure")
st.markdown("**Chapter 15** · Debt ratio sweep · Synthetic ratings · Bankruptcy costs · Repurchase analysis")
st.warning("⚠ Pre-loaded with Disney 2023 (reference case from capstru.xlsx). Replace inputs for your firm.", icon="⚠️")
explain("optimal_cs")
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Inputs")
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Income statement**")
    ebitda      = st.number_input("EBITDA ($m)",           value=11_767.0)
    depreciation= st.number_input("Depreciation ($m)",     value=5_200.0)
    ebit        = st.number_input("EBIT ($m)",             value=6_567.0,
                                   help="Enter adjusted EBIT (after lease/R&D adjustments if needed)")
    interest    = st.number_input("Interest expense ($m)", value=1_653.0)
    tax_rate    = st.number_input("Marginal tax rate",     value=0.25, format="%.2f")
    fcff        = st.number_input("Current FCFF ($m)",     value=4_812.25,
                                   help="Used to anchor the firm value perpetuity")

with col2:
    st.markdown("**Market data**")
    equity_mv   = st.number_input("Market cap ($m)",         value=183_230.0)
    debt_mv     = st.number_input("Debt MV ($m)",            value=44_850.0)
    beta        = st.number_input("Levered beta",            value=1.02)
    rf          = st.number_input("Risk-free rate",          value=0.039, format="%.3f")
    erp         = st.number_input("Equity risk premium",     value=0.0661, format="%.4f")
    actual_kd   = st.number_input("Actual pre-tax kd (lock current row)",
                                   value=0.069, format="%.3f",
                                   help="Company's actual cost of debt — locks the current debt ratio row to avoid synthetic rating distortion")

with col3:
    st.markdown("**Firm & shares**")
    company     = st.text_input("Company name", value="Disney")
    cash        = st.number_input("Cash ($m)", value=11_615.0)
    shares      = st.number_input("Shares outstanding (m)", value=1_826.82)
    price       = st.number_input("Current stock price ($)", value=100.30)
    g_stable    = st.number_input("Stable growth rate", value=0.039, format="%.3f",
                                   help="Damodaran uses rf as stable growth rate in capstru.xlsx")

if apply_bc:
    explain("bankruptcy_costs")
if apply_il:
    explain("interest_limit")

debt_ratios = [d / 100 for d in range(0, 101, steps)]

# ─────────────────────────────────────────────────────────────────────────────
# Calculate
# ─────────────────────────────────────────────────────────────────────────────
if st.button("Calculate Optimal Structure →", type="primary"):
    try:
        result = optimal_capital_structure(
            ebitda=ebitda, depreciation=depreciation, ebit=ebit,
            interest_expense=interest, tax_rate=tax_rate,
            equity_mv=equity_mv, debt_mv=debt_mv,
            beta_levered=beta, rf=rf, erp=erp,
            fcff=fcff, g_stable=g_stable,
            firm_type=firm_type,
            apply_bankruptcy_costs=apply_bc,
            apply_interest_limit=apply_il,
            shares_outstanding=shares,
            current_price=price,
            cash=cash,
            lock_current_kd=actual_kd,
            company=company,
            debt_ratios=debt_ratios,
        )

        st.divider()
        st.markdown(f"## Results — {result.company}")

        # ── Top metrics ──────────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current D/(D+E)", f"{result.current_debt_ratio:.1%}")
        c2.metric("Optimal D/(D+E)", f"{result.optimal_debt_ratio:.1%}",
                  delta=f"{(result.optimal_debt_ratio-result.current_debt_ratio)*100:+.1f}pp")
        c3.metric("Current WACC", f"{result.current_wacc:.2%}")
        c4.metric("Optimal WACC", f"{result.optimal_wacc:.2%}",
                  delta=f"{(result.optimal_wacc-result.current_wacc)*100:+.2f}pp")

        c1b, c2b, c3b, c4b = st.columns(4)
        c1b.metric("Current Firm Value", f"${result.current_firm_value:,.0f}m")
        c2b.metric("Optimal Firm Value", f"${result.optimal_firm_value:,.0f}m",
                   delta=f"+${result.value_gain:,.0f}m")
        c3b.metric("Current Price", f"${result.current_price:.2f}")
        c4b.metric("Optimal Price/Share",
                   f"${result.optimal_price_per_share:.2f}" if result.optimal_price_per_share > 0 else "N/A",
                   delta=f"{(result.optimal_price_per_share/result.current_price-1)*100:+.1f}%" if result.current_price > 0 and result.optimal_price_per_share > 0 else None)

        # Score
        s, t, c = score_debt_position(result.current_debt_ratio, result.optimal_debt_ratio)
        st.markdown(badge(s, t, c), unsafe_allow_html=True)

        # ── Interpretation ───────────────────────────────────────────────────
        direction = "over-levered" if result.current_debt_ratio > result.optimal_debt_ratio else "under-levered"
        action = ("reduce debt" if direction == "over-levered" else "issue more debt and repurchase shares")
        st.markdown(f"""<div class="explain-box">
<strong>Interpretation:</strong><br>
{company} is currently <strong>{direction}</strong> — its debt ratio of {result.current_debt_ratio:.1%}
{"exceeds" if direction == "over-levered" else "is below"} the optimal {result.optimal_debt_ratio:.1%}.
The recommended action is to <strong>{action}</strong>.<br><br>
{"<strong>Repurchase analysis:</strong> At the optimal structure, " + company + " would issue $" + f"{result.new_debt_issued:,.0f}m" + " in new debt and use the proceeds to repurchase approximately " + f"{result.shares_repurchased:,.0f}m shares" + " at the current price of $" + f"{result.current_price:.2f}" + ". The remaining shares would be worth $" + f"{result.optimal_price_per_share:.2f}" + " each — a gain of " + f"{(result.optimal_price_per_share/result.current_price-1)*100:+.1f}%" + "." if result.new_debt_issued > 0 and result.current_price > 0 else ""}
</div>""", unsafe_allow_html=True)

        # ── Sweep table ──────────────────────────────────────────────────────
        st.markdown("### Full debt ratio sweep")

        rows = []
        for r in result.sweep:
            is_opt = abs(r.debt_ratio - result.optimal_debt_ratio) < 0.001
            is_cur = abs(r.debt_ratio - result.current_debt_ratio) < 0.001
            tag = " ◀ OPTIMAL" if is_opt else (" ◀ current" if is_cur else "")
            rows.append({
                "D/(D+E)":    f"{r.debt_ratio:.0%}{tag}",
                "$ Debt ($m)": f"${r.dollar_debt:,.0f}",
                "Beta":        f"{r.beta_levered:.3f}",
                "ke":          f"{r.ke:.2%}",
                "ICR":         f"{r.icr:.2f}×" if r.icr < 1000 else "∞",
                "Rating":      r.rating,
                "kd (pre-tax)":f"{r.kd_pretax:.2%}",
                "WACC":        f"{r.wacc:.3%}",
                "Firm Value":  f"${r.firm_value:,.0f}m" if r.firm_value < 1e12 else "∞",
            })

        df = pd.DataFrame(rows)
        # Highlight optimal and current rows
        optimal_idx = next((i for i, r in enumerate(result.sweep)
                           if abs(r.debt_ratio - result.optimal_debt_ratio) < 0.001), None)

        st.dataframe(df, use_container_width=True, hide_index=True)

        # ── WACC chart data ──────────────────────────────────────────────────
        st.markdown("### WACC & Firm Value by Debt Ratio")
        chart_df = pd.DataFrame([{
            "Debt Ratio (%)": int(r.debt_ratio * 100),
            "WACC (%)": round(r.wacc * 100, 3),
            "Firm Value ($m)": round(r.firm_value, 0) if r.firm_value < 1e12 else None,
        } for r in result.sweep if r.firm_value < 1e12])

        col_wacc, col_val = st.columns(2)
        with col_wacc:
            st.markdown("**WACC across debt ratios**")
            st.line_chart(chart_df.set_index("Debt Ratio (%)")["WACC (%)"])
        with col_val:
            st.markdown("**Firm value across debt ratios**")
            st.line_chart(chart_df.set_index("Debt Ratio (%)")["Firm Value ($m)"])

        # ── Rating transition points ─────────────────────────────────────────
        st.markdown("### Rating transitions")
        st.caption("Points where the credit rating changes — these drive the kd step function")

        prev_rating = None
        transitions = []
        for r in result.sweep:
            if r.rating != prev_rating:
                transitions.append({
                    "At D/(D+E)":   f"{r.debt_ratio:.0%}",
                    "Rating":        r.rating,
                    "kd (pre-tax)": f"{r.kd_pretax:.2%}",
                    "EBITDA haircut": f"{0:.0%}",
                })
                prev_rating = r.rating

        st.dataframe(pd.DataFrame(transitions), use_container_width=True, hide_index=True)

    except ValueError as e:
        st.error(str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""<div style="font-size:0.75rem;color:#475569;text-align:center;padding:12px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed., Ch 15 (Optimal Capital Structure)<br>
Source file: capstru.xlsx (Disney 2023 reference case) · Spreads: Jan 2026 vintage
</div>""", unsafe_allow_html=True)
