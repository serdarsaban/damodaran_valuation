"""
app.py — Home page
Damodaran Investment Valuation Toolkit
"""

import streamlit as st

st.set_page_config(
    page_title="Damodaran Valuation",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }

.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 48px 56px;
    margin-bottom: 32px;
}
.hero-title {
    font-family: 'DM Serif Display', serif;
    font-size: 3rem;
    font-weight: 400;
    letter-spacing: -1px;
    color: #f1f5f9;
    line-height: 1.15;
    margin: 0 0 12px 0;
}
.hero-subtitle {
    font-size: 1.1rem;
    color: #94a3b8;
    font-weight: 300;
    margin: 0 0 8px 0;
}
.hero-source {
    font-size: 0.82rem;
    color: #475569;
    font-style: italic;
}

.module-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 24px 28px;
    height: 100%;
    transition: border-color 0.2s;
}
.module-card:hover { border-color: #3b82f6; }
.module-number {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: #3b82f6;
    margin-bottom: 8px;
}
.module-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.35rem;
    color: #f1f5f9;
    margin-bottom: 8px;
}
.module-desc {
    font-size: 0.87rem;
    color: #94a3b8;
    line-height: 1.6;
    margin-bottom: 16px;
}
.module-chapters {
    font-size: 0.75rem;
    color: #475569;
    margin-bottom: 12px;
}
.status-live {
    display: inline-block;
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 20px;
    background: #14532d;
    color: #86efac;
    font-weight: 500;
}
.status-building {
    display: inline-block;
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 20px;
    background: #713f12;
    color: #fde68a;
    font-weight: 500;
}
.status-planned {
    display: inline-block;
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 20px;
    background: #1e293b;
    color: #475569;
    font-weight: 500;
}

.formula-strip {
    background: #1e293b;
    border-radius: 8px;
    padding: 14px 20px;
    font-family: 'DM Mono', 'Courier New', monospace;
    font-size: 0.82rem;
    color: #7dd3fc;
    margin: 6px 0;
    line-height: 1.6;
}

.data-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid #1e293b;
    font-size: 0.87rem;
    color: #cbd5e1;
}
.data-dot-live    { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; flex-shrink: 0; }
.data-dot-pending { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; flex-shrink: 0; }
.data-dot-todo    { width: 8px; height: 8px; border-radius: 50%; background: #334155; flex-shrink: 0; }

.section-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: #475569;
    margin: 32px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <div class="hero-title">Investment Valuation<br><em>Toolkit</em></div>
  <div class="hero-subtitle">
    A chapter-by-chapter implementation of Damodaran's valuation framework —
    every formula explained, scored, and ready for live data.
  </div>
  <div class="hero-source">
    Based on: Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed. (2002) ·
    35 chapters · 65 Excel models
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Module cards
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Modules</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 01</div>
  <div class="module-title">📐 Cost of Capital</div>
  <div class="module-desc">
    Synthetic credit rating from interest coverage ratio.
    Hamada equation to unlever and re-lever beta.
    WACC from market-value weights. Country risk premia.
    Operating lease and R&D capitalisation adjustments.
  </div>
  <div class="module-chapters">Chapters 7–8 · ratings.xls · levbeta.xls · wacccalc.xls</div>
  <span class="status-live">✓ Live</span>
</div>
""", unsafe_allow_html=True)
    if st.button("Open module →", key="go_coc", use_container_width=True):
        st.switch_page("pages/1_Cost_of_Capital.py")

with col2:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 02</div>
  <div class="module-title">💵 Cash Flow Valuation</div>
  <div class="module-desc">
    Six models: FCFF stable, 2-stage, 3-stage; FCFE stable,
    2-stage, 3-stage. Fundamental growth from ROC × reinvestment.
    Terminal value from perpetuity. Full equity bridge.
  </div>
  <div class="module-chapters">Chapters 9–10, 14–15 · fcffst/2st/3st.xls · fcfeginzu.xls</div>
  <span class="status-live">✓ Live</span>
</div>
""", unsafe_allow_html=True)
    if st.button("Open module →", key="go_cf", use_container_width=True):
        st.switch_page("pages/2_Cash_Flows.py")

