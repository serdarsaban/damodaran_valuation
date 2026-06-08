"""pages/4_Relative_Valuation.py — Relative Valuation (Ch 17–21)"""
import streamlit as st
import pandas as pd
from relative_valuation import (
    justified_equity_multiples, justified_firm_multiples,
    score_multiple, implied_price_from_peer_multiple,
    INDUSTRY_NAMES_RV, INDUSTRY_MULTIPLES,
)

st.set_page_config(page_title="Relative Valuation", page_icon="⚖️", layout="wide")

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
.multiple-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0; }
.mult-card { background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px 18px; }
.mult-label { font-size:0.7rem; text-transform:uppercase; letter-spacing:2px; color:#64748b; margin-bottom:4px; }
.mult-value { font-size:1.8rem; font-family:'DM Serif Display',serif; color:#f1f5f9; }
.mult-ind   { font-size:0.75rem; color:#475569; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

EXPLANATIONS = {
    "pe": {
        "title": "Price / Earnings (PE)",
        "what": "How much investors pay for each dollar of earnings. The most widely used equity multiple.",
        "formula": "PE = Price / EPS  =  Payout × (1+g) / (ke − g)  [stable growth]",
        "why": ("PE is driven by three fundamentals: payout ratio, growth, and cost of equity. "
                "A high PE is only justified if growth is high or risk is low. "
                "Damodaran always asks: what growth rate is implied by the current PE?"),
        "source": "Damodaran, Ch 17, p.431",
    },
    "peg": {
        "title": "PEG Ratio",
        "what": "PE divided by the expected growth rate (expressed as a percentage). Popularised by Peter Lynch.",
        "formula": "PEG = PE / (g × 100)",
        "why": ("A PEG < 1 implies you are paying less for earnings growth than the growth rate — "
                "often seen as a signal of undervaluation. But PEG ignores risk: two firms with the "
                "same PEG can have very different risk profiles."),
        "source": "Damodaran, Ch 18, p.462",
    },
    "pbv": {
        "title": "Price / Book Value (PBV)",
        "what": "Market price vs accounting book value of equity per share.",
        "formula": "PBV = (ROE − g) / (ke − g)  [stable growth]",
        "why": ("PBV < 1 is not automatically cheap — it may reflect low ROE. "
                "The key relationship: PBV is justified by the excess of ROE over ke. "
                "A firm with ROE = ke should trade at book value regardless of growth."),
        "source": "Damodaran, Ch 19, p.487",
    },
    "ev_ebitda": {
        "title": "EV / EBITDA",
        "what": ("Enterprise value divided by earnings before interest, tax, depreciation and amortisation. "
                 "The most commonly used firm-level multiple in M&A and LBOs."),
        "formula": "EV/EBITDA = (1−t) × (1−RIR) / (WACC − g)  × (EBIT/EBITDA)",
        "why": ("Unlike PE, EV/EBITDA is capital-structure neutral and not distorted by "
                "depreciation policy. But it can be misleading for capital-intensive firms "
                "where depreciation is economically real (it needs to be replaced)."),
        "source": "Damodaran, Ch 20, p.521",
    },
    "ev_sales": {
        "title": "EV / Sales",
        "what": "Enterprise value divided by revenues. Useful for loss-making firms where earnings multiples fail.",
        "formula": "EV/Sales = EBIT_margin × (1−t) × (1−RIR) / (WACC − g)",
        "why": ("EV/Sales is only meaningful relative to profitability. A 2× EV/Sales is cheap "
                "for a 20% margin business but expensive for a 2% margin one. "
                "Always pair with the operating margin."),
        "source": "Damodaran, Ch 20, p.527",
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

def mult_card(label, value, ind_value=None, fmt=".1f"):
    ind_html = f'<div class="mult-ind">Industry median: {ind_value:{fmt}}×</div>' if ind_value else ""
    return f"""<div class="mult-card">
  <div class="mult-label">{label}</div>
  <div class="mult-value">{value:{fmt}}×</div>
  {ind_html}
</div>"""

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Settings")
    st.markdown('<span class="placeholder-badge">⚠ Placeholder data</span>', unsafe_allow_html=True)
    industry = st.selectbox("Industry (for benchmarks)", ["(None)"] + INDUSTRY_NAMES_RV)
    industry = None if industry == "(None)" else industry
    current_price = st.number_input("Current stock price ($)", value=0.0, min_value=0.0)
    st.markdown("---")
    st.markdown("""<div style='font-size:0.75rem;color:#475569;line-height:1.7'>
<strong>Data roadmap</strong><br>
🟡 Placeholder (now)<br>
🔵 yfinance — price, EPS, BV, revenue<br>
🔵 Module 01 → ke, WACC<br>
🔵 Module 03 → growth rate
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ Relative Valuation")
st.markdown("**Chapters 17–21** · PE · PEG · PBV · PS · EV/EBITDA · EV/Sales")
st.warning("⚠ Placeholder inputs. Live connection to yfinance coming soon.", icon="⚠️")
st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Equity Multiples", "🏢 Firm Multiples", "📋 Industry Table"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Equity multiples
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## Equity Multiples")
    st.markdown("Justified PE, PBV, PS and PEG from a 2-stage DDM. Source: `eqmult.xls`")
    explain("pe"); explain("pbv"); explain("peg")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**High-growth period**")
        g_high      = st.number_input("Growth rate (high)",         value=0.10,  format="%.3f", key="eq_gh")
        payout_high = st.number_input("Payout / FCFE% of NI (high)",value=0.371, format="%.3f", key="eq_ph")
        ke_high     = st.number_input("Cost of equity (high)",      value=0.085, format="%.3f", key="eq_kh")
        n           = int(st.number_input("High-growth years",      value=10, step=1,            key="eq_n"))
        st.markdown("**Firm-specific inputs**")
        net_margin  = st.number_input("Net profit margin",          value=0.025, format="%.3f", key="eq_nm")
        bv_per_share = st.number_input("Book value / share",        value=6.29,                 key="eq_bv")
        eps_fwd     = st.number_input("Forward EPS",                value=1.0,                  key="eq_eps")
        rev_fwd     = st.number_input("Forward revenue / share",    value=40.0,                 key="eq_rev")

    with col2:
        st.markdown("**Stable-growth period**")
        g_stable      = st.number_input("Stable growth rate",         value=0.03,  format="%.3f", key="eq_gs")
        payout_stable = st.number_input("Payout / FCFE% of NI (stable)",value=0.70,format="%.3f", key="eq_ps")
        ke_stable     = st.number_input("Cost of equity (stable)",    value=0.08,  format="%.3f", key="eq_ks")

    if st.button("Calculate Equity Multiples →", type="primary", key="btn_eq"):
        try:
            r = justified_equity_multiples(
                g_high=g_high, payout_high=payout_high, ke_high=ke_high, n=n,
                g_stable=g_stable, payout_stable=payout_stable, ke_stable=ke_stable,
                net_margin=net_margin, book_equity_per_share=bv_per_share,
                eps_next_year=eps_fwd, revenues_next_year=rev_fwd,
            )
            st.divider()
            st.markdown("### Justified multiples")

            ind = INDUSTRY_MULTIPLES.get(industry, {}) if industry else {}

            # Cards grid
            cards_html = '<div class="multiple-grid">'
            cards_html += mult_card("PE (Forward)",  r.pe_forward,  ind.get("pe"),  ".1f")
            cards_html += mult_card("PE (Trailing)", r.pe_trailing, None,           ".1f")
            cards_html += mult_card("PBV",           r.pbv,         ind.get("pbv"), ".2f")
            cards_html += mult_card("PS (Forward)",  r.ps_forward,  ind.get("ps"),  ".2f")
            cards_html += '</div>'
            st.markdown(cards_html, unsafe_allow_html=True)

            # PEG
            if r.peg:
                st.metric("PEG Ratio", f"{r.peg:.2f}×", help="PE / (g × 100)")

            # Scores
            s_pe,  t_pe,  c_pe  = score_multiple("pe",  r.pe_forward,  industry)
            s_pbv, t_pbv, c_pbv = score_multiple("pbv", r.pbv,         industry)
            s_peg, t_peg, c_peg = score_multiple("peg", r.peg or 0)
            st.markdown(badge(s_pe,  t_pe,  c_pe)  + "&nbsp;&nbsp;" +
                        badge(s_pbv, t_pbv, c_pbv) + "&nbsp;&nbsp;" +
                        badge(s_peg, t_peg, c_peg), unsafe_allow_html=True)

            # Implied prices
            st.markdown("### Implied prices")
            pc = [(f"From PE ({r.pe_forward:.1f}×)", r.implied_price_pe),
                  (f"From PBV ({r.pbv:.2f}×)", r.implied_price_pbv),
                  (f"From PS ({r.ps_forward:.2f}×)", r.implied_price_ps)]
            df_prices = pd.DataFrame([
                {"Method": label,
                 "Implied Price": f"${val:.2f}" if val else "N/A",
                 "vs Current": f"{(val/current_price-1)*100:+.1f}%" if val and current_price > 0 else "—"}
                for label, val in pc
            ])
            st.dataframe(df_prices, use_container_width=True, hide_index=True)

            # Detail
            st.markdown(f"""<div class="explain-box">
<strong>Key relationships:</strong><br>
ROE (high growth) = g / (1−payout) = {r.roe_high:.2%} — implied return on equity during growth period<br>
ROE (stable) = {r.roe_stable:.2%}<br><br>
<strong>PBV interpretation:</strong> A PBV of {r.pbv:.2f}× implies the market expects ROE of {r.roe_high:.2%},
which {"exceeds" if r.roe_high > ke_high else "is below"} the cost of equity of {ke_high:.2%}.
{"This excess return justifies the premium to book." if r.roe_high > ke_high
 else "This shortfall explains the discount to book."}<br><br>
<strong>PEG interpretation:</strong> {"PEG of " + f"{r.peg:.2f}" + ("× — below 1: paying less than the growth rate (undervalued signal)." if r.peg < 1 else "× — above 1: paying more than growth rate.") if r.peg else "PEG not available."}
</div>""", unsafe_allow_html=True)

        except ValueError as e:
            st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Firm multiples
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Firm Multiples")
    st.markdown("Justified EV/EBIT, EV/EBITDA, EV/IC, EV/Sales from a 2-stage FCFF model. Source: `firmmult.xls`")
    explain("ev_ebitda"); explain("ev_sales")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**High-growth period**")
        fg_high   = st.number_input("Growth rate (high)",           value=0.096, format="%.3f", key="fm_gh")
        rir_high  = st.number_input("Reinvestment rate (high)",     value=0.60,  format="%.2f", key="fm_rh")
        wacc_high = st.number_input("WACC (high)",                  value=0.0803,format="%.4f", key="fm_wh")
        mg_high   = st.number_input("After-tax operating margin",   value=0.1443,format="%.4f", key="fm_mh")
        fn        = int(st.number_input("High-growth years",        value=10, step=1,            key="fm_n"))
        tax_rate  = st.number_input("Tax rate",                     value=0.40,  format="%.2f", key="fm_t")
        st.markdown("**Scaling inputs**")
        nopat_fwd = st.number_input("NOPAT next year ($m)",         value=100.0,                key="fm_np")
        inv_cap   = st.number_input("Invested Capital ($m)",        value=625.0,                key="fm_ic")
        rev_fwd2  = st.number_input("Revenue next year ($m)",       value=693.0,                key="fm_rv")

    with col2:
        st.markdown("**Stable-growth period**")
        fg_stable   = st.number_input("Stable growth rate",         value=0.035, format="%.3f", key="fm_gs")
        rir_stable  = st.number_input("Reinvestment rate (stable)", value=0.2917,format="%.4f", key="fm_rs")
        wacc_stable = st.number_input("WACC (stable)",              value=0.0774,format="%.4f", key="fm_ws")
        mg_stable   = st.number_input("Stable after-tax margin",    value=0.05,  format="%.3f", key="fm_ms")
        st.markdown("**Equity bridge**")
        debt_mv2 = st.number_input("Debt MV ($m)",                  value=0.0,                  key="fm_d")
        cash2    = st.number_input("Cash ($m)",                     value=0.0,                  key="fm_c")
        shares2  = st.number_input("Shares outstanding (m)",        value=100.0,                key="fm_sh")

    if st.button("Calculate Firm Multiples →", type="primary", key="btn_fm"):
        try:
            r = justified_firm_multiples(
                g_high=fg_high, rir_high=rir_high, wacc_high=wacc_high,
                margin_high=mg_high, n=fn,
                g_stable=fg_stable, rir_stable=rir_stable, wacc_stable=wacc_stable,
                margin_stable=mg_stable, tax_rate=tax_rate,
                nopat_next_year=nopat_fwd, invested_capital=inv_cap,
                revenues_next_year=rev_fwd2,
            )
            st.divider()
            st.markdown("### Justified multiples")

            ind = INDUSTRY_MULTIPLES.get(industry, {}) if industry else {}

            cards_html = '<div class="multiple-grid">'
            cards_html += mult_card("EV/EBIT (Fwd)",      r.ev_ebit_forward,    None,                   ".1f")
            cards_html += mult_card("EV/EBIT (Trl)",      r.ev_ebit_trailing,   None,                   ".1f")
            cards_html += mult_card("EV/Sales (Fwd)",     r.ev_sales_forward,   ind.get("ev_sales"),    ".1f")
            cards_html += mult_card("EV/IC",              r.ev_ic,              None,                   ".1f")
            cards_html += '</div>'
            st.markdown(cards_html, unsafe_allow_html=True)

            # EV/EBITDA note
            st.caption("Note: EV/EBITDA not directly output — use EV/EBIT × (EBIT/EBITDA) where EBIT/EBITDA = 1 − D&A/EBITDA")

            # Scores
            s_ev, t_ev, c_ev = score_multiple("ev_sales", r.ev_sales_forward, industry)
            st.markdown(badge(s_ev, t_ev, c_ev), unsafe_allow_html=True)

            # Implied EVs
            st.markdown("### Implied Enterprise Value")
            evs = []
            if r.implied_ev_from_ebit:
                ev_equity = r.implied_ev_from_ebit - debt_mv2 + cash2
                evs.append(("From EV/EBIT", r.implied_ev_from_ebit,
                             ev_equity, ev_equity/shares2 if shares2 > 0 else 0))
            if r.implied_ev_from_ic:
                ev_equity = r.implied_ev_from_ic - debt_mv2 + cash2
                evs.append(("From EV/IC", r.implied_ev_from_ic,
                             ev_equity, ev_equity/shares2 if shares2 > 0 else 0))
            if r.implied_ev_from_sales:
                ev_equity = r.implied_ev_from_sales - debt_mv2 + cash2
                evs.append(("From EV/Sales", r.implied_ev_from_sales,
                             ev_equity, ev_equity/shares2 if shares2 > 0 else 0))
            if evs:
                df_ev = pd.DataFrame([{
                    "Method": label,
                    "Implied EV ($m)": f"${ev:,.0f}",
                    "Implied Equity ($m)": f"${eq:,.0f}",
                    "Implied Price": f"${vps:.2f}",
                    "vs Current": f"{(vps/current_price-1)*100:+.1f}%" if current_price > 0 else "—",
                } for label, ev, eq, vps in evs])
                st.dataframe(df_ev, use_container_width=True, hide_index=True)

            st.markdown(f"""<div class="explain-box">
<strong>ROIC (high growth):</strong> {r.roic_high:.2%}  |  <strong>ROIC (stable):</strong> {r.roic_stable:.2%}<br>
<strong>After-tax margin (high):</strong> {mg_high:.2%}  |  <strong>(stable):</strong> {mg_stable:.2%}<br><br>
<strong>EV/IC interpretation:</strong> EV/IC of {r.ev_ic:.2f}× implies the market expects
ROIC of {r.roic_high:.2%} vs WACC of {wacc_high:.2%}.
{"Positive spread — value creation justifies the premium." if r.roic_high > wacc_high
 else "Negative spread — EV/IC should be below 1 for a value-destroying firm."}
</div>""", unsafe_allow_html=True)

        except ValueError as e:
            st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Industry comparison table
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Industry Multiples")
    st.caption("Source: wacccalc.xls — US Industry Averages (Jan 2026)")
    st.markdown("Compare your firm's multiples against the industry median.")

    col1, col2, col3 = st.columns(3)
    firm_pe    = col1.number_input("Your PE (forward)",    value=0.0, key="cmp_pe")
    firm_pbv   = col1.number_input("Your PBV",            value=0.0, key="cmp_pbv")
    firm_ps    = col2.number_input("Your PS (trailing)",   value=0.0, key="cmp_ps")
    firm_ev_eb = col2.number_input("Your EV/EBITDA",       value=0.0, key="cmp_eveb")
    firm_ev_s  = col3.number_input("Your EV/Sales",        value=0.0, key="cmp_evs")

    # Full table
    rows = []
    for name in INDUSTRY_NAMES_RV:
        d = INDUSTRY_MULTIPLES[name]
        row = {
            "Industry":    name,
            "PE (fwd)":    f"{d['pe']:.1f}×",
            "PBV":         f"{d['pbv']:.1f}×",
            "PS":          f"{d['ps']:.1f}×",
            "EV/EBITDA":   f"{d['ev_ebitda']:.1f}×" if d['ev_ebitda'] else "N/A",
            "EV/Sales":    f"{d['ev_sales']:.1f}×"  if d['ev_sales']  else "N/A",
        }
        # Highlight if firm inputs provided
        if industry and name == industry:
            row["Industry"] = f"▶ {name}"
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

    # Firm vs industry comparison
    if industry and any([firm_pe, firm_pbv, firm_ps, firm_ev_eb, firm_ev_s]):
        st.markdown(f"### {industry} — your firm vs industry")
        ind = INDUSTRY_MULTIPLES[industry]
        comp = []
        for mult_name, firm_val, ind_val in [
            ("PE (forward)", firm_pe, ind["pe"]),
            ("PBV", firm_pbv, ind["pbv"]),
            ("PS", firm_ps, ind["ps"]),
            ("EV/EBITDA", firm_ev_eb, ind["ev_ebitda"]),
            ("EV/Sales", firm_ev_s, ind["ev_sales"]),
        ]:
            if firm_val > 0 and ind_val:
                pct = (firm_val / ind_val - 1) * 100
                comp.append({
                    "Multiple": mult_name,
                    "Your firm": f"{firm_val:.1f}×",
                    "Industry median": f"{ind_val:.1f}×",
                    "Premium/Discount": f"{pct:+.1f}%",
                    "Signal": "Discount ↑" if pct < -10 else ("Premium ↓" if pct > 10 else "In line"),
                })
        if comp:
            st.dataframe(pd.DataFrame(comp), use_container_width=True, hide_index=True)

st.divider()
st.markdown("""<div style="font-size:0.75rem;color:#475569;text-align:center;padding:12px 0">
Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed., Ch 17–21<br>
Source files: eqmult.xls (equity multiples), firmmult.xls (firm multiples), wacccalc.xls (industry benchmarks)
</div>""", unsafe_allow_html=True)
