"""app.py — Home page + global ticker input"""
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
.hero { background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%); border:1px solid #1e3a5f; border-radius:16px; padding:48px 56px; margin-bottom:32px; }
.hero-title { font-family:'DM Serif Display',serif; font-size:3rem; font-weight:400; letter-spacing:-1px; color:#f1f5f9; line-height:1.15; margin:0 0 12px; }
.hero-subtitle { font-size:1.1rem; color:#94a3b8; font-weight:300; margin:0 0 8px; }
.hero-source { font-size:0.82rem; color:#475569; font-style:italic; }
.module-card { background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:24px 28px; height:100%; }
.module-card:hover { border-color:#3b82f6; }
.module-number { font-size:0.72rem; text-transform:uppercase; letter-spacing:3px; color:#3b82f6; margin-bottom:8px; }
.module-title { font-family:'DM Serif Display',serif; font-size:1.35rem; color:#f1f5f9; margin-bottom:8px; }
.module-desc { font-size:0.87rem; color:#94a3b8; line-height:1.6; margin-bottom:16px; }
.module-chapters { font-size:0.75rem; color:#475569; margin-bottom:12px; }
.status-live { display:inline-block; font-size:0.72rem; padding:3px 10px; border-radius:20px; background:#14532d; color:#86efac; font-weight:500; }
.formula-strip { background:#1e293b; border-radius:8px; padding:14px 20px; font-family:'DM Mono','Courier New',monospace; font-size:0.82rem; color:#7dd3fc; margin:6px 0; line-height:1.6; }
.section-label { font-size:0.72rem; text-transform:uppercase; letter-spacing:3px; color:#475569; margin:32px 0 16px; }
.ticker-box { background:#0f172a; border:1px solid #3b82f6; border-radius:12px; padding:24px 28px; margin-bottom:32px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Global ticker input — THE single entry point for all data
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Company</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="ticker-box">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        ticker_input = st.text_input(
            "Ticker",
            value=st.session_state.get("ticker", "AAPL"),
            placeholder="e.g. AAPL, MSFT, TSLA, JPM",
            key="ticker_input_home",
        )
    with col2:
        fred_key_input = st.text_input(
            "FRED API key",
            value=st.session_state.get("fred_key", ""),
            type="password",
            placeholder="Paste your FRED API key here",
            help="Free at fred.stlouisfed.org — used for the 10-yr Treasury yield (risk-free rate)",
            key="fred_key_input_home",
        )
    with col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        fetch_clicked = st.button(
            "🔄 Load company data",
            type="primary",
            use_container_width=True,
            key="home_fetch",
        )
    st.markdown('</div>', unsafe_allow_html=True)

# Fetch on button click
if fetch_clicked and ticker_input.strip():
    ticker_clean = ticker_input.upper().strip()
    with st.spinner(f"Fetching {ticker_clean} from yfinance, EDGAR, FRED…"):
        try:
            from data_fetcher import get_company_data
            d = get_company_data(ticker_clean, fred_api_key=fred_key_input, force_refresh=True)
            d.ebitda = d.ebitda or (d.ebit + d.depreciation)
            d.fcff   = d.ebit * (1 - d.tax_rate) - (d.capex - d.depreciation) - d.delta_wc
            st.session_state["company_data"] = d
            st.session_state["ticker"]       = ticker_clean
            st.session_state["fred_key"]     = fred_key_input
        except Exception as e:
            st.error(f"Fetch failed: {e}")

# Status bar
d = st.session_state.get("company_data")
if d:
    from data_fetcher import source_badge_html
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            f"**{d.name}** ({d.ticker}) &nbsp;·&nbsp; "
            f"Price **${d.price:.2f}** &nbsp;·&nbsp; "
            f"Market cap **${d.equity_market_cap:,.0f}m** &nbsp;·&nbsp; "
            f"EBIT **${d.ebit:,.0f}m** &nbsp;·&nbsp; "
            f"rf **{d.rf:.2%}** &nbsp; "
            + source_badge_html(d),
            unsafe_allow_html=True,
        )
        if d.fetch_errors:
            with st.expander("⚠ Data warnings"):
                for e in d.fetch_errors: st.caption(e)
    with col2:
        st.markdown(f"<div style='text-align:right;font-size:0.8rem;color:#475569'>Navigate to any module →<br>data will be pre-loaded</div>", unsafe_allow_html=True)
else:
    st.info("Enter a ticker above and click **Load company data** — all six modules will use the same data.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <div class="hero-title">Investment Valuation<br><em>Toolkit</em></div>
  <div class="hero-subtitle">A chapter-by-chapter implementation of Damodaran's valuation framework — every formula explained, scored, and ready for live data.</div>
  <div class="hero-source">Based on: Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed. (2002) · 35 chapters · 65 Excel models</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Module cards
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Modules</div>', unsafe_allow_html=True)

MODULES = [
    ("01", "📐", "Cost of Capital",      "Synthetic credit rating · Hamada beta · WACC · Country risk · Lease & R&D adjustments.",     "Ch 7–8 · ratings.xls · levbeta.xls · wacccalc.xls",      "./1_Cost_of_Capital"),
    ("02", "💵", "Cash Flow Valuation",   "FCFF & FCFE — stable, 2-stage, 3-stage. Terminal value. Full equity bridge.",                  "Ch 9–10, 14–15 · fcffst/2st/3st.xls · fcfeginzu.xls",    "./2_Cash_Flows"),
    ("03", "📈", "Growth & Terminal Value","Three growth approaches · TV consistency checks · Industry benchmark quartiles.",             "Ch 11–12 · chgrowth.xls",                                  "./3_Growth"),
    ("04", "⚖️", "Relative Valuation",    "Justified PE, PBV, PEG, EV/EBITDA, EV/Sales · Industry comparison table.",                   "Ch 17–21 · eqmult.xls · firmmult.xls",                    "./4_Relative_Valuation"),
    ("05", "🏗️", "Optimal Capital Structure","Debt ratio sweep · Bankruptcy costs · WACC minimisation · Repurchase analysis.",         "Ch 15 · capstru.xlsx",                                     "./5_Optimal_Capital_Structure"),
    ("06", "🔬", "Special Cases",         "EVA equivalence · Distressed firm adjustment · Financial firm excess returns · Normalisation.","Ch 21–22, 30, 32 · fcffeva.xls · fcffsimpleginzu.xlsx",   "./6_Special_Cases"),
]

col1, col2, col3 = st.columns(3)
for i, (num, icon, title, desc, chapters, link) in enumerate(MODULES):
    with [col1, col2, col3][i % 3]:
        st.markdown(f"""
<div class="module-card">
  <div class="module-number">Module {num}</div>
  <div class="module-title">{icon} {title}</div>
  <div class="module-desc">{desc}</div>
  <div class="module-chapters">{chapters}</div>
  <span class="status-live">✓ Live</span>
</div>
""", unsafe_allow_html=True)
        st.markdown(f"[Open →]({link})")
    if i == 2:
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)

# ─────────────────────────────────────────────────────────────────────────────
# Formulas
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Core formulas</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="formula-strip">WACC = ke×(E/V) + kd×(1−t)×(D/V)<br>ke = rf + β×ERP<br>β_u = β_L / [1+(1−t)×D/E]<br>kd = rf + company_spread + country_spread</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="formula-strip">FCFF = EBIT×(1−t) − Net_CapEx − ΔWC<br>FCFE = NI − (1−δ)×(Net_CapEx+ΔWC)<br>g = ROC × Reinvestment_Rate<br>TV = FCFF_{n+1} / (WACC − g_stable)</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Report download
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">Download Report</div>', unsafe_allow_html=True)

if not d:
    st.info("Load a company above before generating a report.")
else:
    with st.expander("⚙ Assumptions (optional — uses sensible defaults if left at 0)"):
        ac1, ac2, ac3 = st.columns(3)
        g_high_r    = ac1.number_input("High-growth rate (0 = auto)",   value=0.0,  format="%.3f", key="r_gh")
        n_high_r    = ac1.number_input("High-growth years",             value=5,    step=1,         key="r_nh")
        g_stable_r  = ac2.number_input("Stable growth rate",            value=0.03, format="%.3f", key="r_gs")
        stable_roc_r= ac2.number_input("Stable ROC",                    value=0.12, format="%.3f", key="r_roc")
        erp_r       = ac3.number_input("Equity risk premium",           value=0.055,format="%.3f", key="r_erp")

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        generate_clicked = st.button(
            f"⬇ Generate report for {d.ticker}",
            type="primary", use_container_width=True, key="gen_report",
        )
    with col_info:
        st.markdown(f"<div style='font-size:0.85rem;color:#64748b;padding-top:8px'>Will run all 6 modules on <strong>{d.name}</strong> and produce a self-contained HTML file.</div>", unsafe_allow_html=True)

    if generate_clicked:
        with st.spinner(f"Running all 6 modules for {d.ticker}…"):
            try:
                from report_generator import generate_report, ReportAssumptions
                from datetime import datetime

                a = ReportAssumptions(
                    g_high=g_high_r, n_high=int(n_high_r),
                    g_stable=g_stable_r, stable_roc=stable_roc_r, erp=erp_r,
                )
                html = generate_report(d, a)
                filename = f"{d.ticker}_valuation_{datetime.now().strftime('%Y%m%d')}.html"
                st.success(f"✓ Report ready — {len(html):,} bytes · {len(html.split(chr(10)))} lines")
                st.download_button(
                    label=f"⬇ Download {filename}",
                    data=html, file_name=filename, mime="text/html",
                    use_container_width=True,
                )
                if d.source != "live":
                    st.warning(f"⚠ Data source: {d.source}. Some fields may use estimates.", icon="⚠️")
            except Exception as e:
                st.error(f"Report generation failed: {e}")
                import traceback; st.code(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="font-size:0.75rem;color:#334155;text-align:center;padding:40px 0 20px;border-top:1px solid #1e293b;margin-top:48px">
Aswath Damodaran, <em>Investment Valuation: Tools and Techniques for Determining the Value of Any Asset</em>,
2nd Edition, Wiley Finance, 2002 · Spreads updated January 2026
</div>
""", unsafe_allow_html=True)
