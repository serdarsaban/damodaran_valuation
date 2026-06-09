"""pages/5_Optimal_Capital_Structure.py — Optimal Capital Structure with live data"""
import streamlit as st
import pandas as pd
from data_fetcher import get_company_data, source_badge_html
from optimal_capital_structure import optimal_capital_structure, _TABLE_NAMES
from cost_of_capital import full_cost_of_capital

st.set_page_config(page_title="Optimal Capital Structure", page_icon="🏗️", layout="wide")
pg_id = "5"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box{background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:10px 0 18px 0;font-size:0.88rem;line-height:1.7;color:#cbd5e1;}
.score-pill{display:inline-block;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:500;margin-top:6px;}
.score-green{background:#14532d;color:#86efac;} .score-yellow{background:#713f12;color:#fde68a;} .score-red{background:#7f1d1d;color:#fca5a5;}
</style>""", unsafe_allow_html=True)

def badge(s,t,c): return f'<span class="score-pill score-{c}">Score {s}/10 — {t[:65]}</span>'
def score_position(cur, opt):
    gap = abs(cur-opt)
    dir = "over-levered" if cur>opt else "under-levered"
    if gap < .03: return 9,"Near-optimal — within 3% of optimal","green"
    elif gap < .08: return 7,f"Modestly {dir} — {gap:.0%} from optimal","yellow"
    elif gap < .15: return 5,f"Noticeably {dir} — {gap:.0%} from optimal","yellow"
    else: return 2,f"Significantly {dir} — {gap:.0%} from optimal","red"

with st.sidebar:
    st.markdown("## 🏗️ Capital Structure")
    d = st.session_state.get("company_data")
    if d: st.markdown(source_badge_html(d), unsafe_allow_html=True); st.caption(d.name)
    else: st.warning("No data loaded. Go to the home page and click **Load company data**.")
    st.markdown("---")
    firm_type = st.selectbox("Firm type", [1,2,3], format_func=lambda x:_TABLE_NAMES[x], key=f"ft_{pg_id}")
    apply_bc = st.checkbox("Indirect bankruptcy costs", value=True, key=f"bc_{pg_id}")
    apply_il = st.checkbox("Interest deduction limit (30%)", value=False, key=f"il_{pg_id}")
    steps = st.selectbox("D/C step size", [5,10,20], format_func=lambda x:f"{x}%", index=1, key=f"st_{pg_id}")

name = d.name if d else "—"
st.title(f"🏗️ Optimal Capital Structure — {name}")
if not d: st.info("Enter a ticker and fetch data."); st.stop()
st.markdown(source_badge_html(d), unsafe_allow_html=True); st.divider()

# CoC for actual_kd
coc_key = f"coc_{ticker}_{pg_id}"
if coc_key not in st.session_state:
    try:
        coc = full_cost_of_capital(ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=d.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=firm_type)
        st.session_state[coc_key] = coc
    except: st.session_state[coc_key] = None
coc = st.session_state.get(coc_key)
actual_kd = coc.debt_cost.kd_pretax if coc else None

st.markdown("## Inputs")
st.caption("Pre-filled from live data · all editable")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Income statement**")
    ebitda  = st.number_input("EBITDA ($m)",        value=float(d.ebitda or d.ebit+d.depreciation), key="oc_ebitda")
    depr    = st.number_input("Depreciation ($m)",  value=float(d.depreciation), key="oc_depr")
    ebit    = st.number_input("EBIT ($m)",          value=float(d.ebit),         key="oc_ebit")
    interest= st.number_input("Interest ($m)",      value=float(d.interest_expense), key="oc_int")
    tax     = st.number_input("Tax rate",           value=float(d.tax_rate),     key="oc_tax", format="%.3f")
    fcff_v  = st.number_input("Current FCFF ($m)",  value=float(max(d.fcff,10)), key="oc_fcff")
with col2:
    st.markdown("**Market data**")
    eq_mv   = st.number_input("Market cap ($m)",    value=float(d.equity_market_cap), key="oc_eq")
    debt_mv = st.number_input("Debt MV ($m)",       value=float(d.book_debt),    key="oc_dm")
    beta    = st.number_input("Beta",               value=float(d.beta_levered), key="oc_b",  format="%.3f")
    rf      = st.number_input("Risk-free rate",     value=float(d.rf),           key="oc_rf", format="%.3f")
    erp     = st.number_input("ERP",                value=float(d.erp),          key="oc_erp",format="%.4f")
    kd_lock = st.number_input("Actual kd (lock current row)", value=float(actual_kd) if actual_kd else 0.05, key="oc_kd", format="%.3f")
with col3:
    st.markdown("**Firm & shares**")
    g_stable= st.number_input("Stable growth rate", value=float(d.rf),           key="oc_gs", format="%.3f")
    cash_v  = st.number_input("Cash ($m)",          value=float(d.cash),         key="oc_ca")
    shares  = st.number_input("Shares (m)",         value=float(d.shares),       key="oc_sh")
    price   = st.number_input("Price ($)",          value=float(d.price),        key="oc_pr")

debt_ratios = [r/100 for r in range(0,101,steps)]

st.divider()
st.markdown("## Results")

try:
    result = optimal_capital_structure(
        ebitda=ebitda, depreciation=depr, ebit=ebit,
        interest_expense=interest, tax_rate=tax,
        equity_mv=eq_mv, debt_mv=debt_mv,
        beta_levered=beta, rf=rf, erp=erp,
        fcff=fcff_v, g_stable=g_stable,
        firm_type=firm_type,
        apply_bankruptcy_costs=apply_bc,
        apply_interest_limit=apply_il,
        shares_outstanding=shares, current_price=price,
        cash=cash_v, lock_current_kd=kd_lock if kd_lock>0 else None,
        company=d.name, debt_ratios=debt_ratios,
    )

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Current D/(D+E)",  f"{result.current_debt_ratio:.1%}")
    c2.metric("Optimal D/(D+E)",  f"{result.optimal_debt_ratio:.1%}", delta=f"{(result.optimal_debt_ratio-result.current_debt_ratio)*100:+.1f}pp")
    c3.metric("Current WACC",     f"{result.current_wacc:.2%}")
    c4.metric("Optimal WACC",     f"{result.optimal_wacc:.2%}", delta=f"{(result.optimal_wacc-result.current_wacc)*100:+.2f}pp")
    c1b,c2b,c3b,c4b = st.columns(4)
    c1b.metric("Current Firm Value", f"${result.current_firm_value:,.0f}m")
    c2b.metric("Optimal Firm Value", f"${result.optimal_firm_value:,.0f}m", delta=f"+${result.value_gain:,.0f}m")
    c3b.metric("Current Price", f"${price:.2f}")
    c4b.metric("Optimal Price/Share", f"${result.optimal_price_per_share:.2f}" if result.optimal_price_per_share > 0 else "N/A")

    s,t,c = score_position(result.current_debt_ratio, result.optimal_debt_ratio)
    st.markdown(badge(s,t,c), unsafe_allow_html=True)

    direction = "over-levered" if result.current_debt_ratio > result.optimal_debt_ratio else "under-levered"
    action = "reduce debt" if direction == "over-levered" else "issue more debt and repurchase shares"
    st.markdown(f"""<div class="explain-box">
<strong>Interpretation:</strong> {d.name} is currently <strong>{direction}</strong>.
Current D/(D+E) = {result.current_debt_ratio:.1%} vs optimal {result.optimal_debt_ratio:.1%}.
Recommended action: <strong>{action}</strong>.
{"<br>Repurchase: issue $" + f"{result.new_debt_issued:,.0f}m debt, repurchase {result.shares_repurchased:,.0f}m shares. Remaining shares → ${result.optimal_price_per_share:.2f}/share." if result.new_debt_issued > 0 and price > 0 else ""}
</div>""", unsafe_allow_html=True)

    st.markdown("### Full debt ratio sweep")
    rows = []
    for r in result.sweep:
        is_opt = abs(r.debt_ratio-result.optimal_debt_ratio)<0.001
        is_cur = abs(r.debt_ratio-result.current_debt_ratio)<0.001
        tag = " ◀ OPTIMAL" if is_opt else (" ◀ current" if is_cur else "")
        rows.append({"D/(D+E)":f"{r.debt_ratio:.0%}{tag}","Rating":r.rating,"kd":f"{r.kd_pretax:.2%}","ke":f"{r.ke:.2%}","WACC":f"{r.wacc:.3%}","Firm Value":f"${r.firm_value:,.0f}m" if r.firm_value<1e12 else "∞"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    col_w, col_v = st.columns(2)
    chart_df = pd.DataFrame([{"D/C (%)":int(r.debt_ratio*100),"WACC (%)":round(r.wacc*100,3),"Firm Value ($m)":round(r.firm_value,0)} for r in result.sweep if r.firm_value<1e12])
    col_w.markdown("**WACC**"); col_w.line_chart(chart_df.set_index("D/C (%)")["WACC (%)"])
    col_v.markdown("**Firm Value**"); col_v.line_chart(chart_df.set_index("D/C (%)")["Firm Value ($m)"])

except Exception as e:
    st.error(f"Model error: {e}")

st.divider()
st.markdown('<div style="font-size:0.75rem;color:#475569;text-align:center">Damodaran Ch 15 · capstru.xlsx (Disney 2023 reference) · Spreads Jan 2026</div>', unsafe_allow_html=True)