with col3:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 03</div>
  <div class="module-title">📈 Growth & Terminal Value</div>
  <div class="module-desc">
    Historical, analyst, and fundamental growth estimates.
    ROC and ROE decomposition. Terminal value sensitivity.
    Stable-period consistency checks.
  </div>
  <div class="module-chapters">Chapter 11–12 · chgrowth.xls</div>
  <span class="status-building">⟳ Building</span>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='padding:6px 0;color:#475569;font-size:0.82rem'>Coming soon</div>",
                unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
col4, col5, col6 = st.columns(3)

with col4:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 04</div>
  <div class="module-title">⚖️ Relative Valuation</div>
  <div class="module-desc">
    Justified PE, PBV, PEG from fundamentals. EV/EBITDA
    and EV/Sales multiples. Regression-based comparables.
    Industry benchmark tables.
  </div>
  <div class="module-chapters">Chapters 17–21 · eqmult.xls · firmmult.xls</div>
  <span class="status-planned">· Planned</span>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='padding:6px 0;color:#475569;font-size:0.82rem'>Coming soon</div>",
                unsafe_allow_html=True)

with col5:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 05</div>
  <div class="module-title">🏗️ Optimal Capital Structure</div>
  <div class="module-desc">
    Sweep debt ratios 0–90%. Synthetic rating at each level.
    Indirect bankruptcy cost haircuts. WACC-minimising
    and firm-value-maximising optimal point.
  </div>
  <div class="module-chapters">Chapter 15 · capstru.xlsx · apv.xls</div>
  <span class="status-planned">· Planned</span>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='padding:6px 0;color:#475569;font-size:0.82rem'>Coming soon</div>",
                unsafe_allow_html=True)

with col6:
    st.markdown("""
<div class="module-card">
  <div class="module-number">Module 06</div>
  <div class="module-title">🔬 Special Cases</div>
  <div class="module-desc">
    Financial firms (excess return model). Negative-earnings
    firms. Distressed firm survival probability. Real options.
    Private company illiquidity discount.
  </div>
  <div class="module-chapters">Chapters 21–22, 28–30 · distress.xls · equity.xls</div>
  <span class="status-planned">· Planned</span>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='padding:6px 0;color:#475569;font-size:0.82rem'>Coming soon</div>",
                unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Core formulas strip
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Core formulas</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown("""
<div class="formula-strip">
WACC  =  ke × (E/V)  +  kd × (1−t) × (D/V)<br>
ke    =  rf  +  β × ERP<br>
β_u   =  β_L / [1 + (1−t) × D/E]<br>
kd    =  rf  +  company_spread  +  country_spread
</div>
""", unsafe_allow_html=True)

with c2:
    st.markdown("""
<div class="formula-strip">
FCFF  =  EBIT × (1−t)  −  Net_CapEx  −  ΔWC<br>
FCFE  =  NI  −  (1−δ) × (Net_CapEx + ΔWC)<br>
g     =  ROC × Reinvestment_Rate<br>
TV    =  FCFF_{n+1} / (WACC − g_stable)
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Data status
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Data sources</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown("""
<div class="data-row"><div class="data-dot-pending"></div>
  <strong>Yahoo Finance</strong> — Beta, market cap, financials (EBIT, NI, CapEx, WC)
</div>
<div class="data-row"><div class="data-dot-pending"></div>
  <strong>SEC EDGAR</strong> — 10-K filings, debt schedule, lease footnotes
</div>
<div class="data-row"><div class="data-dot-pending"></div>
  <strong>FRED (St. Louis Fed)</strong> — 10-year Treasury yield (risk-free rate)
</div>
""", unsafe_allow_html=True)

with c2:
    st.markdown("""
<div class="data-row"><div class="data-dot-pending"></div>
  <strong>Damodaran datasets</strong> — Industry betas, ERP, country spreads (Jan 2026)
</div>
<div class="data-row"><div class="data-dot-todo"></div>
  <strong>All modules</strong> — Currently using placeholder data
</div>
<div class="data-row" style="border:none"><div class="data-dot-todo"></div>
  Live connection wiring in progress — complete before Phase 3
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="font-size:0.75rem;color:#334155;text-align:center;padding:40px 0 20px 0;border-top:1px solid #1e293b;margin-top:48px">
Aswath Damodaran, <em>Investment Valuation: Tools and Techniques for Determining the Value of Any Asset</em>,
2nd Edition, Wiley Finance, 2002 · Spreads updated January 2026
</div>
""", unsafe_allow_html=True)
