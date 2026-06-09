"""pages/6_Special_Cases.py — Special Cases with live data"""
import streamlit as st
import pandas as pd
from data_fetcher import get_company_data, source_badge_html
from special_cases import (
    eva_valuation, distressed_firm_value, financial_firm_excess_returns,
    normalise_earnings, default_probability_from_rating,
    DEFAULT_PROB_BY_RATING, RATING_NAMES, INDUSTRY_NAMES_SC, SURVIVAL_BY_INDUSTRY,
    default_probability_from_industry_age,
)
from cost_of_capital import full_cost_of_capital
from fcff_models import fcff_2stage

st.set_page_config(page_title="Special Cases", page_icon="🔬", layout="wide")
pg_id = "6"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box{background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:10px 0 18px 0;font-size:0.88rem;line-height:1.7;color:#cbd5e1;}
.check-pass{background:#14532d;color:#86efac;border-radius:8px;padding:10px 14px;margin:6px 0;font-size:0.87rem;}
.check-fail{background:#7f1d1d;color:#fca5a5;border-radius:8px;padding:10px 14px;margin:6px 0;font-size:0.87rem;}
.score-pill{display:inline-block;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:500;margin-top:6px;}
.score-green{background:#14532d;color:#86efac;} .score-yellow{background:#713f12;color:#fde68a;} .score-red{background:#7f1d1d;color:#fca5a5;}
</style>""", unsafe_allow_html=True)

def badge(s,t,c): return f'<span class="score-pill score-{c}">Score {s}/10 — {t[:65]}</span>'
def score_eva(er):
    if er>.10: return 9,f"ROC {er:.1%} above WACC — exceptional value creation","green"
    elif er>.05: return 8,f"Healthy {er:.1%} excess return","green"
    elif er>0: return 6,f"Marginal {er:.1%} excess return","yellow"
    elif er>-.03: return 4,"ROC ≈ WACC — value-neutral","yellow"
    else: return 2,f"ROC {abs(er):.1%} below WACC — destroying value","red"
def score_distress(p):
    if p<.01: return 9,f"Negligible risk ({p:.2%})","green"
    elif p<.05: return 7,f"Low risk ({p:.2%})","green"
    elif p<.15: return 5,f"Moderate risk ({p:.2%})","yellow"
    elif p<.35: return 3,f"High risk ({p:.2%})","red"
    else: return 1,f"Very high risk ({p:.2%})","red"

with st.sidebar:
    st.markdown("## 🔬 Special Cases")
    ticker = st.text_input("Ticker", value="AAPL", key=f"ticker_{pg_id}").upper()
    fred_key = st.text_input("FRED API key (optional)", type="password", key=f"fred_{pg_id}")
    if st.button("🔄 Fetch live data", key=f"fetch_{pg_id}", type="primary"):
        with st.spinner(f"Fetching {ticker}…"):
            _d = get_company_data(ticker, fred_api_key=fred_key, force_refresh=True)
            st.session_state[f"live_{pg_id}"] = _d
            st.rerun()
    d = st.session_state.get(f"live_{pg_id}")
    if d: st.markdown(source_badge_html(d), unsafe_allow_html=True); st.caption(d.name)
    else: st.markdown('<span style="font-size:0.72rem;padding:2px 8px;border-radius:4px;background:#3b2a0f;color:#fbbf24">⚠ Enter ticker and fetch</span>', unsafe_allow_html=True)

name = d.name if d else "—"
st.title(f"🔬 Special Cases — {name}")
if not d: st.info("Enter a ticker and fetch data."); st.stop()
st.markdown(source_badge_html(d), unsafe_allow_html=True); st.divider()

# CoC
coc_key = f"coc_{ticker}_{pg_id}"
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
ke_val   = coc.beta_result.ke   if coc else 0.10
rating   = coc.debt_cost.rating if coc else "Baa2/BBB"
# Normalise rating for lookup
rating_simple = "AAA" if "AAA" in rating else "AA" if "AA" in rating else "A" if "/A" in rating and "BBB" not in rating else "BBB" if "BBB" in rating else "BB" if "BB" in rating else "B" if "/B" in rating else "CCC/C"

tab1, tab2, tab3, tab4 = st.tabs(["📊 EVA Framework","⚠️ Distressed","🏦 Financial Firm","📉 Normalise Earnings"])

# ── Tab 1: EVA ────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("## EVA Framework")
    st.markdown("Prove DCF = Capital + PV(EVA). Source: fcffeva.xls")

    # Build EVA from live data using the FCFF 2-stage outputs as proxy
    nopat_current = d.ebit * (1 - d.tax_rate)
    ic_current    = d.book_equity + d.book_debt
    eva_current   = nopat_current - wacc_val * ic_current
    roc_current   = nopat_current / ic_current if ic_current > 0 else 0

    col1, col2 = st.columns(2)
    with col1:
        init_cap = st.number_input("Initial invested capital ($m)", value=float(ic_current), key="ev_ic")
        fcff_ref = st.number_input("FCFF firm value (cross-check $m)", value=float(max(d.fcff*10,1000)), key="ev_fv",
                                    help="Paste value from Module 02 to verify equivalence")
        g_stable_ev = st.number_input("Stable growth rate", value=0.03, format="%.3f", key="ev_g")
        term_roc    = st.number_input("Terminal ROC",       value=round(roc_current,4),    format="%.4f", key="ev_tr")
    with col2:
        st.markdown("**Current year EVA:**")
        c1,c2,c3 = st.columns(3)
        c1.metric("NOPAT", f"${nopat_current:,.0f}m")
        c2.metric("WACC Charge", f"${wacc_val*ic_current:,.0f}m")
        c3.metric("EVA", f"${eva_current:,.0f}m", delta="positive" if eva_current>0 else "negative")
        s,t,c = score_eva(roc_current - wacc_val)
        st.markdown(badge(s,t,c), unsafe_allow_html=True)
        st.markdown(f"""<div class="explain-box">
ROC = NOPAT/IC = {nopat_current:,.0f}/{ic_current:,.0f} = <strong>{roc_current:.2%}</strong><br>
WACC = <strong>{wacc_val:.2%}</strong><br>
EVA = ({roc_current:.2%} − {wacc_val:.2%}) × {ic_current:,.0f} = <strong>${eva_current:,.0f}m</strong><br>
{"✓ Company is creating value" if eva_current>0 else "✗ Company is destroying value"}
</div>""", unsafe_allow_html=True)

    st.markdown("#### Grow EVA over forecast horizon (uses FCFF model parameters)")
    st.caption("Enter year-by-year NOPAT, Capital, WACC from Module 02 output to run full EVA equivalence")
    nopat_str = st.text_area("NOPAT ($m) years 1–5+", key="ev_np",
        value=", ".join(f"{nopat_current*(1.10**t):.0f}" for t in range(1,6)), height=60)
    capital_str = st.text_area("Invested Capital ($m) years 1–5+", key="ev_cp",
        value=", ".join(f"{ic_current*(1.08**t):.0f}" for t in range(1,6)), height=60)
    wacc_str = st.text_area("WACC years 1–5+", key="ev_wc",
        value=", ".join(f"{wacc_val:.4f}" for _ in range(5)), height=60)

    if st.button("Run EVA equivalence →", type="primary", key="btn_eva"):
        def pf(s): return [float(x.strip()) for x in s.split(",") if x.strip()]
        try:
            nopat_s = pf(nopat_str); capital_s = pf(capital_str); wacc_s = [float(x.strip()) for x in wacc_str.split(",") if x.strip()]
            r = eva_valuation(init_cap, nopat_s, capital_s, wacc_s,
                terminal_nopat=nopat_s[-1]*(1+g_stable_ev),
                terminal_wacc=wacc_s[-1], terminal_roc=term_roc, g_stable=g_stable_ev,
                fcff_firm_value=fcff_ref)
            c1,c2,c3 = st.columns(3)
            c1.metric("Firm Value (EVA)", f"${r.firm_value:,.0f}m")
            c2.metric("FCFF Cross-check", f"${r.fcff_firm_value:,.0f}m")
            diff = abs(r.firm_value-r.fcff_firm_value)/r.fcff_firm_value*100 if r.fcff_firm_value else 0
            c3.metric("Difference", f"{diff:.2f}%")
            if diff < 2:
                st.markdown('<div style="background:#14532d22;border:1px solid #22c55e44;border-radius:8px;padding:12px;color:#86efac;font-size:0.87rem">✓ EVA = FCFF — the two frameworks confirm each other</div>', unsafe_allow_html=True)

            df = pd.DataFrame([{"Year":y,"NOPAT":f"${n:,.0f}","WACC Charge":f"${w:,.0f}","EVA":f"${e:,.0f}","ROC":f"{ro:.2%}","PV(EVA)":f"${p:,.0f}"} for y,n,w,e,ro,p in zip(r.years,r.nopat,r.wacc_charge,r.eva,r.roc,r.pv_eva)])
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e: st.error(str(e))

# ── Tab 2: Distressed ─────────────────────────────────────────────────────────
with tab2:
    st.markdown("## Distressed Firm Valuation")
    st.caption("Adjust going-concern value for probability of default")
    col1, col2 = st.columns(2)
    with col1:
        gc_val  = st.number_input("Going-concern firm value ($m)", value=float(d.equity_market_cap+d.book_debt), key="dr_gc")
        debt_d  = st.number_input("Debt outstanding ($m)",         value=float(d.book_debt), key="dr_d")
        cash_d  = st.number_input("Cash ($m)",                     value=float(d.cash),      key="dr_c")
        sh_d    = st.number_input("Shares (m)",                    value=float(d.shares),    key="dr_sh")
        pr_d    = st.number_input("Current price ($)",             value=float(d.price),     key="dr_pr")
    with col2:
        # Auto-suggest rating from Module 01
        rating_idx = RATING_NAMES.index(rating_simple) if rating_simple in RATING_NAMES else 3
        sel_rating = st.selectbox("Credit rating", RATING_NAMES, index=rating_idx, key="dr_rt")
        st.caption(f"Auto-detected from Module 01: {rating}")
        horizon = st.slider("Horizon (years)", 1, 5, 5, key="dr_hz")
        distress_v = st.number_input("Distress sale value ($m)", value=round(d.book_debt*0.6,0), key="dr_dv",
                                      help="Typically 50–70% of book debt — Altman fire-sale research")
        prob_df = pd.DataFrame({f"Yr{y+1}":[f"{v:.2%}" for v in probs] for y,probs in enumerate(zip(*DEFAULT_PROB_BY_RATING.values()))}, index=RATING_NAMES)
        st.dataframe(prob_df, use_container_width=True)

    p = default_probability_from_rating(sel_rating, horizon)
    r = distressed_firm_value(gc_val, debt_d, p, distress_v, sh_d, cash_d, sel_rating, horizon)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Default Prob",          f"{r.distress_probability:.2%}")
    c2.metric("GC Value/Share",        f"${r.value_per_share_gc:.2f}")
    c3.metric("Adjusted Value/Share",  f"${r.value_per_share_adjusted:.2f}", delta=f"{(r.value_per_share_adjusted/r.value_per_share_gc-1)*100:.1f}%" if r.value_per_share_gc > 0 else None)
    c4.metric("vs Market Price",       f"{(r.value_per_share_adjusted/pr_d-1)*100:+.1f}%" if pr_d > 0 else "N/A")
    s,t,c = score_distress(p); st.markdown(badge(s,t,c), unsafe_allow_html=True)
    st.markdown(f"""<div class="explain-box">
GC value: ${r.going_concern_value:,.0f}m × (1−{r.distress_probability:.2%}) = ${r.going_concern_value*(1-r.distress_probability):,.0f}m<br>
Distress proceeds: ${r.distress_sale_proceeds:,.0f}m × {r.distress_probability:.2%} = ${r.distress_sale_proceeds*r.distress_probability:,.0f}m<br>
Adjusted firm value: <strong>${r.adjusted_value:,.0f}m</strong> → Equity: <strong>${r.equity_adjusted:,.0f}m</strong>
</div>""", unsafe_allow_html=True)

# ── Tab 3: Financial Firm ─────────────────────────────────────────────────────
with tab3:
    st.markdown("## Financial Firm (Excess Returns Model)")
    st.caption("For banks and insurers. Value = Book Equity + PV(Excess Returns where ROE > ke)")
    col1, col2 = st.columns(2)
    with col1:
        bv_eq = st.number_input("Book equity ($m)", value=float(d.book_equity), key="ff_bv")
        sh_ff = st.number_input("Shares (m)",       value=float(d.shares),      key="ff_sh")
        pr_ff = st.number_input("Price ($)",        value=float(d.price),       key="ff_pr")
        roe_h = st.number_input("ROE (high)",       value=round(d.net_income/d.book_equity,4) if d.book_equity>0 else 0.15, format="%.4f", key="ff_rh")
        ke_h  = st.number_input("ke (high)",        value=round(ke_val,4),      format="%.4f", key="ff_kh")
        g_h   = st.number_input("Growth (high)",    value=0.08, format="%.3f",  key="ff_gh")
        n_h   = int(st.number_input("High-growth years", value=5, step=1,       key="ff_n"))
    with col2:
        roe_s = st.number_input("ROE (stable)",     value=round(ke_val*1.1,4),  format="%.4f", key="ff_rs")
        ke_s  = st.number_input("ke (stable)",      value=round(ke_val*0.9,4),  format="%.4f", key="ff_ks")
        g_s   = st.number_input("Stable growth",    value=0.03, format="%.3f",  key="ff_gs")

    try:
        r = financial_firm_excess_returns(bv_eq, roe_h, ke_h, g_h, n_h, roe_s, ke_s, g_s, sh_ff)
        pbv = r.value_of_equity/r.book_equity
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Book Equity",       f"${r.book_equity:,.0f}m")
        c2.metric("PV Excess Returns", f"${r.pv_excess_returns:,.0f}m")
        c3.metric("Equity Value",      f"${r.value_of_equity:,.0f}m")
        c4.metric("Value/Share",       f"${r.value_per_share:.2f}", delta=f"{(r.value_per_share/pr_ff-1)*100:+.1f}%" if pr_ff>0 else None)
        s,t,c = score_eva(r.excess_return); st.markdown(badge(s,t,c), unsafe_allow_html=True)
        st.markdown(f"""<div class="explain-box">
Excess return: ROE {roe_h:.2%} − ke {ke_h:.2%} = <strong>{r.excess_return:+.2%}/yr on book equity</strong><br>
PBV = {pbv:.2f}× — {"justified by ROE > ke" if r.excess_return>0 else "ROE < ke → should trade below book"}
</div>""", unsafe_allow_html=True)
    except Exception as e: st.error(str(e))

# ── Tab 4: Normalise ──────────────────────────────────────────────────────────
with tab4:
    st.markdown("## Earnings Normalisation")
    st.caption("For cyclical or temporarily-distressed firms with non-representative current earnings")
    col1, col2 = st.columns(2)
    with col1:
        curr_earn = st.number_input("Current earnings ($m)", value=float(d.net_income), key="nm_ce")
        curr_rev  = st.number_input("Current revenue ($m)",  value=float(d.revenue),   key="nm_cr")
        curr_ast  = st.number_input("Total assets ($m)",     value=float(d.total_assets), key="nm_ca")
        ind_roa   = st.number_input("Industry ROA (optional)", value=0.0, format="%.3f", key="nm_roa")
    with col2:
        default_he = ", ".join(f"{v:.0f}" for v in d.historical_eps[-8:]) if d.historical_eps else ""
        he_str = st.text_area("Historical earnings ($m)", value=default_he, height=80, key="nm_he",
                               help="Populated from yfinance historical data")
        default_hr = ", ".join(f"{v:.0f}" for v in d.historical_revenue[-8:]) if d.historical_revenue else ""
        hr_str = st.text_area("Historical revenues ($m)", value=default_hr, height=80, key="nm_hr")

    def pf(s): return [float(x.strip())*d.shares if d.shares and float(x.strip())<1000 else float(x.strip()) for x in s.split(",") if x.strip()] if s.strip() else []
    he = pf(he_str); hr = pf(hr_str) if hr_str.strip() else []
    res = normalise_earnings(curr_earn, he, curr_rev, hr, curr_ast, ind_roa if ind_roa>0 else None)
    rows = [
        ["Current (reported)", f"${res['current_earnings']:,.0f}m", "May be distorted"],
        ["Avg historical",     f"${res.get('average_earnings',0):,.0f}m" if 'average_earnings' in res else "N/A", "Simple average"],
        ["Avg margin × revenue", f"${res.get('margin_normalised',0):,.0f}m" if 'margin_normalised' in res else "N/A", f"Avg margin: {res.get('avg_margin',0):.2%}"],
        ["ROA × assets",       f"${res.get('roa_normalised',0):,.0f}m" if 'roa_normalised' in res else "N/A", f"ROA: {ind_roa:.2%}" if ind_roa>0 else "Not provided"],
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Method","Earnings ($m)","Note"]), use_container_width=True, hide_index=True)
    rec = res['recommended']
    st.markdown(f"""<div class="explain-box">
<strong>Recommended normalised earnings: ${rec:,.0f}m</strong>
{"(average margin method)" if 'margin_normalised' in res else "(average earnings)"}<br>
{"⚠ Current earnings are negative — use normalised figure for any PE or growth calculation." if curr_earn<0 else f"Current vs normalised: {(curr_earn/rec-1)*100:+.1f}% {'above' if curr_earn>rec else 'below'} long-run average."}
</div>""", unsafe_allow_html=True)

st.divider()
st.markdown('<div style="font-size:0.75rem;color:#475569;text-align:center">Damodaran Ch 21, 22, 30, 32 · fcffeva.xls · fcffsimpleginzu.xlsx</div>', unsafe_allow_html=True)
