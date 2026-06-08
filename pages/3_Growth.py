"""pages/3_Growth.py — Growth & Terminal Value (Ch 11–12)"""
import streamlit as st
import pandas as pd
import math
from growth_models import (
    estimate_growth, terminal_value_gordon,
    benchmark_vs_industry, INDUSTRY_NAMES, INDUSTRY_DATA,
)

st.set_page_config(page_title="Growth & Terminal Value", page_icon="📈", layout="wide")

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
.check-pass { background:#14532d; color:#86efac; border-radius:8px; padding:10px 14px; margin:6px 0; font-size:0.87rem; }
.check-fail { background:#7f1d1d; color:#fca5a5; border-radius:8px; padding:10px 14px; margin:6px 0; font-size:0.87rem; }
.score-pill { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.8rem; font-weight:500; margin-top:6px; }
.score-green  { background:#14532d; color:#86efac; }
.score-yellow { background:#713f12; color:#fde68a; }
.score-red    { background:#7f1d1d; color:#fca5a5; }
.quartile-bar-wrap { background:#1e293b; border-radius:6px; height:10px; width:100%; position:relative; margin:4px 0 12px 0; }
.placeholder-badge { font-size:0.72rem; padding:2px 8px; border-radius:4px; background:#3b2a0f; color:#fbbf24; display:inline-block; margin-bottom:6px; }
.tv-warning { background:#292524; border:1px solid #78350f; border-radius:8px; padding:12px 16px; color:#fde68a; font-size:0.87rem; margin:8px 0; }
</style>
""", unsafe_allow_html=True)

EXPLANATIONS = {
    "fundamental_g": {
        "title": "Fundamental Growth Rate",
        "what": ("Growth derived from what the firm actually does — how much it earns on its "
                 "invested capital and how much it reinvests. This is Damodaran's preferred "
                 "approach for long-term growth."),
        "formula": "g = ROC × Reinvestment_Rate    (firm)\ng = ROE × Retention_Ratio    (equity)",
        "why": ("Growth only creates value when ROC > WACC. A firm growing at 20% with "
                "ROC = 5% is destroying value. The fundamental approach forces you to "
                "connect growth to reinvestment — you can't grow for free."),
        "source": "Damodaran, Ch 11, p.278",
    },
    "historical_g": {
        "title": "Historical Growth Rate",
        "what": ("The compound annual growth rate (CAGR) of earnings or revenues over a "
                 "historical period. Simple to compute but often misleading — it reflects "
                 "the past, not necessarily the future."),
        "formula": "g = (EPS_n / EPS_0)^(1/n) − 1   [geometric mean]",
        "why": ("Damodaran prefers geometric mean over arithmetic mean because the arithmetic "
                "average overstates expected growth when earnings are volatile. Historical "
                "growth is most useful as a sanity check, not a primary estimate."),
        "source": "Damodaran, Ch 11, p.271",
    },
    "analyst_g": {
        "title": "Analyst Growth Estimates",
        "what": ("Consensus forecasts from sell-side analysts, typically for 1–5 years. "
                 "These incorporate information not in the financial statements — management "
                 "guidance, industry intelligence, product pipeline."),
        "formula": "Typically sourced from Bloomberg, FactSet, or I/B/E/S consensus",
        "why": ("Analyst estimates are most valuable in the near term (1–3 years) when "
                "analysts have specific insights. They become less reliable beyond 3–5 years. "
                "Studies show analyst estimates are systematically optimistic — apply judgment."),
        "source": "Damodaran, Ch 11, p.282",
    },
    "terminal_value": {
        "title": "Terminal Value",
        "what": ("The present value of all cash flows beyond the explicit forecast period, "
                 "expressed as a single number at the end of the forecast. Typically 60–80% "
                 "of total firm value in a DCF."),
        "formula": "TV = FCFF_{n+1} / (WACC − g_stable)",
        "why": ("The terminal value is where most DCF mistakes are made. The three most "
                "common errors: (1) using g > rf, (2) assuming ROC >> WACC forever, "
                "(3) not adjusting the discount rate downward for the now-mature firm. "
                "The sensitivity table below shows how much TV varies with assumptions."),
        "source": "Damodaran, Ch 12, p.303",
    },
    "roc": {
        "title": "Return on Capital (ROC)",
        "what": ("The after-tax operating return the firm earns on its invested capital. "
                 "This is the single most important input for growth quality — high growth "
                 "with high ROC creates value; high growth with low ROC destroys it."),
        "formula": "ROC = EBIT × (1−t) / (Book_Equity + Book_Debt)",
        "why": ("In the stable terminal period, Damodaran recommends setting ROC = WACC "
                "(implying zero excess returns). Only firms with genuine, durable competitive "
                "advantage can sustain ROC > WACC indefinitely."),
        "source": "Damodaran, Ch 11, p.280",
    },
}

def explain(key):
    e = EXPLANATIONS.get(key, {})
    if not e: return
    with st.expander(f"📖 What is {e['title']}?", expanded=False):
        st.markdown(f"""<div class="explain-box">
<strong>What it is:</strong> {e['what']}<br><br>
<strong>Formula:</strong> <code>{e['formula']}</code><br><br>
<strong>Why it matters:</strong> {e['why']}<br><br>
<div style="font-size:0.72rem;color:#475569">📚 {e['source']}</div>
</div>""", unsafe_allow_html=True)

def badge(score, text, colour):
    short = text[:70] + "…" if len(text) > 70 else text
    return f'<span class="score-pill score-{colour}">Score {score}/10 — {short}</span>'

def score_growth(g, ind_median=None):
    if ind_median and g > ind_median * 3:
        return 3, "Far above industry median — verify this is sustainable", "red"
    elif ind_median and g > ind_median * 1.5:
        return 6, "Above industry median — optimistic but not implausible", "yellow"
    elif g > 0.30:
        return 4, "Very high growth (>30%) — very few firms sustain this", "yellow"
    elif g > 0.15:
        return 7, "High growth — realistic for early-stage or disruptive firms", "green"
    elif g > 0.05:
        return 8, "Moderate growth — well within normal corporate range", "green"
    elif g > 0:
        return 7, "Low growth — appropriate for mature, stable businesses", "green"
    else:
        return 5, "Negative growth — declining firm or temporary trough", "yellow"

def score_roc(roc, wacc):
    excess = roc - wacc
    if excess > 0.15:
        return 9, f"ROC is {excess:.1%} above WACC — strong value creation", "green"
    elif excess > 0.05:
        return 8, f"ROC exceeds WACC by {excess:.1%} — healthy returns", "green"
    elif excess > 0:
        return 6, f"ROC marginally above WACC ({excess:.1%}) — limited value creation", "yellow"
    elif excess > -0.03:
        return 4, f"ROC ≈ WACC — firm earns its cost of capital but little more", "yellow"
    else:
        return 2, f"ROC below WACC by {abs(excess):.1%} — growth is destroying value", "red"

def quartile_marker(value, q1, med, q3, fmt=".1%"):
    """Render a simple text-based quartile position indicator."""
    total_range = q3 - q1 if q3 > q1 else 1
    pct = max(0, min(100, (value - q1) / total_range * 100)) if total_range > 0 else 50
    label = "bottom quartile" if value < q1 else ("2nd quartile" if value < med else ("3rd quartile" if value < q3 else "top quartile"))
    bar = "▓" * int(pct / 10) + "░" * (10 - int(pct / 10))
    return f"`{value:{fmt}}` |{bar}| {label}  _(Q1:{q1:{fmt}} · Med:{med:{fmt}} · Q3:{q3:{fmt}})_"


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Settings")
    st.markdown('<span class="placeholder-badge">⚠ Placeholder data</span>', unsafe_allow_html=True)
    industry = st.selectbox("Industry", ["(None)"] + INDUSTRY_NAMES)
    industry = None if industry == "(None)" else industry
    rf = st.number_input("Risk-free rate", value=0.045, format="%.3f")
    gdp_g = st.number_input("Long-run GDP growth", value=0.025, format="%.3f",
                             help="Used in terminal value consistency checks")
    st.markdown("---")
    st.markdown("""<div style='font-size:0.75rem;color:#475569;line-height:1.7'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — historical EPS/revenue series<br>
🔵 EDGAR — book equity, debt, CapEx<br>
🔵 Module 01 WACC → feeds here
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("📈 Growth & Terminal Value")
st.markdown("**Chapter 11–12** · Three growth approaches · Terminal value consistency · Industry benchmarks")
st.warning("⚠ Placeholder inputs. Live connection to yfinance + EDGAR coming soon.", icon="⚠️")
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Tab layout: Growth | Terminal Value | Industry Benchmark
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Growth Estimation", "🔭 Terminal Value", "🏭 Industry Benchmark"])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Growth estimation
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## Growth estimation")
    st.markdown("Three approaches — Damodaran recommends using all three as cross-checks.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### Fundamental")
        st.caption("From ROC × reinvestment rate")
        ebit       = st.number_input("EBIT ($m)",               value=5_186.0, key="g_ebit")
        tax_rate   = st.number_input("Tax rate",                value=0.285,   key="g_tax",   format="%.3f")
        net_capex  = st.number_input("Net CapEx ($m)",          value=924.0,   key="g_ncx")
        delta_wc   = st.number_input("ΔWorking Capital ($m)",   value=499.0,   key="g_dwc")
        book_eq    = st.number_input("Book Equity ($m)",        value=12_000.0,key="g_beq")
        book_debt  = st.number_input("Book Debt ($m)",          value=1_822.0, key="g_bdt")
        net_income = st.number_input("Net Income ($m)",         value=3_200.0, key="g_ni")
        dividends  = st.number_input("Dividends ($m)",          value=800.0,   key="g_div")
        wacc_input = st.number_input("WACC (for ROC scoring)",  value=0.096,   key="g_wacc",  format="%.3f")
        explain("fundamental_g"); explain("roc")

    with col2:
        st.markdown("### Historical")
        st.caption("CAGR of past EPS or revenues")
        st.markdown("**EPS history** (oldest → newest, comma-separated)")
        eps_str = st.text_input("EPS values", value="2.10, 2.40, 2.80, 3.10, 3.60", key="g_eps")
        st.markdown("**Revenue history** (optional)")
        rev_str = st.text_input("Revenue values", value="", key="g_rev",
                                placeholder="e.g. 10000, 11200, 12500, 14100, 15800")
        explain("historical_g")

    with col3:
        st.markdown("### Analyst estimate")
        st.caption("Consensus sell-side forecast")
        analyst_g = st.number_input("Analyst growth estimate", value=0.12, format="%.3f", key="g_anal",
                                     help="From Bloomberg/FactSet consensus. Leave 0 if unavailable.")
        analyst_g = analyst_g if analyst_g > 0 else None
        st.markdown("**Blend weights**")
        w_hist = st.slider("Historical weight", 0, 100, 25, key="g_wh")
        w_anal = st.slider("Analyst weight",    0, 100, 50, key="g_wa")
        w_fund = 100 - w_hist - w_anal
        st.caption(f"Fundamental weight: {w_fund}%")
        if w_fund < 0:
            st.error("Weights exceed 100% — reduce historical or analyst weight")
        explain("analyst_g")

    if st.button("Estimate Growth →", type="primary", key="btn_growth"):
        # Parse historical series
        def parse_series(s):
            try:
                return [float(x.strip()) for x in s.split(",") if x.strip()]
            except:
                return None

        hist_eps = parse_series(eps_str)
        hist_rev = parse_series(rev_str) if rev_str.strip() else None

        if w_fund < 0:
            st.error("Fix blend weights first.")
        else:
            g = estimate_growth(
                ebit=ebit, tax_rate=tax_rate, net_capex=net_capex, delta_wc=delta_wc,
                book_equity=book_eq, book_debt=book_debt,
                net_income=net_income, dividends=dividends,
                historical_eps=hist_eps, historical_rev=hist_rev,
                analyst_growth=analyst_g, industry=industry,
            )

            st.divider()
            st.markdown("## Results")

            # Top metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Fundamental g (firm)",   f"{g.fundamental_growth_firm:.2%}", help="ROC × RIR")
            c2.metric("Fundamental g (equity)", f"{g.fundamental_growth_equity:.2%}", help="ROE × Retention")
            c3.metric("Recommended growth",     f"{g.recommended_growth:.2%}")
            c4.metric("ROC",                    f"{g.roc:.2%}")

            # Scores
            s_g, t_g, c_g = score_growth(g.recommended_growth, g.industry_rev_g_median)
            s_r, t_r, c_r = score_roc(g.roc, wacc_input)
            st.markdown(badge(s_g, t_g, c_g) + "&nbsp;&nbsp;" + badge(s_r, t_r, c_r),
                        unsafe_allow_html=True)

            # Detail box
            st.markdown(f"""<div class="explain-box">
<strong>Growth build-up:</strong><br>
ROC = EBIT×(1−t) / Invested_Capital = {ebit*(1-tax_rate):,.0f} / {book_eq+book_debt:,.0f} = <strong>{g.roc:.2%}</strong><br>
Reinvestment Rate = (Net CapEx + ΔWC) / NOPAT = {net_capex+delta_wc:,.0f} / {ebit*(1-tax_rate):,.0f} = <strong>{g.reinvestment_rate:.2%}</strong><br>
Fundamental g (firm) = {g.roc:.2%} × {g.reinvestment_rate:.2%} = <strong>{g.fundamental_growth_firm:.2%}</strong><br><br>
ROE = NI / Book_Equity = {net_income:,.0f} / {book_eq:,.0f} = <strong>{g.roe:.2%}</strong><br>
Retention Ratio = (NI − Dividends) / NI = {net_income-dividends:,.0f} / {net_income:,.0f} = <strong>{g.retention_ratio:.2%}</strong><br>
Fundamental g (equity) = {g.roe:.2%} × {g.retention_ratio:.2%} = <strong>{g.fundamental_growth_equity:.2%}</strong><br><br>
{"Historical EPS CAGR: <strong>" + f"{g.historical_eps_cagr:.2%}</strong><br>" if g.historical_eps_cagr else ""}
{"Analyst estimate: <strong>" + f"{g.analyst_growth:.2%}</strong><br>" if g.analyst_growth else ""}
<strong>Blended recommendation: {g.recommended_growth:.2%}</strong> — {g.recommended_basis}
{"<br><br>Industry median revenue growth (" + industry + "): <strong>" + f"{g.industry_rev_g_median:.2%}</strong>" if g.industry_rev_g_median else ""}
</div>""", unsafe_allow_html=True)

            # Three-way comparison table
            comparison = {
                "Approach": ["Fundamental (firm)", "Fundamental (equity)",
                             "Historical EPS CAGR", "Analyst estimate", "Recommended blend"],
                "Growth rate": [
                    f"{g.fundamental_growth_firm:.2%}",
                    f"{g.fundamental_growth_equity:.2%}",
                    f"{g.historical_eps_cagr:.2%}" if g.historical_eps_cagr else "N/A",
                    f"{g.analyst_growth:.2%}" if g.analyst_growth else "N/A",
                    f"{g.recommended_growth:.2%}",
                ],
                "Basis": [
                    "ROC × Reinvestment Rate",
                    "ROE × Retention Ratio",
                    "Geometric mean of EPS series",
                    "Sell-side consensus",
                    g.recommended_basis,
                ],
            }
            st.dataframe(pd.DataFrame(comparison), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Terminal value
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Terminal Value")
    st.markdown("The growing perpetuity beyond the explicit forecast period — typically 60–80% of total firm value.")
    explain("terminal_value")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Inputs**")
        cf_final   = st.number_input("Final year FCFF or FCFE ($m)", value=8_288.0, key="tv_cf")
        disc_rate  = st.number_input("Discount rate (WACC or ke)",   value=0.096,   key="tv_dr", format="%.3f")
        g_stable   = st.number_input("Stable growth rate (g)",       value=0.040,   key="tv_g",  format="%.3f")
        stable_roc = st.number_input("Stable ROC (0 = no fundamental RIR check)",
                                      value=0.12, key="tv_roc", format="%.3f")
        stable_roc = stable_roc if stable_roc > 0 else None
    with col2:
        st.markdown("**Consistency rules (Ch 12)**")
        st.markdown(f"""<div class="explain-box" style="margin-top:0">
Damodaran's three requirements for a valid terminal value:<br><br>
1. <strong>g ≤ risk-free rate</strong> — the firm cannot grow faster than the economy in perpetuity<br>
2. <strong>ROC → WACC</strong> — competition erodes excess returns; assume ROC ≈ WACC in stable period<br>
3. <strong>Reinvest consistently</strong> — if g = 4% and ROC = 8%, RIR must be 50%, not zero
</div>""", unsafe_allow_html=True)

    if st.button("Calculate Terminal Value →", type="primary", key="btn_tv"):
        try:
            tv = terminal_value_gordon(
                cash_flow_final_year=cf_final,
                discount_rate=disc_rate,
                g_stable=g_stable,
                stable_roc=stable_roc,
                tax_rate=0.25,
            )

            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Terminal Value", f"${tv.terminal_value:,.0f}m")
            c2.metric("Implied multiple", f"{tv.terminal_value / cf_final:.1f}×",
                      help="Terminal value / final year cash flow")
            rr = g_stable / stable_roc if stable_roc else None
            c3.metric("Stable RIR", f"{rr:.1%}" if rr else "N/A",
                      help="Reinvestment rate = g / ROC in terminal year")

            # Consistency checks
            st.markdown("### Consistency checks")
            all_pass = all(v["pass"] for v in tv.checks.values())
            for k, v in tv.checks.items():
                css = "check-pass" if v["pass"] else "check-fail"
                icon = "✓" if v["pass"] else "✗"
                st.markdown(f'<div class="{css}"><strong>{icon} {v["label"]}</strong><br>{v["detail"]}</div>',
                            unsafe_allow_html=True)

            if not all_pass:
                st.markdown('<div class="tv-warning">⚠ One or more consistency checks failed. '
                            'Terminal value assumptions may overstate or understate intrinsic value. '
                            'Review the flagged items before using this number in a valuation.</div>',
                            unsafe_allow_html=True)

            # Sensitivity table
            st.markdown("### Sensitivity analysis")
            st.caption("Terminal value ($m) across growth rates (rows) and discount rates (columns)")

            g_vals = sorted(set(k[0] for k in tv.sensitivity.keys()))
            r_vals = sorted(set(k[1] for k in tv.sensitivity.keys()))

            rows = []
            for g in g_vals:
                row = {"g \\ WACC": f"{g:.2%}"}
                for r in r_vals:
                    val = tv.sensitivity.get((g, r))
                    row[f"{r:.2%}"] = f"${val:,.0f}" if val else "—"
                rows.append(row)

            df_sens = pd.DataFrame(rows).set_index("g \\ WACC")
            # Highlight the base case cell
            st.dataframe(df_sens, use_container_width=True)

            st.caption(f"Base case highlighted: g = {g_stable:.2%}, WACC = {disc_rate:.2%} → TV = ${tv.terminal_value:,.0f}m")

        except ValueError as e:
            st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Industry benchmark
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Industry Benchmark")
    st.markdown("Compare your assumptions against the quartile distribution of actual companies.")
    st.caption("Source: Damodaran *fcffsimpleginzu.xlsx* — Input Stat Distributions sheet (Jan 2026, ~8,000 global firms)")

    if not industry:
        st.info("Select an industry in the sidebar to see benchmarks.")
    else:
        st.markdown(f"### {industry}")
        d = INDUSTRY_DATA[industry]

        col1, col2 = st.columns(2)
        with col1:
            rev_g_input = st.number_input("Your revenue growth",    value=0.08, format="%.3f", key="bm_rg")
            margin_input = st.number_input("Your EBIT margin",      value=0.14, format="%.3f", key="bm_mg")
        with col2:
            s2c_input   = st.number_input("Your Sales/Capital",     value=1.80, format="%.2f", key="bm_s2c")
            wacc_bm     = st.number_input("Your WACC",              value=0.088,format="%.3f", key="bm_wc")

        bm = benchmark_vs_industry(industry, rev_g_input, margin_input, s2c_input, wacc_bm)

        metrics = {
            "revenue_growth":   ("Revenue Growth",   ".1%"),
            "ebit_margin":      ("EBIT Margin",      ".1%"),
            "sales_to_capital": ("Sales / Capital",  ".2f"),
            "wacc":             ("WACC",             ".1%"),
        }

        st.markdown("### Your position vs industry")
        for key, (label, fmt) in metrics.items():
            if key not in bm: continue
            data = bm[key]
            q1, med, q3 = data["q1"], data["median"], data["q3"]
            val = data["value"]
            pos = data["position"]

            colour = ("green" if pos in ("3rd quartile", "top quartile")
                      else "yellow" if pos == "2nd quartile" else "red")
            if key == "wacc":
                colour = ("yellow" if pos == "top quartile" else
                          "green" if pos in ("2nd quartile", "3rd quartile") else "green")

            st.markdown(f"**{label}**")
            st.markdown(quartile_marker(val, q1, med, q3, fmt))
            st.markdown(badge(0, pos, colour).replace("Score 0/10 — ", ""), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # Full industry distribution table
        with st.expander("📋 Full industry distribution table"):
            rows = []
            for name in INDUSTRY_NAMES:
                d2 = INDUSTRY_DATA[name]
                rows.append({
                    "Industry":         name,
                    "Rev Growth Q1":    f"{d2['rev_g'][0]:.1%}",
                    "Rev Growth Med":   f"{d2['rev_g'][1]:.1%}",
                    "Rev Growth Q3":    f"{d2['rev_g'][2]:.1%}",
                    "Margin Q1":        f"{d2['margin'][0]:.1%}",
                    "Margin Med":       f"{d2['margin'][1]:.1%}",
                    "Margin Q3":        f"{d2['margin'][2]:.1%}",
                    "S/C Q1":           f"{d2['s2c'][0]:.2f}",
                    "S/C Med":          f"{d2['s2c'][1]:.2f}",
                    "WACC Med":         f"{d2['wacc'][1]:.1%}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Footer
st.divider()
st.markdown("""<div style="font-size:0.75rem;color:#475569;text-align:center;padding:12px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed., Ch 11 (growth), Ch 12 (terminal value)<br>
Industry data: fcffsimpleginzu.xlsx — Input Stat Distributions (Jan 2026 · ~8,000 global firms)
</div>""", unsafe_allow_html=True)
