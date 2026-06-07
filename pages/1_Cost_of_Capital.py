"""
app.py — Cost of Capital Dashboard
Damodaran Investment Valuation — Ch 7–8

Features:
  - Plain-English explanations from the textbook for every metric
  - Scored interpretation (1–10 scale) with colour-coded signals
  - Data placeholders ready for live EDGAR + yfinance connection
  - Rate-limit-aware yfinance fetch helpers (commented until wired up)
"""

import streamlit as st
import math
from dataclasses import dataclass
from typing import Optional
from cost_of_capital import (
    full_cost_of_capital, capitalise_operating_leases,
    FullCostOfCapitalResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Cost of Capital",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
h1, h2, h3 { font-family: 'DM Serif Display', serif; }

.metric-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
}
.metric-value {
    font-size: 2.2rem;
    font-weight: 300;
    letter-spacing: -1px;
    font-family: 'DM Serif Display', serif;
}
.metric-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #64748b;
    margin-bottom: 4px;
}
.score-pill {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    margin-top: 8px;
}
.score-green  { background: #14532d; color: #86efac; }
.score-yellow { background: #713f12; color: #fde68a; }
.score-red    { background: #7f1d1d; color: #fca5a5; }

.explain-box {
    background: #1e293b;
    border-left: 3px solid #3b82f6;
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin: 10px 0 18px 0;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #cbd5e1;
}
.source-tag {
    font-size: 0.72rem;
    color: #475569;
    margin-top: 8px;
}
.data-badge {
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 4px;
    background: #1e3a5f;
    color: #93c5fd;
    display: inline-block;
    margin-bottom: 6px;
}
.placeholder-badge {
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 4px;
    background: #3b2a0f;
    color: #fbbf24;
    display: inline-block;
    margin-bottom: 6px;
}
.section-divider {
    border: none;
    border-top: 1px solid #1e293b;
    margin: 28px 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Textbook explanations — sourced from Damodaran Ch 7–8
# ─────────────────────────────────────────────────────────────────────────────

EXPLANATIONS = {
    "wacc": {
        "title": "Weighted Average Cost of Capital (WACC)",
        "what": (
            "WACC is the minimum return a firm must earn on its existing asset base " "to keep its shareholders and creditors satisfied. It blends the cost of " "equity and the after-tax cost of debt, weighted by how much of each the " "firm actually uses."
        ),
        "formula": "WACC = ke × (E/V) + kd × (1−t) × (D/V)",
        "why": (
            "This is the discount rate used to value the firm's free cash flows " "(FCFF model). A lower WACC means less of every dollar of cash flow is " "eaten up by the cost of financing — which directly raises firm value."
        ),
        "source": "Damodaran, *Investment Valuation* 2nd Ed, Ch 8, p.195",
    },
    "ke": {
        "title": "Cost of Equity (ke)",
        "what": (
            "The return shareholders require to hold the stock rather than put their " "money elsewhere. It is not a cash outflow — it is an opportunity cost. " "Computed via the Capital Asset Pricing Model (CAPM)."
        ),
        "formula": "ke = rf + β × ERP",
        "why": (
            "Equity is the most expensive form of capital because shareholders bear " "residual risk. The higher the beta (sensitivity to market swings) and " "the higher the equity risk premium, the more investors demand."
        ),
        "source": "Damodaran, Ch 7, p.160",
    },
    "kd": {
        "title": "Pre-tax Cost of Debt (kd)",
        "what": (
            "The yield the firm would have to offer on new debt today — not the " "coupon rate on old debt. Estimated from the firm's synthetic credit " "rating, which is derived from how comfortably EBIT covers interest."
        ),
        "formula": "kd = rf + default spread",
        "why": (
            "Debt is cheaper than equity because interest is tax-deductible and " "creditors have priority in bankruptcy. But as debt increases, the " "rating falls and the spread widens — eventually making debt expensive."
        ),
        "source": "Damodaran, Ch 8, p.182",
    },
    "icr": {
        "title": "Interest Coverage Ratio (ICR)",
        "what": (
            "How many times over EBIT can cover the annual interest bill. " "This is the single number Damodaran uses to assign a synthetic " "credit rating to any firm — even one with no actual bond rating."
        ),
        "formula": "ICR = EBIT / Interest Expense",
        "why": (
            "A higher ICR means more cushion for creditors, which means a better " "rating and a lower default spread. ICR below 1.5 suggests the firm " "cannot comfortably service its debt from operations."
        ),
        "source": "Damodaran, Ch 8, p.183",
    },
    "beta": {
        "title": "Beta (β)",
        "what": (
            "Beta measures how much a stock moves relative to the overall market. " "A beta of 1.2 means the stock tends to rise 12% when the market rises " "10%, and fall 12% when it falls 10%. It captures systematic risk — " "the risk that cannot be diversified away."
        ),
        "formula": "β_relevered = β_unlevered × [1 + (1−t) × D/E]",
        "why": (
            "Damodaran always unlevered the beta first (removing financial risk) " "then re-levers it for the firm's actual capital structure. This way " "you are comparing apples to apples when using industry betas."
        ),
        "source": "Damodaran, Ch 8, p.170 (Hamada equation)",
    },
    "debt_mv": {
        "title": "Market Value of Debt",
        "what": (
            "Book value of debt (from the balance sheet) is often wrong as an input " "to WACC because it reflects what was borrowed years ago, not what it " "would cost to refinance today. Damodaran converts it to a present value " "by treating all debt as a single coupon bond."
        ),
        "formula": "MV(Debt) = Interest × annuity_factor(kd, n) + Book_Debt / (1+kd)^n",
        "why": (
            "WACC must use market-value weights, not book-value weights. Using book " "weights overstates the debt burden for firms that issued debt when " "rates were higher than today, and vice versa."
        ),
        "source": "Damodaran, Ch 8, p.194",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Scoring functions — benchmarks from Damodaran & wacccalc industry dataset
# ─────────────────────────────────────────────────────────────────────────────

def score_wacc(wacc: float) -> tuple[int, str, str]:
    """
    Score WACC 1–10 using Damodaran's industry average WACC dataset.
    Median US WACC across all sectors ≈ 8–9%. Source: wacccalc.xls Industry Averages.
    """
    pct = wacc * 100
    if pct < 5:
        return 9, "Very low — cost of capital well below market norms. " "High-quality, low-risk business or significant leverage benefit.", "green"
    elif pct < 7:
        return 8, "Low — below the typical 7–9% range for most US corporates. " "Implies strong credit quality or conservative capital structure.", "green"
    elif pct < 9:
        return 7, "Average — within the 7–9% band for most US firms. " "Neither a competitive advantage nor a penalty.", "green"
    elif pct < 11:
        return 5, "Above average — higher than the market median. " "Check whether leverage, beta, or country risk is the driver.", "yellow"
    elif pct < 14:
        return 3, "High — significantly above typical rates. " "Firm faces elevated financing costs; will need higher returns to create value.", "yellow"
    else:
        return 1, "Very high — WACC above 14% is typical only for distressed firms " "or high-risk emerging market businesses.", "red"


def score_icr(icr: float) -> tuple[int, str, str]:
    """
    Score interest coverage ratio using Damodaran's ratings table breakpoints.
    """
    if icr == math.inf or icr > 12.5:
        return 10, "Exceptional coverage — no meaningful credit risk. " "Equivalent to Aaa/AAA. Firm has significant unused debt capacity.", "green"
    elif icr > 8.5:
        return 9, "Excellent — Aa2/AA equivalent. Very comfortable debt service.", "green"
    elif icr > 5.5:
        return 8, "Strong — A-range rating. EBIT covers interest >5x.", "green"
    elif icr > 3.0:
        return 6, "Adequate — BBB to A− range. Serviceable but leaves limited cushion " "in a downturn.", "yellow"
    elif icr > 2.0:
        return 4, "Weak — BB range. Interest expense consumes a significant share of " "operating income. Refinancing risk is real.", "yellow"
    elif icr > 1.25:
        return 2, "Stressed — B range. The firm struggles to cover interest from " "operations. Default risk is meaningful.", "red"
    else:
        return 1, "Distressed — ICR below 1.25 means EBIT barely covers interest. " "High probability of financial difficulty.", "red"


def score_beta(beta: float) -> tuple[int, str, str]:
    """
    Score beta relative to market (β=1). Source: Damodaran, Ch 8.
    """
    if beta < 0.5:
        return 9, "Defensive — stock moves at less than half the market rate. " "Typical of utilities, consumer staples, REITs.", "green"
    elif beta < 0.8:
        return 8, "Low volatility — below-market sensitivity. " "Lower cost of equity; often mature, stable businesses.", "green"
    elif beta < 1.1:
        return 7, "Market-rate risk — moves roughly in line with the index. " "Appropriate for diversified industrial firms.", "green"
    elif beta < 1.4:
        return 5, "Moderately elevated — 10–40% more volatile than the market. " "Typical of cyclicals, mid-cap tech, specialty industrials.", "yellow"
    elif beta < 1.8:
        return 3, "High — 40–80% more volatile. Increases cost of equity meaningfully. " "Common in small-cap, high-growth, or highly-leveraged firms.", "yellow"
    else:
        return 1, "Very high beta — equity amplifies market moves by nearly 2x or more. " "Implies a high cost of equity and significant systematic risk.", "red"


def score_ke(ke: float) -> tuple[int, str, str]:
    """
    Benchmark against Damodaran's average cost of equity across sectors ≈ 9–11%.
    """
    pct = ke * 100
    if pct < 7:
        return 9, "Very low cost of equity — reflects low beta or defensive sector. " "Typical of utilities and regulated industries.", "green"
    elif pct < 9:
        return 8, "Below-average cost of equity. Investors do not demand a large " "premium for this stock's systematic risk.", "green"
    elif pct < 11:
        return 7, "Average — broadly in line with the 9–11% range for most US firms.", "green"
    elif pct < 13:
        return 5, "Above average — market asks for a meaningful premium. " "Check whether beta or ERP is the main driver.", "yellow"
    elif pct < 16:
        return 3, "High cost of equity — firm must generate strong returns to " "exceed what shareholders could earn elsewhere.", "yellow"
    else:
        return 1, "Very high — cost of equity above 16% is typical only of very " "high-beta, distressed, or emerging-market equities.", "red"


# ─────────────────────────────────────────────────────────────────────────────
# Data placeholder helpers — swap real fetchers in here
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompanyData:
    ticker: str
    name: str
    ebit: float
    interest_expense: float
    book_debt: float
    avg_debt_maturity: float
    equity_market_cap: float
    beta_levered: float
    rf: float
    erp: float
    tax_rate: float
    country_spread: float
    firm_type: int
    source: str   # "placeholder" | "yfinance" | "edgar"


def get_placeholder_data(ticker: str) -> CompanyData:
    """
    Placeholder data. Replace the body of this function with
    live fetchers (see commented section below).

    EDGAR fetch notes:
      - Use SEC EDGAR full-text search API (free, no key):
        https://efts.sec.gov/LATEST/search-index?q="{ticker}"&dateRange=custom
      - Pull the most recent 10-K filing JSON
      - Rate limit: ~10 req/sec, no auth needed

    yfinance notes:
      - Use yf.Ticker(ticker).info for beta, market cap
      - Use yf.Ticker(ticker).financials for EBIT, interest
      - IMPORTANT: cache results in st.session_state to avoid
        re-fetching on every rerender. yfinance free tier has no
        hard rate limit but will throttle after ~2,000 req/hr.
      - Never call yfinance inside a loop or on every keystroke.
        Only fetch on button click.
    """

    # ── Live fetch would go here ──────────────────────────────────────────
    # import yfinance as yf
    # t = yf.Ticker(ticker)
    # info = t.info          # one call — cache in session_state
    # fin  = t.financials    # one call — cache in session_state
    #
    # ebit             = float(fin.loc["EBIT"].iloc[0])
    # interest_expense = float(fin.loc["Interest Expense"].iloc[0])
    # beta_levered     = float(info.get("beta", 1.0))
    # equity_mv        = float(info.get("marketCap", 0)) / 1e6
    # ─────────────────────────────────────────────────────────────────────

    DEFAULTS = {
        "AAPL": CompanyData("AAPL", "Apple Inc.", 115_000, 3_900, 111_000,
                             5, 2_800_000, 1.24, 0.045, 0.055, 0.21, 0.0, 1, "placeholder"),
        "MSFT": CompanyData("MSFT", "Microsoft Corp.", 88_500, 1_900, 60_000,
                             6, 3_100_000, 0.90, 0.045, 0.055, 0.21, 0.0, 1, "placeholder"),
        "TSLA": CompanyData("TSLA", "Tesla Inc.", 8_700, 590, 8_800,
                             4, 600_000, 2.30, 0.045, 0.055, 0.21, 0.0, 2, "placeholder"),
        "JPM":  CompanyData("JPM", "JPMorgan Chase", 55_000, 32_000, 400_000,
                             5, 500_000, 1.10, 0.045, 0.055, 0.25, 0.0, 3, "placeholder"),
    }

    if ticker.upper() in DEFAULTS:
        return DEFAULTS[ticker.upper()]

    # Generic placeholder for any other ticker
    return CompanyData(
        ticker=ticker, name=f"{ticker} (placeholder data)",
        ebit=1_500, interest_expense=300, book_debt=3_000,
        avg_debt_maturity=5, equity_market_cap=12_000,
        beta_levered=1.2, rf=0.045, erp=0.055, tax_rate=0.25,
        country_spread=0.0, firm_type=1, source="placeholder",
    )


# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def score_badge(score: int, label: str, colour: str) -> str:
    css = f"score-{colour}"
    return f'<span class="score-pill {css}">Score {score}/10 — {label}</span>'


def explain_block(key: str) -> None:
    e = EXPLANATIONS.get(key, {})
    if not e:
        return
    with st.expander(f"📖 What is {e['title']}?", expanded=False):
        st.markdown(f"""
<div class="explain-box">
<strong>What it is:</strong> {e['what']}
<br><br>
<strong>Formula:</strong> <code>{e['formula']}</code>
<br><br>
<strong>Why it matters for valuation:</strong> {e['why']}
<br><br>
<div class="source-tag">Source: {e['source']}</div>
</div>
""", unsafe_allow_html=True)


def metric_card(label: str, value: str, score: int, interp: str, colour: str,
                delta: str = "") -> None:
    badge = score_badge(score, interp, colour)
    delta_html = f'<div style="font-size:0.78rem;color:#64748b;margin-top:4px">{delta}</div>' if delta else ""
    st.markdown(f"""
<div class="metric-card">
  <div class="metric-label">{label}</div>
  <div class="metric-value">{value}</div>
  {delta_html}
  {badge}
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — data source + inputs
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏢 Company")

    ticker = st.text_input("Ticker", value="AAPL", help="Enter any ticker. Placeholder data shown until live connection is enabled.").upper()

    data_source = st.radio(
        "Data source",
        ["Placeholder (demo)", "Manual override"],
        help="Live EDGAR + yfinance connection coming soon.",
    )

    d = get_placeholder_data(ticker)

    if d.source == "placeholder":
        st.markdown('<span class="placeholder-badge">⚠ Placeholder data — not live</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="data-badge">✓ Live data</span>', unsafe_allow_html=True)

    st.markdown("---")

    if data_source == "Manual override":
        st.markdown("### Override inputs")
        ebit             = st.number_input("EBIT ($m)",                  value=d.ebit)
        interest_expense = st.number_input("Interest Expense ($m)",      value=d.interest_expense)
        book_debt        = st.number_input("Book Value of Debt ($m)",     value=d.book_debt)
        avg_maturity     = st.number_input("Avg Debt Maturity (yrs)",     value=d.avg_debt_maturity)
        equity_mv        = st.number_input("Market Cap ($m)",             value=d.equity_market_cap)
        beta_levered     = st.number_input("Levered Beta",                value=d.beta_levered)
        rf               = st.number_input("Risk-free Rate",              value=d.rf, format="%.3f")
        erp              = st.number_input("Equity Risk Premium",         value=d.erp, format="%.3f")
        tax_rate         = st.number_input("Marginal Tax Rate",           value=d.tax_rate, format="%.2f")
        country_spread   = st.number_input("Country Spread (0 = US)",     value=d.country_spread, format="%.3f")
        firm_type        = st.selectbox("Firm Type", [1, 2, 3],
                               format_func=lambda x: {1:"Large firm",2:"Small/risky",3:"Financial"}[x],
                               index=d.firm_type - 1)
    else:
        ebit, interest_expense = d.ebit, d.interest_expense
        book_debt, avg_maturity = d.book_debt, d.avg_debt_maturity
        equity_mv, beta_levered = d.equity_market_cap, d.beta_levered
        rf, erp, tax_rate = d.rf, d.erp, d.tax_rate
        country_spread, firm_type = d.country_spread, d.firm_type

    st.markdown("---")
    st.markdown("""
<div style='font-size:0.75rem;color:#475569;line-height:1.7'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — beta, market cap, financials<br>
🔵 SEC EDGAR — 10-K filings, debt schedule<br>
🔵 FRED — 10-yr Treasury (risk-free rate)<br>
🔵 Damodaran site — ERP, country spreads
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Run model
# ─────────────────────────────────────────────────────────────────────────────

result = full_cost_of_capital(
    ebit=ebit, interest_expense=interest_expense,
    book_debt=book_debt, avg_debt_maturity=avg_maturity,
    equity_market_cap=equity_mv, beta_levered=beta_levered,
    rf=rf, erp=erp, tax_rate=tax_rate,
    country_spread=country_spread, firm_type=firm_type,
)

dc = result.debt_cost
br = result.beta_result
wr = result.wacc_result

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(f"# {d.name}")
st.markdown(f"**Cost of Capital Analysis** · Damodaran *Investment Valuation* methodology")

if d.source == "placeholder":
    st.warning("⚠ Showing placeholder data. Live connection to EDGAR and Yahoo Finance coming soon.", icon="⚠️")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Top-line results
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Summary")
st.caption("The three numbers that drive every DCF valuation")

col1, col2, col3 = st.columns(3)

with col1:
    s, interp, colour = score_wacc(wr.wacc)
    metric_card("WACC", f"{wr.wacc:.2%}", s, interp[:40] + "…" if len(interp) > 40 else interp, colour,
                delta=f"Equity {wr.weight_equity:.0%} / Debt {wr.weight_debt:.0%}")
    explain_block("wacc")

with col2:
    s, interp, colour = score_ke(br.ke)
    metric_card("Cost of Equity", f"{br.ke:.2%}", s, interp[:40] + "…" if len(interp) > 40 else interp, colour,
                delta=f"β {br.beta_relevered:.2f} × ERP {br.erp:.1%}")
    explain_block("ke")

with col3:
    s, interp, colour = score_icr(dc.icr)
    icr_str = "∞" if dc.icr == math.inf else f"{dc.icr:.1f}x"
    metric_card("Interest Coverage", icr_str, s, interp[:40] + "…" if len(interp) > 40 else interp, colour,
                delta=f"Rating: {dc.rating} · Spread: {dc.company_spread:.2%}")
    explain_block("icr")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Detailed breakdown
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Step-by-step breakdown")
st.caption("How Damodaran builds up the cost of capital from first principles")

# ── Step 1: Credit rating ────────────────────────────────────────────────────
st.markdown("### Step 1 — Synthetic Credit Rating")
st.markdown("""
Damodaran does not rely on Moody's or S&P. He derives a rating purely from
the interest coverage ratio (EBIT ÷ interest expense), then reads off the
default spread from a lookup table. This works even for private firms.
""")

c1, c2, c3, c4 = st.columns(4)
c1.metric("EBIT", f"${ebit:,.0f}m")
c2.metric("Interest Expense", f"${interest_expense:,.0f}m")
c3.metric("ICR", "∞" if dc.icr == math.inf else f"{dc.icr:.2f}×")
c4.metric("Rating → Spread", f"{dc.rating} → {dc.company_spread:.2%}")

explain_block("icr")
explain_block("kd")

s, interp, colour = score_icr(dc.icr)
st.markdown(score_badge(s, interp, colour), unsafe_allow_html=True)

st.markdown(f"""
<div class="explain-box">
<strong>Interpretation:</strong> {interp}
<br><br>
Pre-tax cost of debt = {dc.rf:.2%} (risk-free) + {dc.company_spread:.2%} (company spread)
{"+ " + f"{dc.country_spread:.2%} (country)" if dc.country_spread > 0 else ""} = <strong>{dc.kd_pretax:.2%}</strong><br>
After-tax cost of debt = {dc.kd_pretax:.2%} × (1 − {dc.tax_rate:.0%}) = <strong>{dc.kd_aftertax:.2%}</strong>
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ── Step 2: Beta and cost of equity ─────────────────────────────────────────
st.markdown("### Step 2 — Beta & Cost of Equity")
st.markdown("""
The Hamada equation first strips out financial leverage from the observed beta
(giving the *unlevered* or *asset* beta), then re-applies the firm's actual
capital structure to get the *levered* beta used in CAPM.
""")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Input Beta (levered)", f"{br.beta_levered_input:.3f}")
c2.metric("Unlevered Beta", f"{br.beta_unlevered:.3f}")
c3.metric("Re-levered Beta", f"{br.beta_relevered:.3f}")
c4.metric("Cost of Equity", f"{br.ke:.2%}")

explain_block("beta")
explain_block("ke")

s_b, interp_b, col_b = score_beta(br.beta_relevered)
s_k, interp_k, col_k = score_ke(br.ke)
st.markdown(score_badge(s_b, interp_b, col_b) + "&nbsp;&nbsp;" + score_badge(s_k, interp_k, col_k), unsafe_allow_html=True)

st.markdown(f"""
<div class="explain-box">
<strong>CAPM build-up:</strong><br>
ke = {br.rf:.2%} (risk-free) + {br.beta_relevered:.3f} (beta) × {br.erp:.2%} (ERP) = <strong>{br.ke:.2%}</strong>
<br><br>
<strong>Unlevering:</strong> β_u = {br.beta_levered_input:.3f} / [1 + (1 − {br.tax_rate:.0%}) × {br.current_de:.2f}] = {br.beta_unlevered:.3f}
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ── Step 3: Market value of debt ─────────────────────────────────────────────
st.markdown("### Step 3 — Market Value of Debt")
st.markdown("""
Book value of debt (from the balance sheet) reflects what was borrowed years
ago. Damodaran converts it to today's market value by treating all debt as a
single bond: discount the coupon stream (= interest expense) plus the face
value (= book debt) at the current cost of debt.
""")

c1, c2, c3 = st.columns(3)
c1.metric("Book Value of Debt", f"${book_debt:,.0f}m")
c2.metric("Market Value of Debt", f"${result.market_debt:,.0f}m")
pct_diff = (result.market_debt - book_debt) / book_debt * 100 if book_debt else 0
c3.metric("Difference", f"{pct_diff:+.1f}%", help="Positive = market value > book (rates fell since issuance)")

explain_block("debt_mv")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ── Step 4: WACC assembly ─────────────────────────────────────────────────────
st.markdown("### Step 4 — WACC Assembly")
st.markdown("""
All components are combined using **market-value weights** — not book values.
Damodaran is emphatic: book weights are backward-looking; market weights
reflect the actual opportunity cost investors face today.
""")

c1, c2, c3 = st.columns(3)
c1.metric("Equity Weight",        f"{wr.weight_equity:.1%}",  delta=f"${wr.equity_mv:,.0f}m")
c2.metric("Debt Weight",          f"{wr.weight_debt:.1%}",    delta=f"${wr.debt_mv:,.0f}m")
c3.metric("Total Capital (MV)",   f"${wr.total_capital:,.0f}m")

explain_block("wacc")

s_w, interp_w, col_w = score_wacc(wr.wacc)
st.markdown(score_badge(s_w, interp_w, col_w), unsafe_allow_html=True)

wacc_equity_contrib = br.ke * wr.weight_equity
wacc_debt_contrib   = dc.kd_aftertax * wr.weight_debt
st.markdown(f"""
<div class="explain-box">
<strong>WACC build-up:</strong><br>
Equity component: {br.ke:.2%} × {wr.weight_equity:.1%} = {wacc_equity_contrib:.2%}<br>
Debt component: {dc.kd_aftertax:.2%} × {wr.weight_debt:.1%} = {wacc_debt_contrib:.2%}<br>
<strong>WACC = {wr.wacc:.2%}</strong>
<br><br>
<strong>What this means for valuation:</strong> Every $1 of FCFF the firm generates
is discounted at {wr.wacc:.2%} per year. A 1 percentage point reduction in WACC
increases the terminal value by roughly {(1/(wr.wacc-0.03) - 1/(wr.wacc+0.01-0.03))/(1/(wr.wacc-0.03)):.0%}
(assuming 3% stable growth).
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Overall scorecard
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Overall Scorecard")

scores = {
    "WACC":              score_wacc(wr.wacc),
    "Cost of Equity":    score_ke(br.ke),
    "Interest Coverage": score_icr(dc.icr),
    "Beta":              score_beta(br.beta_relevered),
}

composite = sum(s for s, _, _ in scores.values()) / len(scores)

c1, c2 = st.columns([1, 2])
with c1:
    st.markdown(f"""
<div class="metric-card" style="text-align:center">
  <div class="metric-label">Composite Score</div>
  <div class="metric-value" style="font-size:3.5rem">{composite:.1f}</div>
  <div style="color:#64748b;font-size:0.85rem">out of 10</div>
</div>
""", unsafe_allow_html=True)

with c2:
    for name, (s, interp, colour) in scores.items():
        bar_width = s * 10
        bar_color = {"green": "#22c55e", "yellow": "#f59e0b", "red": "#ef4444"}[colour]
        st.markdown(f"""
<div style="margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
    <span style="font-size:0.85rem;color:#cbd5e1">{name}</span>
    <span style="font-size:0.85rem;color:{bar_color};font-weight:500">{s}/10</span>
  </div>
  <div style="background:#1e293b;border-radius:4px;height:8px">
    <div style="background:{bar_color};width:{bar_width}%;height:8px;border-radius:4px;transition:width 0.3s"></div>
  </div>
  <div style="font-size:0.75rem;color:#64748b;margin-top:3px">{interp[:80]}{"…" if len(interp) > 80 else ""}</div>
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="font-size:0.75rem;color:#475569;text-align:center;padding:20px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed. (2002), Chapters 7–8<br>
Spread tables: wacccalc.xls, ratings.xls (Jan-2026 vintage)<br>
Data: placeholder · Live connection (EDGAR, yfinance, FRED) coming soon
</div>
""", unsafe_allow_html=True)
