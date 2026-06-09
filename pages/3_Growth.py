"""pages/3_Growth.py — Growth & Terminal Value with live data"""
import streamlit as st
import pandas as pd
from data_fetcher import get_company_data, source_badge_html
from growth_models import estimate_growth, terminal_value_gordon, benchmark_vs_industry, INDUSTRY_NAMES, INDUSTRY_DATA
from cost_of_capital import full_cost_of_capital

st.set_page_config(page_title="Growth & Terminal Value", page_icon="📈", layout="wide")
pg_id = "3"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box { background:#1e293b; border-left:3px solid #3b82f6; border-radius:0 8px 8px 0; padding:14px 18px; margin:10px 0 18px 0; font-size:0.88rem; line-height:1.7; color:#cbd5e1; }
.check-pass { background:#14532d; color:#86efac; border-radius:8px; padding:10px 14px; margin:6px 0; font-size:0.87rem; }
.check-fail { background:#7f1d1d; color:#fca5a5; border-radius:8px; padding:10px 14px; margin:6px 0; font-size:0.87rem; }
.score-pill { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.8rem; font-weight:500; margin-top:6px; }
.score-green{background:#14532d;color:#86efac;} .score-yellow{background:#713f12;color:#fde68a;} .score-red{background:#7f1d1d;color:#fca5a5;}
</style>""", unsafe_allow_html=True)

def badge(s,t,c): return f'<span class="score-pill score-{c}">Score {s}/10 — {t[:65]}</span>'
def score_growth(g, ind=None):
    if ind and g > ind*3: return 3,"Far above industry median — verify sustainability","red"
    elif g > .30: return 4,"Very high (>30%) — few firms sustain this","yellow"
    elif g > .15: return 7,"High — realistic for early-stage firms","green"
    elif g > .05: return 8,"Moderate — normal corporate range","green"
    elif g > 0: return 7,"Low — appropriate for mature businesses","green"
    else: return 5,"Negative — declining or temporary trough","yellow"
def score_roc(roc, wacc):
    ex = roc-wacc
    if ex > .15: return 9,f"ROC {ex:.1%} above WACC — strong value creation","green"
    elif ex > .05: return 8,f"ROC {ex:.1%} above WACC — healthy returns","green"
    elif ex > 0: return 6,f"Marginal excess return {ex:.1%}","yellow"
    elif ex > -.03: return 4,"ROC ≈ WACC — earns cost of capital but little more","yellow"
    else: return 2,f"ROC {abs(ex):.1%} below WACC — growth destroys value","red"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 Growth & Terminal Value")
    d = st.session_state.get("company_data")
    if d:
        st.markdown(source_badge_html(d), unsafe_allow_html=True)
        st.caption(d.name)
    else:
        st.warning("No data loaded. Go to the home page and click **Load company data**.")
    st.markdown("---")
    industry = st.selectbox("Industry (for benchmarks)", ["(None)"] + INDUSTRY_NAMES, key=f"ind_{pg_id}")
    industry = None if industry == "(None)" else industry
    g_stable = st.number_input("Stable growth rate", value=0.03, format="%.3f", key=f"gst_{pg_id}")
    stable_roc = st.number_input("Stable ROC", value=0.12, format="%.3f", key=f"sroc_{pg_id}")
    rf = st.number_input("Risk-free rate", value=float(d.rf) if d else 0.045, format="%.3f", key=f"rf_{pg_id}")

# ── Header ────────────────────────────────────────────────────────────────────
name = d.name if d else "—"
ticker = d.ticker if d else ""
st.title(f"📈 Growth & Terminal Value — {name}")
if not d:
    st.info("Go to the home page, enter a ticker and click **Load company data**, then return here.")
    st.stop()

st.markdown(source_badge_html(d), unsafe_allow_html=True)
st.divider()

# Get WACC
coc_key = f"coc_{d.ticker}_{pg_id}"
if coc_key not in st.session_state:
    try:
        coc = full_cost_of_capital(ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=d.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=d.firm_type)
        st.session_state[coc_key] = coc
    except: st.session_state[coc_key] = None
coc = st.session_state.get(coc_key)
wacc_val = coc.wacc_result.wacc if coc else 0.09

tab1, tab2, tab3 = st.tabs(["📊 Growth Estimation", "🔭 Terminal Value", "🏭 Industry Benchmark"])

# ── Tab 1: Growth ─────────────────────────────────────────────────────────────
with tab1:
    st.markdown("## Growth Estimation")
    st.markdown("All three approaches computed from live data. Adjust any input below.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Fundamental inputs**")
        ebit    = st.number_input("EBIT ($m)",             value=float(d.ebit),         key="ge_ebit")
        tax     = st.number_input("Tax rate",              value=float(d.tax_rate),     key="ge_tax", format="%.3f")
        net_capex=st.number_input("Net CapEx ($m)",        value=float(d.capex-d.depreciation), key="ge_ncx")
        dwc     = st.number_input("ΔWC ($m)",              value=float(d.delta_wc),     key="ge_dwc")
        bk_eq   = st.number_input("Book Equity ($m)",      value=float(d.book_equity),  key="ge_beq")
        bk_dt   = st.number_input("Book Debt ($m)",        value=float(d.book_debt),    key="ge_bdt")
        ni      = st.number_input("Net Income ($m)",       value=float(d.net_income),   key="ge_ni")
        divs    = st.number_input("Dividends ($m)",        value=0.0,                   key="ge_div")
    with col2:
        st.markdown("**Historical EPS** (oldest → newest)")
        if d.historical_eps:
            default_eps = ", ".join(f"{v:.2f}" for v in d.historical_eps[-8:])
        else:
            default_eps = ""
        eps_str = st.text_area("EPS history", value=default_eps, height=80, key="ge_eps",
                                help="Pulled from yfinance quarterly/annual data")
        st.markdown("**Historical Revenue** (optional)")
        if d.historical_revenue:
            default_rev = ", ".join(f"{v:.0f}" for v in d.historical_revenue[-8:])
        else:
            default_rev = ""
        rev_str = st.text_area("Revenue history", value=default_rev, height=80, key="ge_rev")
    with col3:
        st.markdown("**Analyst estimate**")
        analyst_g = st.number_input("Analyst growth (0 = none)", value=0.0, format="%.3f", key="ge_ag")
        analyst_g = analyst_g if analyst_g > 0 else None
        st.markdown("**Blend weights**")
        w_hist = st.slider("Historical weight", 0, 100, 40, key="ge_wh")
        w_anal = st.slider("Analyst weight", 0, 100, 0 if not analyst_g else 30, key="ge_wa")
        w_fund = 100 - w_hist - w_anal
        st.caption(f"Fundamental weight: {w_fund}%")
        if w_fund < 0: st.error("Weights exceed 100%")

    def parse_series(s):
        try: return [float(x.strip()) for x in s.split(",") if x.strip()]
        except: return None

    hist_eps = parse_series(eps_str)
    hist_rev = parse_series(rev_str) if rev_str.strip() else None

    try:
        g = estimate_growth(
            ebit=ebit, tax_rate=tax, net_capex=net_capex, delta_wc=dwc,
            book_equity=bk_eq, book_debt=bk_dt, net_income=ni, dividends=divs,
            historical_eps=hist_eps, historical_rev=hist_rev,
            analyst_growth=analyst_g, industry=industry,
        )

        st.divider()
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Fundamental g (firm)",   f"{g.fundamental_growth_firm:.2%}")
        c2.metric("Fundamental g (equity)", f"{g.fundamental_growth_equity:.2%}")
        c3.metric("Recommended growth",     f"{g.recommended_growth:.2%}")
        c4.metric("ROC",                    f"{g.roc:.2%}")

        s_g,t_g,c_g = score_growth(g.recommended_growth, g.industry_rev_g_median)
        s_r,t_r,c_r = score_roc(g.roc, wacc_val)
        st.markdown(badge(s_g,t_g,c_g)+"&nbsp;&nbsp;"+badge(s_r,t_r,c_r), unsafe_allow_html=True)

        st.markdown(f"""<div class="explain-box">
<strong>Build-up:</strong><br>
ROC = EBIT×(1−t)/IC = {ebit*(1-tax):,.0f}/{bk_eq+bk_dt:,.0f} = <strong>{g.roc:.2%}</strong><br>
RIR = (Net CapEx + ΔWC)/NOPAT = {net_capex+dwc:,.0f}/{ebit*(1-tax):,.0f} = <strong>{g.reinvestment_rate:.2%}</strong><br>
Fundamental g (firm) = {g.roc:.2%} × {g.reinvestment_rate:.2%} = <strong>{g.fundamental_growth_firm:.2%}</strong><br>
ROE = NI/BV_Equity = {ni:,.0f}/{bk_eq:,.0f} = <strong>{g.roe:.2%}</strong><br>
{"Historical EPS CAGR: <strong>" + f"{g.historical_eps_cagr:.2%}</strong><br>" if g.historical_eps_cagr else ""}
<strong>Recommended: {g.recommended_growth:.2%}</strong> — {g.recommended_basis}
{"<br>Industry median: <strong>" + f"{g.industry_rev_g_median:.2%}</strong> ({industry})" if g.industry_rev_g_median else ""}
</div>""", unsafe_allow_html=True)

        df = pd.DataFrame([
            ["Fundamental (firm)",   f"{g.fundamental_growth_firm:.2%}",   "ROC × RIR"],
            ["Fundamental (equity)", f"{g.fundamental_growth_equity:.2%}", "ROE × Retention"],
            ["Historical EPS CAGR",  f"{g.historical_eps_cagr:.2%}" if g.historical_eps_cagr else "N/A", "Geometric mean"],
            ["Analyst estimate",     f"{g.analyst_growth:.2%}" if g.analyst_growth else "N/A", "Consensus"],
            ["Recommended blend",    f"{g.recommended_growth:.2%}", g.recommended_basis],
        ], columns=["Approach","Growth Rate","Basis"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Growth calculation error: {e}")

# ── Tab 2: Terminal Value ─────────────────────────────────────────────────────
with tab2:
    st.markdown("## Terminal Value")
    col1, col2 = st.columns(2)
    with col1:
        cf_final  = st.number_input("Final year FCFF ($m)", value=float(max(d.fcff,100)), key="tv_cf")
        disc_rate = st.number_input("WACC (stable)",        value=round(wacc_val,4),      key="tv_dr", format="%.4f")
        tv_g      = st.number_input("Stable growth rate",   value=g_stable,              key="tv_g",  format="%.3f")
        tv_roc    = st.number_input("Stable ROC",           value=stable_roc,            key="tv_roc",format="%.3f")
    with col2:
        st.markdown("**Damodaran consistency rules:**")
        st.markdown(f"""<div class="explain-box" style="margin-top:0">
1. g ≤ rf ({rf:.2%}) — firm cannot grow faster than economy<br>
2. ROC → WACC in stable period — competition erodes excess returns<br>
3. Reinvest consistently: RIR = g/ROC = {tv_g:.2%}/{tv_roc:.2%} = {tv_g/tv_roc:.1%}
</div>""", unsafe_allow_html=True)

    try:
        tv = terminal_value_gordon(cf_final, disc_rate, tv_g, tv_roc)
        c1,c2,c3 = st.columns(3)
        c1.metric("Terminal Value", f"${tv.terminal_value:,.0f}m")
        c2.metric("TV Multiple",    f"{tv.terminal_value/cf_final:.1f}×")
        c3.metric("Stable RIR",     f"{tv_g/tv_roc:.1%}")

        st.markdown("### Consistency checks")
        for k,v in tv.checks.items():
            css = "check-pass" if v["pass"] else "check-fail"
            st.markdown(f'<div class="{css}">{"✓" if v["pass"] else "✗"} <strong>{v["label"]}</strong><br>{v["detail"]}</div>', unsafe_allow_html=True)

        st.markdown("### Sensitivity table")
        g_vals = sorted(set(k[0] for k in tv.sensitivity)); r_vals = sorted(set(k[1] for k in tv.sensitivity))
        rows = []
        for g2 in g_vals:
            row = {"g \\ WACC": f"{g2:.2%}"}
            for r2 in r_vals: row[f"{r2:.2%}"] = f"${tv.sensitivity.get((g2,r2)):,.0f}" if tv.sensitivity.get((g2,r2)) else "—"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows).set_index("g \\ WACC"), use_container_width=True)

    except ValueError as e:
        st.error(str(e))

# ── Tab 3: Industry ───────────────────────────────────────────────────────────
with tab3:
    st.markdown("## Industry Benchmark")
    if not industry:
        st.info("Select an industry in the sidebar.")
    else:
        d2 = INDUSTRY_DATA[industry]
        rev_g = d.revenue  # will use growth rate
        col1, col2 = st.columns(2)
        with col1:
            bm_rg  = st.number_input("Revenue growth",  value=0.10, format="%.3f")
            bm_mg  = st.number_input("EBIT margin",     value=float(d.ebit/d.revenue) if d.revenue>0 else 0.15, format="%.3f")
        with col2:
            bm_s2c = st.number_input("Sales/Capital",   value=float(d.revenue/(d.book_equity+d.book_debt)) if (d.book_equity+d.book_debt)>0 else 1.5, format="%.2f")
            bm_wc  = st.number_input("WACC",            value=round(wacc_val,4), format="%.4f")

        from growth_models import benchmark_vs_industry
        bm = benchmark_vs_industry(industry, bm_rg, bm_mg, bm_s2c, bm_wc)
        for key, (label, fmt) in [("revenue_growth","Revenue Growth",".1%"), ("ebit_margin","EBIT Margin",".1%"), ("sales_to_capital","Sales/Capital",".2f"), ("wacc","WACC",".1%")]:
            if key not in bm: continue
            data = bm[key]
            pos = data["position"]
            colour = "green" if pos in ("3rd quartile","top quartile") else ("yellow" if pos=="2nd quartile" else "red")
            if key == "wacc": colour = "green" if pos != "top quartile" else "yellow"
            st.markdown(f"**{label}**: `{data['value']:{fmt}}` — {pos}  (Q1:{data['q1']:{fmt}} · Med:{data['median']:{fmt}} · Q3:{data['q3']:{fmt}})")
            st.markdown(f'<span class="score-pill score-{colour}">{pos}</span>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

st.divider()
st.markdown('<div style="font-size:0.75rem;color:#475569;text-align:center">Damodaran, Ch 11–12 · chgrowth.xls · fcffsimpleginzu.xlsx industry data (Jan 2026)</div>', unsafe_allow_html=True)
