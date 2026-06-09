"""pages/4_Relative_Valuation.py — Relative Valuation with live data"""
import streamlit as st
import pandas as pd
from data_fetcher import get_company_data, source_badge_html
from relative_valuation import justified_equity_multiples, justified_firm_multiples, score_multiple, INDUSTRY_NAMES_RV, INDUSTRY_MULTIPLES
from cost_of_capital import full_cost_of_capital
from growth_models import estimate_growth

st.set_page_config(page_title="Relative Valuation", page_icon="⚖️", layout="wide")
pg_id = "4"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.explain-box{background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:10px 0 18px 0;font-size:0.88rem;line-height:1.7;color:#cbd5e1;}
.score-pill{display:inline-block;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:500;margin-top:6px;}
.score-green{background:#14532d;color:#86efac;} .score-yellow{background:#713f12;color:#fde68a;} .score-red{background:#7f1d1d;color:#fca5a5;}
.mult-card{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 18px;}
.mult-label{font-size:0.7rem;text-transform:uppercase;letter-spacing:2px;color:#64748b;margin-bottom:4px;}
.mult-value{font-size:1.8rem;font-family:'DM Serif Display',serif;color:#f1f5f9;}
</style>""", unsafe_allow_html=True)

def badge(s,t,c): return f'<span class="score-pill score-{c}">Score {s}/10 — {t[:65]}</span>'
def mult_card(label, value, ind=None, fmt=".1f"):
    ind_html = f'<div style="font-size:0.75rem;color:#475569;margin-top:4px">Industry median: {ind:{fmt}}×</div>' if ind else ""
    return f'<div class="mult-card"><div class="mult-label">{label}</div><div class="mult-value">{value:{fmt}}×</div>{ind_html}</div>'

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚖️ Relative Valuation")
    d = st.session_state.get("company_data")
    if d: st.markdown(source_badge_html(d), unsafe_allow_html=True); st.caption(d.name)
    else: st.warning("No data loaded. Go to the home page and click **Load company data**.")
    st.markdown("---")
    industry = st.selectbox("Industry", ["(None)"] + INDUSTRY_NAMES_RV, key=f"ind_{pg_id}")
    industry = None if industry == "(None)" else industry
    price = st.number_input("Current price ($)", value=float(d.price) if d else 0.0, key=f"pr_{pg_id}")

# ── Header ────────────────────────────────────────────────────────────────────
name = d.name if d else "—"
st.title(f"⚖️ Relative Valuation — {name}")
if not d: st.info("Enter a ticker and fetch data."); st.stop()
st.markdown(source_badge_html(d), unsafe_allow_html=True); st.divider()

# Derive ke and WACC
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

# Derive growth
try:
    g_obj = estimate_growth(ebit=d.ebit, tax_rate=d.tax_rate,
        net_capex=d.capex-d.depreciation, delta_wc=d.delta_wc,
        book_equity=d.book_equity, book_debt=d.book_debt,
        net_income=d.net_income, dividends=0,
        historical_eps=d.historical_eps or None)
    g_rec = g_obj.recommended_growth
except: g_rec = 0.10

# FCFE ratio for payout
d_ratio = d.book_debt/(d.book_equity+d.book_debt) if (d.book_equity+d.book_debt)>0 else 0.2
equity_reinv = (1-d_ratio)*((d.capex-d.depreciation)+d.delta_wc)
payout_auto = max(0.0, min(0.95, 1.0 - equity_reinv/d.net_income)) if d.net_income > 0 else 0.5

tab1, tab2, tab3 = st.tabs(["📊 Equity Multiples", "🏢 Firm Multiples", "📋 Industry Table"])

with tab1:
    st.markdown("## Equity Multiples")
    st.caption("Justified PE, PBV, PS, PEG from 2-stage DDM · Source: eqmult.xls")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**High-growth period**")
        g_high   = st.number_input("Growth rate (high)",    value=round(max(g_rec,0.05),3),  format="%.3f", key="eq_gh")
        payout_h = st.number_input("FCFE as % of NI (high)",value=round(payout_auto,3),      format="%.3f", key="eq_ph",
                                    help="For zero-dividend firms: FCFE/NI ratio (auto-computed from CapEx, Depr, WC, debt ratio)")
        ke_h     = st.number_input("Cost of equity (high)", value=round(ke_val,4),           format="%.4f", key="eq_kh")
        n        = int(st.number_input("High-growth years", value=5,  step=1,                 key="eq_n"))
        net_mg   = st.number_input("Net margin",            value=round(d.net_income/d.revenue,4) if d.revenue>0 else 0.10, format="%.4f", key="eq_nm")
        bv_ps    = st.number_input("Book value / share ($)",value=round(d.book_equity/d.shares,2) if d.shares>0 else 10.0, key="eq_bv")
        eps_fwd  = st.number_input("Forward EPS ($)",       value=round(d.eps*(1+g_rec),2) if d.eps else 1.0, key="eq_eps")
        rev_ps   = st.number_input("Forward revenue / share ($)", value=round(d.revenue/d.shares*(1+g_rec),2) if d.shares>0 else 50.0, key="eq_rev")
    with col2:
        st.markdown("**Stable-growth period**")
        g_stab   = st.number_input("Stable growth rate",    value=0.03, format="%.3f", key="eq_gs")
        payout_s = st.number_input("FCFE % (stable)",       value=min(round(payout_auto*1.2,2),0.80), format="%.3f", key="eq_ps")
        ke_s     = st.number_input("Cost of equity (stable)",value=round(ke_val*0.90,4),    format="%.4f", key="eq_ks")

    st.markdown(f"""<div class="explain-box">
Auto-computed from live data:<br>
ke = {ke_val:.2%} (from Module 01 CAPM)<br>
Recommended growth = {g_rec:.2%} (fundamental + historical blend)<br>
FCFE/NI payout proxy = {payout_auto:.2%} (capital-light software company)
</div>""", unsafe_allow_html=True)

    try:
        r = justified_equity_multiples(
            g_high=g_high, payout_high=payout_h, ke_high=ke_h, n=n,
            g_stable=g_stab, payout_stable=payout_s, ke_stable=ke_s,
            net_margin=net_mg, book_equity_per_share=bv_ps,
            eps_next_year=eps_fwd, revenues_next_year=rev_ps,
        )
        ind = INDUSTRY_MULTIPLES.get(industry,{}) if industry else {}
        cards = f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0">'
        cards += mult_card("PE (Forward)", r.pe_forward, ind.get("pe"), ".1f")
        cards += mult_card("PE (Trailing)", r.pe_trailing, None, ".1f")
        cards += mult_card("PBV", r.pbv, ind.get("pbv"), ".2f")
        cards += mult_card("PS (Forward)", r.ps_forward, ind.get("ps"), ".2f")
        cards += '</div>'
        st.markdown(cards, unsafe_allow_html=True)
        if r.peg: st.metric("PEG Ratio", f"{r.peg:.2f}×")

        s_pe,t_pe,c_pe = score_multiple("pe", r.pe_forward, industry)
        s_pb,t_pb,c_pb = score_multiple("pbv", r.pbv, industry)
        s_pg,t_pg,c_pg = score_multiple("peg", r.peg or 0)
        st.markdown(badge(s_pe,t_pe,c_pe)+"&nbsp;&nbsp;"+badge(s_pb,t_pb,c_pb)+"&nbsp;&nbsp;"+badge(s_pg,t_pg,c_pg), unsafe_allow_html=True)

        st.markdown("### Implied prices")
        rows = [
            (f"From PE ({r.pe_forward:.1f}×)", r.implied_price_pe),
            (f"From PBV ({r.pbv:.2f}×)", r.implied_price_pbv),
            (f"From PS ({r.ps_forward:.2f}×)", r.implied_price_ps),
        ]
        df = pd.DataFrame([{"Method":l,"Implied Price":f"${v:.2f}" if v else "N/A",
            "vs Current":f"{(v/price-1)*100:+.1f}%" if v and price>0 else "—"} for l,v in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)

    except ValueError as e:
        st.error(str(e))

with tab2:
    st.markdown("## Firm Multiples")
    st.caption("Justified EV/EBIT, EV/EBITDA, EV/IC, EV/Sales · Source: firmmult.xls")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**High-growth period**")
        fg_h  = st.number_input("Growth rate (high)",         value=round(max(g_rec,0.05),3),  format="%.3f", key="fm_gh")
        rir_h = st.number_input("Reinvestment rate (high)",   value=round(max((d.capex-d.depreciation+d.delta_wc)/(d.ebit*(1-d.tax_rate)),0.1) if d.ebit>0 else 0.4, 3), format="%.3f", key="fm_rh")
        wacc_h= st.number_input("WACC (high)",                value=round(wacc_val,4),          format="%.4f", key="fm_wh")
        mg_h  = st.number_input("After-tax operating margin", value=round(d.ebit*(1-d.tax_rate)/d.revenue,4) if d.revenue>0 else 0.15, format="%.4f", key="fm_mh")
        fn    = int(st.number_input("High-growth years",      value=5, step=1,                   key="fm_n"))
        tax_r = st.number_input("Tax rate",                   value=float(d.tax_rate),           format="%.3f", key="fm_t")
        nopat_fwd = st.number_input("NOPAT next year ($m)",   value=round(d.ebit*(1-d.tax_rate)*(1+g_rec),0), key="fm_np")
        inv_cap   = st.number_input("Invested Capital ($m)",  value=float(d.book_equity+d.book_debt), key="fm_ic")
        rev_fwd   = st.number_input("Revenue next year ($m)", value=round(d.revenue*(1+g_rec),0), key="fm_rv")
    with col2:
        st.markdown("**Stable-growth period**")
        fg_s  = st.number_input("Stable growth rate",         value=0.03, format="%.3f", key="fm_gs")
        rir_s = st.number_input("Reinvestment rate (stable)", value=round(0.03/0.12,4),  format="%.4f", key="fm_rs")
        wacc_s= st.number_input("WACC (stable)",              value=round(wacc_val*0.95,4), format="%.4f", key="fm_ws")
        mg_s  = st.number_input("Stable after-tax margin",    value=round(d.ebit*(1-d.tax_rate)/d.revenue*0.9,4) if d.revenue>0 else 0.12, format="%.4f", key="fm_ms")
        debt_b= st.number_input("Debt MV ($m)",               value=float(d.book_debt), key="fm_d")
        cash_b= st.number_input("Cash ($m)",                  value=float(d.cash),      key="fm_c")
        sh_b  = st.number_input("Shares (m)",                 value=float(d.shares),    key="fm_sh")

    try:
        r = justified_firm_multiples(
            g_high=fg_h, rir_high=rir_h, wacc_high=wacc_h, margin_high=mg_h, n=fn,
            g_stable=fg_s, rir_stable=rir_s, wacc_stable=wacc_s, margin_stable=mg_s,
            tax_rate=tax_r, nopat_next_year=nopat_fwd, invested_capital=inv_cap, revenues_next_year=rev_fwd,
        )
        ind = INDUSTRY_MULTIPLES.get(industry,{}) if industry else {}
        cards = f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0">'
        cards += mult_card("EV/EBIT (Fwd)",  r.ev_ebit_forward,  None, ".1f")
        cards += mult_card("EV/EBIT (Trl)",  r.ev_ebit_trailing, None, ".1f")
        cards += mult_card("EV/Sales (Fwd)", r.ev_sales_forward, ind.get("ev_sales"), ".1f")
        cards += mult_card("EV/IC",          r.ev_ic,            None, ".1f")
        cards += '</div>'
        st.markdown(cards, unsafe_allow_html=True)

        s_ev,t_ev,c_ev = score_multiple("ev_sales", r.ev_sales_forward, industry)
        st.markdown(badge(s_ev,t_ev,c_ev), unsafe_allow_html=True)

        if any([r.implied_ev_from_ebit, r.implied_ev_from_ic, r.implied_ev_from_sales]):
            st.markdown("### Implied EV → Equity → Price")
            rows = []
            for label, ev in [("EV/EBIT",r.implied_ev_from_ebit),("EV/IC",r.implied_ev_from_ic),("EV/Sales",r.implied_ev_from_sales)]:
                if ev:
                    eq = ev - debt_b + cash_b
                    vps = eq/sh_b if sh_b>0 else 0
                    rows.append({"Method":label,"Implied EV":f"${ev:,.0f}m","Equity":f"${eq:,.0f}m","Price/Share":f"${vps:.2f}","vs Current":f"{(vps/price-1)*100:+.1f}%" if price>0 else "—"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except ValueError as e:
        st.error(str(e))

with tab3:
    st.markdown("## Industry Multiples")
    st.caption("Source: wacccalc.xls US Industry Averages (Jan 2026)")
    rows = [{"Industry":n,"PE":f"{d['pe']:.1f}×","PBV":f"{d['pbv']:.1f}×","PS":f"{d['ps']:.1f}×",
             "EV/EBITDA":f"{d['ev_ebitda']:.1f}×" if d['ev_ebitda'] else "N/A",
             "EV/Sales":f"{d['ev_sales']:.1f}×" if d['ev_sales'] else "N/A"}
            for n,d in INDUSTRY_MULTIPLES.items()]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

st.divider()
st.markdown('<div style="font-size:0.75rem;color:#475569;text-align:center">Damodaran Ch 17–21 · eqmult.xls · firmmult.xls · wacccalc.xls industry data</div>', unsafe_allow_html=True)
