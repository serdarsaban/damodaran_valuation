"""
pages/1_Cost_of_Capital.py
Damodaran Ch 7–8 — Cost of Capital with live data
"""

import streamlit as st
import math
from data_fetcher import get_company_data, source_badge_html, CompanyData
from cost_of_capital import (
    full_cost_of_capital, capitalise_operating_leases,
    FullCostOfCapitalResult,
)

st.set_page_config(page_title="Cost of Capital", page_icon="📐", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.metric-card { background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:20px 24px; margin-bottom:12px; }
.metric-value { font-size:2.2rem; font-weight:300; letter-spacing:-1px; font-family:'DM Serif Display',serif; }
.metric-label { font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; color:#64748b; margin-bottom:4px; }
.score-pill { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.8rem; font-weight:500; margin-top:8px; }
.score-green  { background:#14532d; color:#86efac; }
.score-yellow { background:#713f12; color:#fde68a; }
.score-red    { background:#7f1d1d; color:#fca5a5; }
.explain-box { background:#1e293b; border-left:3px solid #3b82f6; border-radius:0 8px 8px 0; padding:14px 18px; margin:10px 0 18px 0; font-size:0.9rem; line-height:1.6; color:#cbd5e1; }
.source-tag { font-size:0.72rem; color:#475569; margin-top:8px; }
.section-divider { border:none; border-top:1px solid #1e293b; margin:28px 0; }
</style>
""", unsafe_allow_html=True)

EXPLANATIONS = {
    "wacc": {"title":"Weighted Average Cost of Capital (WACC)","what":"WACC is the minimum return a firm must earn on its existing asset base to keep its shareholders and creditors satisfied. It blends the cost of equity and the after-tax cost of debt, weighted by how much of each the firm actually uses.","formula":"WACC = ke × (E/V) + kd × (1−t) × (D/V)","why":"This is the discount rate used to value the firm's free cash flows (FCFF model). A lower WACC means less of every dollar of cash flow is eaten up by the cost of financing — which directly raises firm value.","source":"Damodaran, Ch 8, p.195"},
    "ke":   {"title":"Cost of Equity (ke)","what":"The return shareholders require to hold the stock. Computed via CAPM.","formula":"ke = rf + β × ERP","why":"Equity is the most expensive form of capital because shareholders bear residual risk. The higher the beta and ERP, the more investors demand.","source":"Damodaran, Ch 7, p.160"},
    "kd":   {"title":"Pre-tax Cost of Debt (kd)","what":"The yield the firm would have to offer on new debt today. Estimated from the synthetic credit rating derived from interest coverage.","formula":"kd = rf + default spread","why":"Debt is cheaper than equity because interest is tax-deductible and creditors have priority. But as debt increases, the rating falls and the spread widens.","source":"Damodaran, Ch 8, p.182"},
    "icr":  {"title":"Interest Coverage Ratio (ICR)","what":"How many times EBIT can cover the annual interest bill. This is the single number used to assign a synthetic credit rating.","formula":"ICR = EBIT / Interest Expense","why":"A higher ICR means more cushion for creditors, which means a better rating and a lower default spread.","source":"Damodaran, Ch 8, p.183"},
    "beta": {"title":"Beta (β)","what":"Beta measures how much a stock moves relative to the overall market.","formula":"β_relevered = β_unlevered × [1 + (1−t) × D/E]","why":"Damodaran always unleveres the beta first then re-levers it for the firm's actual capital structure.","source":"Damodaran, Ch 8, p.170"},
    "debt_mv": {"title":"Market Value of Debt","what":"Book value of debt converted to present value by treating all debt as a single coupon bond.","formula":"MV(Debt) = Interest × annuity_factor(kd, n) + Book_Debt / (1+kd)^n","why":"WACC must use market-value weights, not book-value weights.","source":"Damodaran, Ch 8, p.194"},
}

def explain(key):
    e = EXPLANATIONS.get(key, {})
    if not e: return
    with st.expander(f"📖 What is {e['title']}?", expanded=False):
        st.markdown(f'<div class="explain-box"><strong>What it is:</strong> {e["what"]}<br><br><strong>Formula:</strong> <code>{e["formula"]}</code><br><br><strong>Why it matters:</strong> {e["why"]}<br><br><div class="source-tag">Source: {e["source"]}</div></div>', unsafe_allow_html=True)

def score_wacc(w):
    p=w*100
    if p<5: return 9,"Very low — well below market norms","green"
    elif p<7: return 8,"Low — below typical 7–9% range","green"
    elif p<9: return 7,"Average — within 7–9% for most US firms","green"
    elif p<11: return 5,"Above average — higher than market median","yellow"
    elif p<14: return 3,"High — firm faces elevated financing costs","yellow"
    else: return 1,"Very high — typical only for distressed firms","red"

def score_icr(icr):
    if icr==math.inf or icr>12.5: return 10,"Exceptional — Aaa/AAA equivalent","green"
    elif icr>8.5: return 9,"Excellent — Aa2/AA equivalent","green"
    elif icr>5.5: return 8,"Strong — A-range rating","green"
    elif icr>3.0: return 6,"Adequate — BBB to A− range","yellow"
    elif icr>2.0: return 4,"Weak — BB range","yellow"
    elif icr>1.25: return 2,"Stressed — B range","red"
    else: return 1,"Distressed — ICR barely covers interest","red"

def score_beta(b):
    if b<0.5: return 9,"Defensive — half market rate","green"
    elif b<0.8: return 8,"Low volatility","green"
    elif b<1.1: return 7,"Market-rate risk","green"
    elif b<1.4: return 5,"Moderately elevated","yellow"
    elif b<1.8: return 3,"High — 40–80% more volatile","yellow"
    else: return 1,"Very high beta","red"

def score_ke(ke):
    p=ke*100
    if p<7: return 9,"Very low cost of equity","green"
    elif p<9: return 8,"Below-average cost of equity","green"
    elif p<11: return 7,"Average — 9–11% range","green"
    elif p<13: return 5,"Above average","yellow"
    elif p<16: return 3,"High cost of equity","yellow"
    else: return 1,"Very high — distressed or EM equity","red"

def badge(s, interp, colour):
    short = interp[:50]+"…" if len(interp)>50 else interp
    return f'<span class="score-pill score-{colour}">Score {s}/10 — {short}</span>'

def metric_card(label, value, score, interp, colour, delta=""):
    b = badge(score, interp, colour)
    dh = f'<div style="font-size:0.78rem;color:#64748b;margin-top:4px">{delta}</div>' if delta else ""
    st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div>{dh}{b}</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — reads from shared session_state set on home page
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📐 Cost of Capital")
    d = st.session_state.get("company_data")
    if d:
        from data_fetcher import source_badge_html
        st.markdown(source_badge_html(d), unsafe_allow_html=True)
        st.caption(f"{d.name} ({d.ticker})")
    else:
        st.warning("No data loaded. Go to the home page and click **Load company data**.")
    st.markdown("---")
    st.markdown("### Override any input")
    override = st.checkbox("Manual override", value=False)

# ─────────────────────────────────────────────────────────────────────────────
# Optional manual override
# ─────────────────────────────────────────────────────────────────────────────
if override:
    with st.sidebar:
        ebit             = st.number_input("EBIT ($m)",              value=float(d.ebit))
        interest_expense = st.number_input("Interest Expense ($m)",  value=float(d.interest_expense))
        book_debt        = st.number_input("Book Debt ($m)",         value=float(d.book_debt))
        avg_maturity     = st.number_input("Avg Maturity (yrs)",     value=float(d.avg_debt_maturity))
        equity_mv        = st.number_input("Market Cap ($m)",        value=float(d.equity_market_cap))
        beta_levered     = st.number_input("Levered Beta",           value=float(d.beta_levered))
        rf               = st.number_input("Risk-free Rate",         value=float(d.rf),  format="%.3f")
        erp              = st.number_input("ERP",                    value=float(d.erp), format="%.3f")
        tax_rate         = st.number_input("Tax Rate",               value=float(d.tax_rate), format="%.2f")
        country_spread   = st.number_input("Country Spread",         value=float(d.country_spread), format="%.3f")
        firm_type        = st.selectbox("Firm Type", [1,2,3],
                               format_func=lambda x:{1:"Large",2:"Small/risky",3:"Financial"}[x],
                               index=d.firm_type-1)
else:
    ebit=d.ebit; interest_expense=d.interest_expense; book_debt=d.book_debt
    avg_maturity=d.avg_debt_maturity; equity_mv=d.equity_market_cap
    beta_levered=d.beta_levered; rf=d.rf; erp=d.erp; tax_rate=d.tax_rate
    country_spread=d.country_spread; firm_type=d.firm_type

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
dc=result.debt_cost; br=result.beta_result; wr=result.wacc_result

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"# {d.name}")
st.markdown(f"**Cost of Capital Analysis** · Damodaran *Investment Valuation* methodology")
st.markdown(source_badge_html(d), unsafe_allow_html=True)
if d.fetch_errors:
    with st.expander("⚠ Data warnings"):
        for err in d.fetch_errors:
            st.caption(err)
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Summary")
col1, col2, col3 = st.columns(3)
with col1:
    s,i,c=score_wacc(wr.wacc)
    metric_card("WACC", f"{wr.wacc:.2%}", s, i, c,
                delta=f"Equity {wr.weight_equity:.0%} / Debt {wr.weight_debt:.0%}")
    explain("wacc")
with col2:
    s,i,c=score_ke(br.ke)
    metric_card("Cost of Equity", f"{br.ke:.2%}", s, i, c,
                delta=f"β {br.beta_relevered:.2f} × ERP {br.erp:.1%}")
    explain("ke")
with col3:
    s,i,c=score_icr(dc.icr)
    icr_str="∞" if dc.icr==math.inf else f"{dc.icr:.1f}x"
    metric_card("Interest Coverage", icr_str, s, i, c,
                delta=f"Rating: {dc.rating} · Spread: {dc.company_spread:.2%}")
    explain("icr")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# Steps 1–4
st.markdown("## Step-by-step breakdown")
st.markdown("### Step 1 — Synthetic Credit Rating")
c1,c2,c3,c4=st.columns(4)
c1.metric("EBIT", f"${ebit:,.0f}m")
c2.metric("Interest Expense", f"${interest_expense:,.0f}m")
c3.metric("ICR", "∞" if dc.icr==math.inf else f"{dc.icr:.2f}×")
c4.metric("Rating → Spread", f"{dc.rating} → {dc.company_spread:.2%}")
explain("icr"); explain("kd")
s,i,c=score_icr(dc.icr)
st.markdown(badge(s,i,c), unsafe_allow_html=True)
st.markdown(f'<div class="explain-box"><strong>Interpretation:</strong> {i}<br><br>Pre-tax kd = {dc.rf:.2%} + {dc.company_spread:.2%} = <strong>{dc.kd_pretax:.2%}</strong><br>After-tax kd = {dc.kd_pretax:.2%} × (1 − {dc.tax_rate:.0%}) = <strong>{dc.kd_aftertax:.2%}</strong></div>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown("### Step 2 — Beta & Cost of Equity")
c1,c2,c3,c4=st.columns(4)
c1.metric("Input Beta", f"{br.beta_levered_input:.3f}")
c2.metric("Unlevered Beta", f"{br.beta_unlevered:.3f}")
c3.metric("Re-levered Beta", f"{br.beta_relevered:.3f}")
c4.metric("Cost of Equity", f"{br.ke:.2%}")
explain("beta"); explain("ke")
sb,ib,cb=score_beta(br.beta_relevered); sk,ik,ck=score_ke(br.ke)
st.markdown(badge(sb,ib,cb)+"&nbsp;&nbsp;"+badge(sk,ik,ck), unsafe_allow_html=True)
st.markdown(f'<div class="explain-box"><strong>CAPM:</strong> ke = {br.rf:.2%} + {br.beta_relevered:.3f} × {br.erp:.2%} = <strong>{br.ke:.2%}</strong><br><strong>Unlevering:</strong> β_u = {br.beta_levered_input:.3f} / [1 + (1−{br.tax_rate:.0%}) × {br.current_de:.2f}] = {br.beta_unlevered:.3f}</div>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown("### Step 3 — Market Value of Debt")
c1,c2,c3=st.columns(3)
c1.metric("Book Value of Debt", f"${book_debt:,.0f}m")
c2.metric("Market Value of Debt", f"${result.market_debt:,.0f}m")
pct_diff=(result.market_debt-book_debt)/book_debt*100 if book_debt else 0
c3.metric("Difference", f"{pct_diff:+.1f}%")
explain("debt_mv")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown("### Step 4 — WACC Assembly")
c1,c2,c3=st.columns(3)
c1.metric("Equity Weight", f"{wr.weight_equity:.1%}", delta=f"${wr.equity_mv:,.0f}m")
c2.metric("Debt Weight", f"{wr.weight_debt:.1%}", delta=f"${wr.debt_mv:,.0f}m")
c3.metric("Total Capital (MV)", f"${wr.total_capital:,.0f}m")
explain("wacc")
sw,iw,cw=score_wacc(wr.wacc)
st.markdown(badge(sw,iw,cw), unsafe_allow_html=True)
eq_c=br.ke*wr.weight_equity; dt_c=dc.kd_aftertax*wr.weight_debt
st.markdown(f'<div class="explain-box"><strong>WACC build-up:</strong><br>Equity: {br.ke:.2%} × {wr.weight_equity:.1%} = {eq_c:.2%}<br>Debt: {dc.kd_aftertax:.2%} × {wr.weight_debt:.1%} = {dt_c:.2%}<br><strong>WACC = {wr.wacc:.2%}</strong></div>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# Scorecard
st.markdown("## Overall Scorecard")
scores={"WACC":score_wacc(wr.wacc),"Cost of Equity":score_ke(br.ke),"Interest Coverage":score_icr(dc.icr),"Beta":score_beta(br.beta_relevered)}
composite=sum(s for s,_,_ in scores.values())/len(scores)
c1,c2=st.columns([1,2])
with c1:
    st.markdown(f'<div class="metric-card" style="text-align:center"><div class="metric-label">Composite Score</div><div class="metric-value" style="font-size:3.5rem">{composite:.1f}</div><div style="color:#64748b;font-size:0.85rem">out of 10</div></div>', unsafe_allow_html=True)
with c2:
    for name,(s,interp,colour) in scores.items():
        bar=s*10; bc={"green":"#22c55e","yellow":"#f59e0b","red":"#ef4444"}[colour]
        st.markdown(f'<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:0.85rem;color:#cbd5e1">{name}</span><span style="font-size:0.85rem;color:{bc};font-weight:500">{s}/10</span></div><div style="background:#1e293b;border-radius:4px;height:8px"><div style="background:{bc};width:{bar}%;height:8px;border-radius:4px"></div></div><div style="font-size:0.75rem;color:#64748b;margin-top:3px">{interp[:80]}{"…" if len(interp)>80 else ""}</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown(f'<div style="font-size:0.75rem;color:#475569;text-align:center;padding:20px 0">Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed. Ch 7–8 · Spreads: Jan-2026 · rf: {"FRED" if d.source!="placeholder" else "placeholder"} · Data: {d.source}</div>', unsafe_allow_html=True)
