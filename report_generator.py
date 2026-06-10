"""
report_generator.py — Complete valuation report matching all 6 pages exactly.
"""
from __future__ import annotations
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import sys
sys.path.insert(0, '/home/claude')

from data_fetcher import CompanyData
from special_cases import DEFAULT_PROB_BY_RATING, RATING_NAMES
from cost_of_capital import full_cost_of_capital
from fcff_models import fcff_2stage
from growth_models import estimate_growth, terminal_value_gordon
from relative_valuation import (justified_equity_multiples, justified_firm_multiples,
                                 score_multiple, INDUSTRY_MULTIPLES)
from optimal_capital_structure import optimal_capital_structure
from special_cases import financial_firm_excess_returns, default_probability_from_rating


@dataclass
class ReportAssumptions:
    g_high:      float = 0.0    # 0 = auto from growth module
    n_high:      int   = 5
    g_stable:    float = 0.03
    stable_roc:  float = 0.12
    erp:         float = 0.055
    run_ocs:     bool  = True


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _pct(v, d=2):   return f"{v:.{d}%}" if v is not None else "N/A"
def _usd(v, d=0):   return f"${v:,.{d}f}m" if v is not None else "N/A"
def _num(v, d=2):   return f"{v:,.{d}f}" if v is not None else "N/A"
def _x(v, d=1):     return f"{v:.{d}f}×" if v is not None else "N/A"
def _dp(v, d=2):    return f"{v:+.{d}f}pp"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');
*{box-sizing:border-box}
body{background:#0a0f1e;color:#cbd5e1;font-family:'DM Sans',sans-serif;font-size:15px;line-height:1.6;margin:0;padding:0}
.wrap{max-width:1020px;margin:0 auto;padding:48px 32px}
h1,h2,h3{font-family:'DM Serif Display',serif}
.sec{margin:48px 0 20px;padding-bottom:12px;border-bottom:2px solid #1e3a5f}
.sec h2{font-size:1.6rem;color:#f1f5f9;margin:0}
.sec p{color:#64748b;font-size:0.9rem;margin:4px 0 0}
.sub{color:#e2e8f0;font-size:1.1rem;margin:24px 0 10px;font-family:'DM Serif Display',serif}
.metrics{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.mc{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;flex:1;min-width:130px}
.ml{font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:4px}
.mv{font-size:1.6rem;font-family:'DM Serif Display',serif;color:#f1f5f9;letter-spacing:-0.5px}
.mn{font-size:0.75rem;color:#64748b;margin-top:2px}
.formula{background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:12px 0;font-family:monospace;font-size:0.88rem;color:#7dd3fc}
.fn{color:#94a3b8;margin-top:6px;font-size:0.85rem;font-family:'DM Sans',sans-serif}
.fs{font-size:0.7rem;color:#475569;margin-top:8px;font-family:'DM Sans',sans-serif}
.box{background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:12px 16px;color:#cbd5e1;font-size:0.87rem;margin:10px 0;line-height:1.7}
.ok{background:#14532d22;border:1px solid #22c55e44;border-radius:8px;padding:12px 16px;color:#86efac;font-size:0.85rem;margin:10px 0}
.warn{background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px 16px;color:#fde68a;font-size:0.85rem;margin:10px 0}
.chk-pass{background:#14532d;color:#86efac;border-radius:8px;padding:10px 14px;margin:6px 0;font-size:0.85rem}
.chk-fail{background:#7f1d1d;color:#fca5a5;border-radius:8px;padding:10px 14px;margin:6px 0;font-size:0.85rem}
table{width:100%;border-collapse:collapse;margin:12px 0;border-radius:8px;overflow:hidden}
thead tr{background:#1e293b}
th{padding:8px 12px;text-align:left;font-size:0.78rem;font-weight:500;color:#64748b;border-bottom:1px solid #1e293b}
td{padding:8px 12px;font-size:0.85rem;color:#cbd5e1;border-bottom:1px solid #1e293b1a}
tr.hl td{background:#14532d22}
tr.hl2 td{background:#1e3a5f33}
tr:nth-child(even) td{background:#0f172a}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:0.78rem;font-weight:500;margin:3px 2px}
.scorecard{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:20px 24px;margin:16px 0}
.sbar-wrap{margin-bottom:12px}
.sbar-hdr{display:flex;justify-content:space-between;margin-bottom:3px}
.sbar-bg{background:#1e293b;border-radius:4px;height:7px}
.sbar-fg{height:7px;border-radius:4px}
.hero{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);border-radius:16px;padding:48px;margin-bottom:40px}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin:16px 0}
.val-card{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 18px}
.val-label{font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;color:#64748b;margin-bottom:4px}
.val-number{font-size:1.7rem;font-family:'DM Serif Display',serif;color:#f1f5f9}
.summary-row{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.summary-item{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px 16px;flex:1;min-width:160px}
.si-label{font-size:0.72rem;color:#475569;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px}
.si-val{font-size:1.3rem;font-family:'DM Serif Display',serif;color:#f1f5f9}
.si-interp{font-size:0.75rem;color:#64748b;margin-top:4px}
@media print{body{background:white;color:#1a1a1a}.wrap{padding:20px}}
"""

def _sc(s):
    if s >= 7: return "#22c55e"
    if s >= 4: return "#f59e0b"
    return "#ef4444"

def _badge(score, text):
    c = _sc(score); short = text[:70]+"…" if len(text) > 70 else text
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}44">{score}/10 — {short}</span>'

def _badges(*items): return '<div style="margin:10px 0">'+"".join(_badge(s,t) for s,t in items)+'</div>'

def _metric(label, value, note=""):
    n = f'<div class="mn">{note}</div>' if note else ""
    return f'<div class="mc"><div class="ml">{label}</div><div class="mv">{value}</div>{n}</div>'

def _metrics(*items):
    cells = "".join(_metric(l,v,n) for item in items for l,v,*rest in [item+(("",) if len(item)<3 else ())] for n in [rest[0] if rest else ""])
    return f'<div class="metrics">{cells}</div>'

def _section(title, subtitle=""):
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return f'<div class="sec"><h2>{title}</h2>{sub}</div>'

def _sub(t): return f'<div class="sub">{t}</div>'

def _formula(f, note="", src=""):
    n = f'<div class="fn">{note}</div>' if note else ""
    s = f'<div class="fs">📚 {src}</div>' if src else ""
    return f'<div class="formula">{f}{n}{s}</div>'

def _box(t, colour="#3b82f6"):
    return f'<div class="box" style="border-color:{colour}">{t}</div>'

def _ok(t):   return f'<div class="ok">✓ {t}</div>'
def _warn(t): return f'<div class="warn">⚠ {t}</div>'

def _table(headers, rows, highlight=None, highlight2=None):
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for i, row in enumerate(rows):
        cls = 'hl' if highlight is not None and i == highlight else 'hl2' if highlight2 is not None and i == highlight2 else ''
        tds = "".join(f"<td>{c}</td>" for c in row)
        trs += f"<tr class='{cls}'>{tds}</tr>"
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"

def _scorecard(scores):
    composite = sum(s for s,_ in scores.values()) / len(scores)
    bars = ""
    for label, (score, text) in scores.items():
        c = _sc(score); pct = score*10
        bars += f'''<div class="sbar-wrap">
<div class="sbar-hdr"><span style="font-size:0.85rem;color:#cbd5e1">{label}</span>
<span style="font-size:0.85rem;color:{c};font-weight:500">{score}/10</span></div>
<div class="sbar-bg"><div class="sbar-fg" style="background:{c};width:{pct}%"></div></div>
<div style="font-size:0.75rem;color:#64748b;margin-top:2px">{text[:70]}</div></div>'''
    return f'''<div class="scorecard">
<div class="ml">Composite Score</div>
<div style="font-size:2.5rem;font-family:'DM Serif Display',serif;color:#f1f5f9;margin-bottom:16px">{composite:.1f}<span style="font-size:1rem;color:#64748b"> / 10</span></div>
{bars}</div>'''

# ── Scoring functions ─────────────────────────────────────────────────────────

def _s_wacc(w):
    p=w*100
    if p<5:  return 9,"Very low WACC"
    if p<7:  return 8,"Low — below typical 7–9%"
    if p<9:  return 7,"Average — 7–9% range"
    if p<11: return 5,"Above average"
    if p<14: return 3,"High — elevated financing costs"
    return 1,"Very high"

def _s_icr(icr):
    if icr==math.inf or icr>12.5: return 10,"Exceptional — Aaa/AAA equivalent"
    if icr>8.5: return 9,"Excellent — Aa/AA equivalent"
    if icr>5.5: return 8,"Strong — A-range rating"
    if icr>3.0: return 6,"Adequate — BBB to A−"
    if icr>2.0: return 4,"Weak — BB range"
    if icr>1.25:return 2,"Stressed — B range"
    return 1,"Distressed"

def _s_beta(b):
    if b<0.5:  return 9,"Defensive"
    if b<0.8:  return 8,"Low volatility"
    if b<1.1:  return 7,"Market-rate risk"
    if b<1.4:  return 5,"Moderately elevated"
    if b<1.8:  return 3,"High beta"
    return 1,"Very high beta"

def _s_ke(ke):
    p=ke*100
    if p<7:  return 9,"Very low cost of equity"
    if p<9:  return 8,"Below average"
    if p<11: return 7,"Average — 9–11%"
    if p<13: return 5,"Above average"
    if p<16: return 3,"High"
    return 1,"Very high"

def _s_tv(tv_pct):
    if tv_pct<.50: return 9,"Low TV dependence — most value from near-term cash flows"
    if tv_pct<.65: return 7,"Moderate — typical for stable businesses"
    if tv_pct<.80: return 5,"High — sensitive to stable-growth assumptions"
    return 3,f"Very high (>{tv_pct:.0%}) — treat terminal value assumptions with care"

def _s_mos(price, value):
    if price<=0 or value<=0: return 5,"No price"
    r=value/price
    if r>1.5:  return 10,f"Large margin of safety — value {r:.1f}× price"
    if r>1.2:  return 8,f"Good — {r:.1f}× price"
    if r>0.9:  return 6,f"Fairly valued — {r:.1f}× price"
    if r>0.7:  return 4,"Mild overvaluation"
    return 2,"Significant overvaluation"

def _s_roc(roc, wacc):
    ex=roc-wacc
    if ex>.15: return 9,f"ROC {ex:.1%} above WACC — exceptional value creation"
    if ex>.05: return 8,f"Healthy {ex:.1%} excess return"
    if ex>0:   return 6,f"Marginal {ex:.1%} excess return"
    if ex>-.03:return 4,"ROC ≈ WACC — value neutral"
    return 2,f"ROC {abs(ex):.1%} below WACC — destroying value"

def _s_growth(g):
    if g>.30: return 4,"Very high (>30%) — few firms sustain this"
    if g>.15: return 7,"High — realistic for high-growth firms"
    if g>.05: return 8,"Moderate — normal corporate range"
    if g>0:   return 7,"Low — appropriate for mature businesses"
    return 5,"Negative — declining or trough"

def _s_distress(p):
    if p<.01: return 9,f"Negligible risk ({p:.2%})"
    if p<.05: return 7,f"Low risk ({p:.2%})"
    if p<.15: return 5,f"Moderate risk ({p:.2%})"
    if p<.35: return 3,f"High risk ({p:.2%})"
    return 1,f"Very high risk ({p:.2%})"

def _s_pos(cur, opt):
    gap=abs(cur-opt); d="over-levered" if cur>opt else "under-levered"
    if gap<.03: return 9,"Near-optimal — within 3%"
    if gap<.08: return 7,f"Modestly {d} — {gap:.0%} from optimal"
    if gap<.15: return 5,f"Noticeably {d} — {gap:.0%} from optimal"
    return 2,f"Significantly {d} — {gap:.0%} from optimal"

def _sm(t, v, ind=None):
    from relative_valuation import score_multiple
    s,tx,_ = score_multiple(t, v, ind); return s, tx


# ── Executive Summary ─────────────────────────────────────────────────────────

def _render_summary(d, coc, g, fcff, eq_m, fm, ocs):
    price = d.price or 0
    wacc_v  = coc.wacc_result.wacc if coc else 0
    ke_v    = coc.beta_result.ke   if coc else 0
    g_rec   = g.recommended_growth if g else 0
    roc_v   = g.roc                if g else 0
    vps     = fcff.value_per_share if fcff else 0

    # All implied values
    implied = {}
    if fcff and vps: implied["FCFF (2-stage DCF)"] = vps
    if eq_m and eq_m.implied_price_pe: implied["PE multiple"] = eq_m.implied_price_pe
    if eq_m and eq_m.implied_price_pbv: implied["PBV multiple"] = eq_m.implied_price_pbv
    if fm and fm.implied_ev_from_ebit:
        p = (fm.implied_ev_from_ebit - d.book_debt + d.cash)/d.shares if d.shares else 0
        if p > 0: implied["EV/EBIT multiple"] = p
    if fm and fm.implied_ev_from_sales:
        p = (fm.implied_ev_from_sales - d.book_debt + d.cash)/d.shares if d.shares else 0
        if p > 0: implied["EV/Sales multiple"] = p

    avg = sum(implied.values())/len(implied) if implied else 0
    prem = (price/avg - 1) if avg > 0 and price > 0 else None
    sent = ("Potentially undervalued" if prem and prem < -0.15 else
            "Potentially overvalued"  if prem and prem > 0.15 else
            "Broadly fairly valued")
    sent_c = "#22c55e" if "under" in sent else ("#ef4444" if "over" in sent else "#f59e0b")

    impl_rows = "".join(
        f'<tr><td style="color:#94a3b8">{k}</td>'
        f'<td style="font-weight:500;color:#f1f5f9">${v:.2f}</td>'
        f'<td style="color:{"#86efac" if v>price else "#fca5a5"}">'
        f'{"↑" if v>price else "↓"} {abs(v/price-1)*100:.1f}%</td></tr>'
        for k,v in implied.items() if v > 0 and price > 0
    ) if price > 0 else ""

    # Key value table (the 7 most important metrics)
    key_vals = [
        ("WACC", _pct(wacc_v), "Discount rate — lower is better for equity holders", _s_wacc(wacc_v)[0]),
        ("ROC", _pct(roc_v), f"Return on invested capital vs WACC {_pct(wacc_v)}", _s_roc(roc_v, wacc_v)[0]),
        ("ROC − WACC", f"{(roc_v-wacc_v)*100:+.2f}pp", "Positive = value creation, negative = destruction",
         9 if roc_v>wacc_v+0.05 else 7 if roc_v>wacc_v else 3),
        ("Recommended Growth", _pct(g_rec), "High-growth period rate (fundamental + historical blend)",
         _s_growth(g_rec)[0]),
        ("Intrinsic Value/Share", f"${vps:.2f}" if vps else "N/A",
         f"vs market price ${price:.2f} — {abs(vps/price-1)*100:.1f}% {'upside' if vps>price else 'downside'}" if vps and price else "",
         _s_mos(price, vps)[0] if vps else 5),
        ("TV as % of Firm", _pct(fcff.pv_terminal_value/fcff.value_of_firm) if fcff and fcff.value_of_firm else "N/A",
         "% of value coming from terminal assumptions", _s_tv(fcff.pv_terminal_value/fcff.value_of_firm)[0] if fcff and fcff.value_of_firm else 5),
        ("Optimal D/(D+E)", _pct(ocs.optimal_debt_ratio) if ocs else "N/A",
         f"Current {_pct(ocs.current_debt_ratio)} — {'under' if ocs and ocs.current_debt_ratio < ocs.optimal_debt_ratio else 'over'}-levered" if ocs else "",
         _s_pos(ocs.current_debt_ratio, ocs.optimal_debt_ratio)[0] if ocs else 5),
    ]

    kv_html = "".join(f'''<div class="summary-item">
<div class="si-label">{lab}</div>
<div class="si-val" style="color:{"#f1f5f9"}">{val}</div>
<div class="si-interp">{interp}</div>
<div style="margin-top:6px"><span class="badge" style="font-size:0.7rem;background:{_sc(sc)}22;color:{_sc(sc)};border:1px solid {_sc(sc)}44">{sc}/10</span></div>
</div>''' for lab,val,interp,sc in key_vals)

    return f'''<div class="hero">
<div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:3px;color:#3b82f6;margin-bottom:8px">Damodaran Investment Valuation Toolkit</div>
<h1 style="font-size:2.8rem;color:#f1f5f9;margin:0 0 4px;letter-spacing:-1px">{d.name}</h1>
<div style="font-size:1rem;color:#64748b;margin-bottom:4px">{d.ticker} · {datetime.now().strftime("%d %B %Y")} · Data: {d.source}</div>
<div style="font-size:0.8rem;color:#475569">Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed. · Spreads: Jan 2026</div>
</div>

{_section("Executive Summary", "The seven most important values and their interpretations")}

<div class="summary-row">{kv_html}</div>

<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;margin:16px 0">
<div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:12px">Implied Value by Method — current price ${price:.2f}</div>
<table><thead><tr><th>Method</th><th>Implied Price</th><th>vs Market</th></tr></thead>
<tbody>{impl_rows}</tbody></table>
<div style="margin-top:12px;padding:10px 14px;background:{sent_c}22;border-radius:6px;color:{sent_c};font-size:0.88rem;font-weight:500">{sent}</div>
</div>'''


# ── Module 01 ─────────────────────────────────────────────────────────────────

def _render_coc(d, coc):
    dc=coc.debt_cost; br=coc.beta_result; wr=coc.wacc_result
    from cost_of_capital import _TABLE_NAMES
    h = _section("Module 01 — Cost of Capital", "Ch 7–8 · ratings.xls · levbeta.xls · wacccalc.xls")

    h += _sub(f"Step 1 — Synthetic Credit Rating [{_TABLE_NAMES.get(dc.firm_type,'Large firm')}]")
    h += _formula(
        f"ICR = EBIT / Interest = {_usd(d.ebit)} / {_usd(d.interest_expense)} = {dc.icr:.2f}×  →  {dc.rating}  →  spread {dc.company_spread:.2%}",
        note=f"Interpretation: {_s_icr(dc.icr)[1]}",
        src="Damodaran Ch 8 p.183; ratings.xls"
    )
    h += _metrics(("EBIT", _usd(d.ebit)), ("Interest Expense", _usd(d.interest_expense)),
                  ("ICR", f"{dc.icr:.2f}×" if dc.icr<999 else "∞"),
                  ("Rating → Spread", f"{dc.rating}"),
                  ("Pre-tax kd", _pct(dc.kd_pretax)), ("After-tax kd", _pct(dc.kd_aftertax)))
    h += _box(f"Pre-tax kd = {dc.rf:.2%} + {dc.company_spread:.2%}{' + '+_pct(dc.country_spread)+' country' if dc.country_spread else ''} = <strong>{dc.kd_pretax:.2%}</strong><br>"
              f"After-tax kd = {dc.kd_pretax:.2%} × (1 − {dc.tax_rate:.2%}) = <strong>{dc.kd_aftertax:.2%}</strong>")

    h += _sub("Step 2 — Beta & Cost of Equity")
    h += _formula(
        f"β_u = {br.beta_levered_input:.3f} / [1 + (1−{br.tax_rate:.2%}) × {br.current_de:.3f}] = {br.beta_unlevered:.3f}<br>"
        f"ke = {br.rf:.2%} + {br.beta_relevered:.3f} × {br.erp:.2%} = {br.ke:.2%}",
        note=f"CAPM: ke = {br.rf:.2%} + {br.beta_relevered:.3f} × {br.erp:.2%} = {br.ke:.2%}<br>"
             f"Unlevering: β_u = {br.beta_levered_input:.3f} / [1 + (1−{br.tax_rate:.2%}) × {br.current_de:.3f}] = {br.beta_unlevered:.3f}",
        src="Damodaran Ch 8 p.170; levbeta.xls"
    )
    h += _metrics(("Input Beta", f"{br.beta_levered_input:.3f}"), ("Unlevered Beta", f"{br.beta_unlevered:.3f}"),
                  ("Re-levered Beta", f"{br.beta_relevered:.3f}"),
                  ("rf", _pct(br.rf)), ("ERP", _pct(br.erp)), ("Cost of Equity", _pct(br.ke)))

    h += _sub("Step 3 — Market Value of Debt")
    diff_pct = (coc.market_debt - d.book_debt)/d.book_debt*100 if d.book_debt else 0
    h += _formula(
        f"MV(Debt) = {_usd(d.interest_expense)} × annuity({dc.kd_pretax:.2%},{d.avg_debt_maturity:.0f}) + {_usd(d.book_debt)} / (1+{dc.kd_pretax:.2%})^{d.avg_debt_maturity:.0f} = {_usd(coc.market_debt)}",
        src="Damodaran Ch 8 p.194; wacccalc.xls"
    )
    h += _metrics(("Book Value of Debt", _usd(d.book_debt)), ("Market Value of Debt", _usd(coc.market_debt)),
                  ("Difference", f"{diff_pct:+.1f}%"))

    h += _sub("Step 4 — WACC Assembly")
    h += _metrics(("Equity Weight", _pct(wr.weight_equity,0), f"+ {_usd(wr.equity_mv)}"),
                  ("Debt Weight", _pct(wr.weight_debt,0), f"+ {_usd(coc.market_debt)}"),
                  ("Total Capital (MV)", _usd(wr.total_capital)),
                  ("WACC", _pct(wr.wacc)))
    h += _formula(
        f"WACC build-up:<br>"
        f"Equity: {br.ke:.2%} × {wr.weight_equity:.1%} = {br.ke*wr.weight_equity:.2%}<br>"
        f"Debt: {dc.kd_aftertax:.2%} × {wr.weight_debt:.1%} = {dc.kd_aftertax*wr.weight_debt:.2%}<br>"
        f"<strong>WACC = {wr.wacc:.2%}</strong>",
        src="Damodaran Ch 8 p.195; wacccalc.xls"
    )

    scores = {"WACC": _s_wacc(wr.wacc), "Cost of Equity": _s_ke(br.ke),
              "Interest Coverage": _s_icr(dc.icr), "Beta": _s_beta(br.beta_relevered)}
    h += _scorecard(scores)
    return h


# ── Module 03 ─────────────────────────────────────────────────────────────────

def _render_growth(d, g, tv, coc):
    wacc_v = coc.wacc_result.wacc if coc else 0.09
    ke_v   = coc.beta_result.ke   if coc else 0.10
    h = _section("Module 03 — Growth & Terminal Value", "Ch 11–12 · chgrowth.xls")

    # Growth estimation
    h += _sub("Growth Estimation — Three Approaches")
    h += _formula(
        f"g(firm) = ROC × RIR = {g.roc:.2%} × {g.reinvestment_rate:.2%} = {g.fundamental_growth_firm:.2%}<br>"
        f"g(equity) = ROE × Retention = {g.roe:.2%} × {g.retention_ratio:.2%} = {g.fundamental_growth_equity:.2%}",
        src="Damodaran Ch 11 p.278"
    )
    h += _metrics(("Fundamental g (firm)", _pct(g.fundamental_growth_firm)),
                  ("Fundamental g (equity)", _pct(g.fundamental_growth_equity)),
                  ("Recommended growth", _pct(g.recommended_growth)),
                  ("ROC", _pct(g.roc)))
    sg, tg = _s_growth(g.recommended_growth)
    sr, tr = _s_roc(g.roc, wacc_v)
    h += _badges((sg, tg), (sr, tr))

    h += _box(
        f"Build-up:<br>"
        f"ROC = EBIT×(1−t)/IC = {d.ebit*(1-d.tax_rate):,.0f}/{d.book_equity+d.book_debt:,.0f} = <strong>{g.roc:.2%}</strong><br>"
        f"RIR = (Net CapEx + ΔWC)/NOPAT = {(d.capex-d.depreciation+d.delta_wc):,.0f}/{d.ebit*(1-d.tax_rate):,.0f} = <strong>{g.reinvestment_rate:.2%}</strong><br>"
        f"Fundamental g (firm) = {g.roc:.2%} × {g.reinvestment_rate:.2%} = <strong>{g.fundamental_growth_firm:.2%}</strong><br>"
        f"ROE = NI/BV_Equity = {d.net_income:,.0f}/{d.book_equity:,.0f} = <strong>{g.roe:.2%}</strong><br>"
        + (f"Historical EPS CAGR: <strong>{g.historical_eps_cagr:.2%}</strong><br>" if g.historical_eps_cagr else "")
        + f"<strong>Recommended: {g.recommended_growth:.2%}</strong> — {g.recommended_basis}"
    )

    h += _table(["Approach", "Growth Rate", "Basis"], [
        ["Fundamental (firm)",   _pct(g.fundamental_growth_firm),   "ROC × Reinvestment Rate"],
        ["Fundamental (equity)", _pct(g.fundamental_growth_equity), "ROE × Retention Ratio"],
        ["Historical EPS CAGR",  _pct(g.historical_eps_cagr) if g.historical_eps_cagr else "N/A", "Geometric mean"],
        ["Analyst estimate",     _pct(g.analyst_growth) if g.analyst_growth else "N/A", "Consensus"],
        ["Recommended blend",    _pct(g.recommended_growth), g.recommended_basis],
    ], highlight=4)

    # Auto-computed note
    d_ratio = d.book_debt/(d.book_equity+d.book_debt) if (d.book_equity+d.book_debt) else 0.2
    eq_reinv = (1-d_ratio)*((d.capex-d.depreciation)+d.delta_wc)
    payout_auto = max(0, min(0.95, 1-eq_reinv/d.net_income)) if d.net_income else 0.5
    h += _box(
        f"Auto-computed from live data:<br>"
        f"ke = {ke_v:.2%} (from Module 01 CAPM)<br>"
        f"Recommended growth = {g.recommended_growth:.2%} (fundamental + historical blend)<br>"
        f"FCFE/NI payout proxy = {payout_auto:.2%}"
    )

    # Terminal value
    h += _sub("Terminal Value")
    if tv:
        h += _metrics(("Terminal Value", f"${tv.terminal_value:,.0f}"),
                      ("TV Multiple", f"{tv.terminal_value/max(d.fcff,1):,.1f}×"),
                      ("Stable RIR", _pct(tv.g_stable/0.12)))
        h += _sub("Terminal Value Consistency Checks")
        for v in tv.checks.values():
            css = "chk-pass" if v["pass"] else "chk-fail"
            h += f'<div class="{css}">{"✓" if v["pass"] else "✗"} <strong>{v["label"]}</strong><br>{v["detail"]}</div>'
        h += _sub("Terminal Value Sensitivity (±2pp around base case)")
        g_vals = sorted(set(k[0] for k in tv.sensitivity))
        r_vals = sorted(set(k[1] for k in tv.sensitivity))
        rows = []
        for g2 in g_vals:
            row = [f"{g2:.2%}"]
            for r2 in r_vals:
                v = tv.sensitivity.get((g2,r2))
                row.append(f"${v:,.0f}" if v else "—")
            rows.append(row)
        h += _table(["g \\ WACC"] + [f"{r2:.2%}" for r2 in r_vals], rows)
    return h


# ── Module 02 ─────────────────────────────────────────────────────────────────

def _render_fcff(d, r, price=0, market_debt=None):
    tv_pct = r.pv_terminal_value / r.value_of_firm if r.value_of_firm > 0 else 0
    # Tax rate anomaly warning
    tax_warn = ""
    if d.tax_rate_anomaly and d.tax_rate_prior_year:
        tax_warn = (_warn(
            f"Tax rate anomaly detected: effective rate {_pct(d.tax_rate)} deviates more than "
            f"10pp from prior year {_pct(d.tax_rate_prior_year)}. This often indicates a "
            f"one-time item (e.g. valuation allowance charge) that inflates the reported rate. "
            f"Damodaran Ch 10 p.248: use a normalised marginal rate for forward valuation. "
            f"Consider using the prior-year rate ({_pct(d.tax_rate_prior_year)}) or the "
            f"statutory rate for NOPAT and FCFF calculations."
        ))
    g_used = r.inputs.get("g_high", 0)
    g_s    = r.inputs.get("g_stable", 0.03)
    sr     = r.inputs.get("stable_roc", 0.12)
    ws     = r.inputs.get("wacc_stable", 0)
    h = _section("Module 02 — Cash Flow Valuation (FCFF 2-stage)", "Ch 10, 15 · fcff2st.xls · fcffginzu.xlsx")
    h += _formula(
        "FCFF = EBIT×(1−t) − Net_CapEx − ΔWC<br>"
        "Value_Firm = Σ PV(FCFF₁…ₙ) + PV(TV)<br>"
        "Value_Equity = Value_Firm − Debt + Cash",
        note=f"High-growth rate: <strong>{g_used:.2%}</strong> (auto from growth module) · "
             f"Stable rate: <strong>{g_s:.2%}</strong> · "
             f"Stable RIR: <strong>{g_s/sr:.1%}</strong> (= g/ROC = {g_s:.2%}/{sr:.2%}) · "
             f"Stable WACC: <strong>{ws:.2%}</strong>" f" (= high-growth WACC × 0.95: reflects lower beta ~0.8–1.0 and less leverage risk in stable phase — adjust this if firm will differ materially at maturity; Ch 12 p.303)",
        src="Damodaran Ch 10 p.247; Ch 15 p.375"
    )
    if tax_warn: h += tax_warn

    h += _metrics(("Value of Firm", _usd(r.value_of_firm)),
                  ("Value of Equity", _usd(r.value_of_equity)),
                  ("Value / Share", f"${r.value_per_share:.2f}",
                   f"{(r.value_per_share/price-1)*100:+.1f}% vs price" if price else ""),
                  ("Terminal Value %", _pct(tv_pct,0)))
    s_tv, t_tv = _s_tv(tv_pct)
    s_m,  t_m  = _s_mos(price, r.value_per_share)
    h += _badges((s_tv, t_tv), (s_m, t_m))

    # Use market value of debt in bridge per Damodaran Ch 15 p.375
    mv_debt_used = market_debt if market_debt and market_debt > 0 else r.debt_mv
    eq_corrected = r.value_of_firm - mv_debt_used + r.cash
    vps_corrected = eq_corrected / r.shares if r.shares > 0 else 0
    mv_note = (f"<br><em style='font-size:0.8rem;color:#94a3b8'>Note: equity bridge uses market value of debt "
               f"({_usd(mv_debt_used)}) per Ch 15 p.375, not book debt ({_usd(r.debt_mv)})</em>"
               if abs(mv_debt_used - r.debt_mv) > 500 else "")
    h += _box(
        f"Value bridge:<br>"
        f"PV high-growth FCFFs: <strong>{_usd(r.pv_fcff_highgrowth)}</strong><br>"
        f"PV terminal value: <strong>{_usd(r.pv_terminal_value)}</strong> ({tv_pct:.0%} of firm value)<br>"
        f"= Firm value: <strong>{_usd(r.value_of_firm)}</strong><br>"
        f"− Market debt: {_usd(mv_debt_used)} + Cash: {_usd(r.cash)}<br>"
        f"= Equity: <strong>{_usd(eq_corrected)}</strong> ÷ {r.shares:,.0f}m shares"
        f" = <strong style='color:#3b82f6;font-size:1.05rem'>${vps_corrected:.2f}/share</strong>"
        f"{mv_note}"
    )

    h += _sub("Terminal Value")
    h += _metrics(("Terminal FCFF", _usd(r.terminal_fcff)),
                  ("Terminal Value", _usd(r.terminal_value)),
                  ("PV of TV", _usd(r.pv_terminal_value)))
    h += _formula(
        f"TV = Terminal_FCFF / (WACC_stable − g_stable) = "
        f"{_usd(r.terminal_fcff)} / ({ws:.2%} − {g_s:.2%}) = {_usd(r.terminal_value)}"
    )

    if tv_pct > 0.75:
        h += _warn(f"Terminal value is {tv_pct:.0%} of firm value — highly sensitive to WACC and g assumptions.")
    else:
        h += _ok(f"Terminal value dependency {tv_pct:.0%} — within acceptable range.")

    # Year-by-year table (compact)
    h += _sub("Year-by-year Cash Flows")
    rows = [[str(row.year), _usd(row.ebit,0), _usd(row.nopat,0), _usd(row.net_capex,0),
             _usd(row.delta_wc,0), _pct(row.reinvestment_rate,0), _usd(row.fcff,0),
             _pct(row.wacc), _usd(row.pv_fcff,0)] for row in r.yearly]
    h += _table(["Year","EBIT","NOPAT","Net CapEx","ΔWC","RIR","FCFF","WACC","PV(FCFF)"], rows)
    return h


# ── Module 04 ─────────────────────────────────────────────────────────────────

def _render_multiples(d, eq_m, fm, coc, g, payout_high):
    price = d.price or 0
    ke_v  = coc.beta_result.ke if coc else 0.10
    g_use = g.recommended_growth if g else 0.10
    h = _section("Module 04 — Relative Valuation", "Ch 17–21 · eqmult.xls · firmmult.xls")

    # Equity multiples
    if eq_m:
        h += _sub("Equity Multiples (2-stage DDM)")
        h += _formula(
            "PE = PV(FCFE stream)/EPS₁    PBV = PE × ROE    PS = PE × net_margin    PEG = PE/(g×100)",
            note="Note: PBV = PE × ROE and PS = PE × net_margin are algebraic identities — "
                 "they derive from the same DDM as PE and will produce the same implied price. "
                 "They are not independent methods; they are one model expressed in three ways "
                 "(Ch 17–19). Use them to cross-check margin and ROE assumptions, not as "
                 "independent valuation evidence.",
            src="Damodaran Ch 17–19; eqmult.xls"
        )
        h += f'<div class="card-grid">'
        for label, val, fmt in [("PE (FORWARD)", eq_m.pe_forward, ".1f"),
                                  ("PE (TRAILING)", eq_m.pe_trailing, ".1f"),
                                  ("PBV", eq_m.pbv, ".2f"),
                                  ("PS (FORWARD)", eq_m.ps_forward, ".2f")]:
            h += f'<div class="val-card"><div class="val-label">{label}</div><div class="val-number">{val:{fmt}}×</div></div>'
        if eq_m.peg:
            h += f'<div class="val-card"><div class="val-label">PEG Ratio</div><div class="val-number">{eq_m.peg:.2f}×</div></div>'
        h += '</div>'

        s_pe,t_pe = _sm("pe", eq_m.pe_forward)
        s_pb,t_pb = _sm("pbv", eq_m.pbv)
        s_pg,t_pg = _sm("peg", eq_m.peg or 0)
        h += _badges((s_pe, t_pe), (s_pb, t_pb), (s_pg, t_pg))

        h += _sub("Implied prices")
        rows = []
        for label, val in [(f"From PE ({eq_m.pe_forward:.1f}×)", eq_m.implied_price_pe),
                            (f"From PBV ({eq_m.pbv:.2f}×)", eq_m.implied_price_pbv),
                            (f"From PS ({eq_m.ps_forward:.2f}×)", eq_m.implied_price_ps)]:
            if val:
                rows.append([label, f"${val:.2f}",
                              f"{(val/price-1)*100:+.1f}%" if price else "—"])
        h += _table(["Method","Implied Price","vs Current"], rows)
        h += _box(f"ROE (high growth implied): {eq_m.roe_high:.2%} | ROE (stable): {eq_m.roe_stable:.2%}<br>"
                  f"FCFE/NI payout used: {payout_high:.2%} — "
                  f"{'positive spread: ROE > ke' if eq_m.roe_high > ke_v else 'ROE < ke — growth may not add value'}")

    # Firm multiples
    if fm:
        h += _sub("Firm Multiples (2-stage FCFF)")
        h += _formula(
            "EV/EBIT_fwd = EV/NOPAT × (1−t)    EV/Sales = EV/NOPAT × margin    EV/IC = EV/NOPAT × ROIC",
            note="Note: EV/Sales and EV/EBIT that imply the same EV are also algebraic transforms of "
                 "the same FCFF model via margin and tax rate. When they return identical prices, "
                 "that is expected — they are not independent (Ch 20). Check that the margin "
                 "assumption in EV/Sales is realistic relative to the EBIT margin.",
            src="Damodaran Ch 20; firmmult.xls"
        )
        h += f'<div class="card-grid">'
        for label, val, fmt in [("EV/EBIT (FWD)", fm.ev_ebit_forward, ".1f"),
                                  ("EV/EBIT (TRL)", fm.ev_ebit_trailing, ".1f"),
                                  ("EV/SALES (FWD)", fm.ev_sales_forward, ".1f"),
                                  ("EV/IC", fm.ev_ic, ".1f")]:
            h += f'<div class="val-card"><div class="val-label">{label}</div><div class="val-number">{val:{fmt}}×</div></div>'
        h += '</div>'

        s_ev, t_ev = _sm("ev_sales", fm.ev_sales_forward)
        h += _badges((s_ev, f"EV/Sales {fm.ev_sales_forward:.1f}× — {t_ev}"))

        h += _sub("Implied EV → Equity → Price")
        rows = []
        for label, ev in [("EV/EBIT", fm.implied_ev_from_ebit),
                           ("EV/IC",   fm.implied_ev_from_ic),
                           ("EV/Sales",fm.implied_ev_from_sales)]:
            if ev and ev > 0:
                eq = ev - d.book_debt + d.cash
                vps2 = eq/d.shares if d.shares else 0
                rows.append([label, f"${ev:,.0f}m", f"${eq:,.0f}m",
                              f"${vps2:.2f}",
                              f"{(vps2/price-1)*100:+.1f}%" if price and vps2 else "—"])
        h += _table(["Method","Implied EV","Equity","Price/Share","vs Current"], rows)
        h += _box(f"ROIC (high growth): {fm.roic_high:.2%} | ROIC (stable): {fm.roic_stable:.2%}<br>"
                  f"EV/IC = {fm.ev_ic:.2f}× — {'value creation: ROIC > WACC' if fm.roic_high > fm.wacc_high else 'value destruction: ROIC < WACC'}")
    return h


# ── Module 05 ─────────────────────────────────────────────────────────────────

def _render_ocs(d, ocs):
    h = _section("Module 05 — Optimal Capital Structure", "Ch 15 · capstru.xlsx")
    h += _metrics(
        ("Current D/(D+E)", _pct(ocs.current_debt_ratio,1)),
        ("Optimal D/(D+E)", _pct(ocs.optimal_debt_ratio,1),
         _dp((ocs.optimal_debt_ratio-ocs.current_debt_ratio)*100)),
        ("Current WACC",    _pct(ocs.current_wacc)),
        ("Optimal WACC",    _pct(ocs.optimal_wacc),
         _dp((ocs.optimal_wacc-ocs.current_wacc)*100)),
        ("Current Firm Value", _usd(ocs.current_firm_value)),
        ("Optimal Firm Value", _usd(ocs.optimal_firm_value),
         f"+{_usd(ocs.value_gain)}"),
        ("Current Price", f"${d.price:.2f}" if d.price else "N/A"),
        ("Optimal Price/Share",
         f"${ocs.optimal_price_per_share:.2f}" if ocs.optimal_price_per_share > 0 else "N/A"),
    )
    s, t = _s_pos(ocs.current_debt_ratio, ocs.optimal_debt_ratio)
    h += _badges((s, t))

    direction = "over-levered" if ocs.current_debt_ratio > ocs.optimal_debt_ratio else "under-levered"
    action = "reduce debt" if direction == "over-levered" else "issue more debt and repurchase shares"
    repurchase = ""
    if ocs.new_debt_issued > 0 and d.price and d.price > 0:
        repurchase = (f"<br>Repurchase: issue ${ocs.new_debt_issued:,.0f}m debt, "
                      f"repurchase {ocs.shares_repurchased:,.0f}m shares. "
                      f"Remaining shares → ${ocs.optimal_price_per_share:.2f}/share." if ocs.optimal_price_per_share > 0
                      else "<br>Repurchase analysis: N/A (optimal price negative — OCS firm value inconsistent with DCF at current growth)")
    # DCF-consistent value gain: apply WACC delta to DCF firm value if available
    wacc_delta = ocs.current_wacc - ocs.optimal_wacc
    h += _box(
        f"<strong>Interpretation:</strong> {d.name} is currently <strong>{direction}</strong>. "
        f"Current D/(D+E) = {ocs.current_debt_ratio:.1%} vs optimal {ocs.optimal_debt_ratio:.1%}.<br>"
        f"Recommended action: <strong>{action}</strong>.{repurchase}"
        f"<br><br><em style='font-size:0.82rem;color:#94a3b8'>"
        f"⚠ OCS firm value ({_usd(ocs.current_firm_value)}) uses a zero-growth perpetuity "
        f"(NOPAT/WACC) and will be far smaller than the DCF value for high-growth firms. "
        f"The WACC reduction ({_pct(ocs.current_wacc)} → {_pct(ocs.optimal_wacc)}, "
        f"Δ = {wacc_delta*100:.2f}pp) is directionally correct. "
        f"For a DCF-consistent gain estimate: apply the WACC reduction to the DCF firm value. "
        f"Textbook ref: Ch 15 p.395</em>"
    )

    opt_idx = next((i for i,r in enumerate(ocs.sweep) if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001), -1)
    cur_idx = next((i for i,r in enumerate(ocs.sweep) if abs(r.debt_ratio-ocs.current_debt_ratio)<0.005), -1)
    rows = []
    for i, r in enumerate(ocs.sweep):
        tag = " ◀ OPTIMAL" if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001 else (
              " ◀ current" if abs(r.debt_ratio-ocs.current_debt_ratio)<0.005 else "")
        rows.append([f"{r.debt_ratio:.0%}{tag}", r.rating, _pct(r.kd_pretax), _pct(r.ke),
                     _pct(r.wacc), _usd(r.firm_value,0) if r.firm_value<1e12 else "∞"])
    h += _sub("Full debt ratio sweep")
    h += _table(["D/(D+E)","Rating","kd","ke","WACC","Firm Value"], rows, highlight=opt_idx, highlight2=cur_idx)
    return h


# ── Module 06 ─────────────────────────────────────────────────────────────────

def _render_special(d, coc, fcff_result=None):
    from special_cases import financial_firm_excess_returns
    wacc_v = coc.wacc_result.wacc if coc else 0.09
    ke_v   = coc.beta_result.ke   if coc else 0.10
    ic     = d.book_equity + d.book_debt
    nopat  = d.ebit * (1 - d.tax_rate)
    roc    = nopat / ic if ic > 0 else 0
    eva_0  = nopat - wacc_v * ic

    h = _section("Module 06 — Special Cases", "Ch 21, 22, 30, 32 · fcffeva.xls · fcffsimpleginzu.xlsx")

    # ── EVA ──────────────────────────────────────────────────────────────────
    h += _sub("EVA Framework — Current Year")
    h += _formula(
        f"EVA = NOPAT − WACC × Invested_Capital<br>"
        f"    = {nopat:,.0f} − {wacc_v:.2%} × {ic:,.0f}<br>"
        f"    = <strong>{eva_0:,.0f}</strong> ({'positive — value creation' if eva_0>0 else 'negative — value destruction'})",
        note=f"= (ROC − WACC) × IC = ({roc:.2%} − {wacc_v:.2%}) × {ic:,.0f} = {eva_0:,.0f}",
        src="Damodaran Ch 32 p.799; fcffeva.xls"
    )
    h += _metrics(("NOPAT", _usd(nopat,0)), ("WACC Charge", _usd(wacc_v*ic,0)),
                  ("EVA", _usd(eva_0,0), "positive" if eva_0>0 else "negative"),
                  ("ROC", _pct(roc)), ("Excess Return", f"{(roc-wacc_v)*100:+.2f}pp"))
    s_r, t_r = _s_roc(roc, wacc_v)
    h += _badges((s_r, t_r))
    h += (_ok(f"Positive EVA of {_usd(eva_0,0)} — earns {roc:.2%} on capital vs {wacc_v:.2%} cost. Every dollar invested creates value.")
          if eva_0 > 0 else
          _warn(f"Negative EVA — ROC {roc:.2%} is below WACC {wacc_v:.2%}. Growth destroys value."))

    # EVA cross-check vs DCF
    if fcff_result and fcff_result.value_of_firm > 0:
        # Simple EVA firm value = IC + PV(EVA perpetuity)
        eva_perp = eva_0 / wacc_v if wacc_v > 0 else 0
        eva_fv   = ic + eva_perp
        dcf_fv   = fcff_result.value_of_firm
        diff_pct = abs(eva_fv - dcf_fv)/dcf_fv*100 if dcf_fv > 0 else 0
        h += _metrics(("Firm Value (EVA, perpetuity)", _usd(eva_fv,0)),
                      ("FCFF Cross-check", _usd(dcf_fv,0)),
                      ("Difference", f"{diff_pct:.1f}%",
                       "Note: EVA perpetuity ≠ DCF (different growth assumptions)"))

    # EVA 5-year projection (fixed IC, growing NOPAT — matches page behaviour)
    h += _sub("EVA — 5-Year Projection")
    h += _box(
        "NOPAT grows at 10% p.a. while IC is held fixed (consistent with page behaviour). "
        "ROC therefore rises each year — this is a modelling limitation: if NOPAT grows, "
        "IC should also grow by the retained reinvestment. The Damodaran-correct approach "
        "(Ch 11 p.280) ties IC growth to the reinvestment rate: ΔIC = NOPAT × RIR. "
        "This projection overstates short-run value creation but is shown for page consistency. "
        "The main FCFF DCF (Module 02) handles this correctly via the RIR and net capex."
    )
    eva_rows = []
    nopat_t = nopat
    for t in range(1, 6):
        nopat_t *= 1.10
        wc_t = wacc_v * ic
        eva_t = nopat_t - wc_t
        roc_t = nopat_t / ic
        pv_t  = eva_t / (1+wacc_v)**t
        eva_rows.append([f"Year {t}", _usd(nopat_t,0), _usd(wc_t,0), _usd(eva_t,0), _pct(roc_t), _usd(pv_t,0)])
    h += _table(["Year","NOPAT","WACC Charge","EVA","ROC","PV(EVA)"], eva_rows)

    # ── Distressed ────────────────────────────────────────────────────────────
    h += _sub("2. Distressed Firm Analysis")
    h += _formula(
        "Adjusted_Value = GC_Value × (1 − p_default) + Distress_Sale × p_default",
        src="Damodaran Ch 22 p.556; Ch 30 p.727; Moody's default data"
    )

    # Full default probability table
    h += _sub("Default Probability Table (Moody's cumulative, by rating and horizon)")
    prob_rows = []
    for rating in RATING_NAMES:
        probs = DEFAULT_PROB_BY_RATING[rating]
        prob_rows.append([rating] + [f"{p:.2%}" for p in probs])
    h += _table(["Rating","Yr1","Yr2","Yr3","Yr4","Yr5"], prob_rows)

    # GC value from FCFF model
    rating_raw = coc.debt_cost.rating if coc else "Baa2/BBB"
    rating_s   = ("AAA" if "AAA" in rating_raw else "AA" if "AA" in rating_raw else
                  "A" if "/A" in rating_raw and "BBB" not in rating_raw else
                  "BBB" if "BBB" in rating_raw else "BB" if "BB" in rating_raw else
                  "B" if "/B" in rating_raw else "CCC/C")
    p5 = default_probability_from_rating(rating_s, 5)
    gc_val = fcff_result.value_of_firm if (fcff_result and fcff_result.value_of_firm > 0) else d.equity_market_cap + d.book_debt
    distress_sale = d.book_debt * 0.6
    adj_fv = gc_val*(1-p5) + distress_sale*p5
    eq_gc  = max(0, gc_val      - d.book_debt + d.cash)
    eq_adj = max(0, adj_fv      - d.book_debt + d.cash)
    vps_gc  = eq_gc  / d.shares if d.shares else 0
    vps_adj = eq_adj / d.shares if d.shares else 0

    h += f'<div style="margin-top:8px"><strong>Distress sale value:</strong> ${distress_sale:,.2f}m (60% of book debt)</div>'
    h += _table(
        ["Horizon","Default Prob","GC Value/Share","Adjusted Value/Share","vs Market Price"],
        [
            [f"{yr}yr", _pct(default_probability_from_rating(rating_s, yr)),
             f"${vps_gc:.2f}",
             f"${max(0, (gc_val*(1-default_probability_from_rating(rating_s,yr)) + distress_sale*default_probability_from_rating(rating_s,yr)) - d.book_debt + d.cash)/d.shares if d.shares else 0:.2f}",
             f"{(max(0,(gc_val*(1-default_probability_from_rating(rating_s,yr))+distress_sale*default_probability_from_rating(rating_s,yr))-d.book_debt+d.cash)/d.shares/d.price-1)*100:+.1f}%" if d.price and d.shares else "—"]
            for yr in [1,3,5]
        ]
    )
    s_d, t_d = _s_distress(p5)
    h += _badges((s_d, f"5-year default probability {p5:.2%} — {t_d}"))
    h += _box(
        f"Synthetic rating: <strong>{rating_raw}</strong> (→ {rating_s} for Moody's lookup)<br>"
        f"GC value: ${gc_val:,.0f}m × (1−{p5:.2%}) = ${gc_val*(1-p5):,.0f}m<br>"
        f"Distress proceeds: ${distress_sale:,.0f}m × {p5:.2%} = ${distress_sale*p5:,.0f}m<br>"
        f"Adjusted firm value: ${adj_fv:,.0f}m → Equity: ${eq_adj:,.0f}m"
    )

    # ── Financial firm ────────────────────────────────────────────────────────
    h += _sub("3. Financial Firm — Excess Returns Model")
    is_financial = d.firm_type == 3
    ff_caveat = ("" if is_financial else
                 "<br><strong style='color:#fde68a'>⚠ Illustrative only:</strong> "
                 "This model is designed for banks and insurers (Ch 21) where debt is raw material. "
                 "Applying it to a non-financial firm overstates equity value because the model "
                 "ignores the reinvestment required to sustain growth. "
                 "Do not use this value for non-financial companies.")
    h += _formula(
        "Value = Book_Equity + PV[(ROE − ke) × Book_Equity]",
        note=f"For banks/insurers where debt is raw material, not capital{ff_caveat}",
        src="Damodaran Ch 21 p.519"
    )
    roe_curr = d.net_income / d.book_equity if d.book_equity > 0 else 0
    try:
        ff = financial_firm_excess_returns(
            book_equity=d.book_equity,
            roe_high=roe_curr, ke_high=ke_v, g_high=0.08, n_high=5,
            roe_stable=max(ke_v*1.05, 0.08), ke_stable=ke_v*0.9, g_stable=0.03,
            shares=d.shares,
        )
        pbv_ff = ff.value_of_equity / ff.book_equity if ff.book_equity > 0 else 0
        h += _metrics(
            ("Book Equity",      _usd(ff.book_equity,0)),
            ("PV Excess Returns",_usd(ff.pv_excess_returns,0)),
            ("Equity Value",     _usd(ff.value_of_equity,0)),
            ("Value/Share",      f"${ff.value_per_share:.2f}",
             f"{(ff.value_per_share/d.price-1)*100:+.1f}%" if d.price else ""),
        )
        s_ff, t_ff = _s_roc(roe_curr, ke_v)
        h += _badges((s_ff, t_ff))
        h += _box(
            f"Excess return: ROE {roe_curr:.2%} − ke {ke_v:.2%} = <strong>{(roe_curr-ke_v)*100:+.2f}%/yr</strong> on book equity<br>"
            f"PBV = {pbv_ff:.2f}× — {'justified by ROE > ke' if roe_curr > ke_v else 'ROE < ke — should trade below book'}"
        )
    except Exception as e:
        h += _warn(f"Financial firm model: {e}")

    # ── Earnings normalisation ────────────────────────────────────────────────
    h += _sub("4. Earnings Normalisation")
    h += _formula(
        "Method 1: Average of last N years' earnings<br>"
        "Method 2: Avg historical margin × current revenue  (preferred)<br>"
        "Method 3: Industry/historical ROA × current assets",
        src="Damodaran Ch 22 p.541"
    )
    curr_margin = d.net_income/d.revenue if d.revenue > 0 else 0
    norm_rows = [["Current (reported)", _usd(d.net_income,0), _pct(curr_margin), "May be distorted"]]
    rec = d.net_income

    if d.historical_eps and d.shares and d.shares > 0:
        hist_ni = [e * d.shares for e in d.historical_eps]
        avg_ni  = sum(hist_ni) / len(hist_ni)
        norm_rows.append(["Avg historical earnings", _usd(avg_ni,0), "—", "Simple average"])
        if d.historical_revenue and len(d.historical_revenue) == len(d.historical_eps):
            margins = [ni/r for ni,r in zip(hist_ni, d.historical_revenue) if r > 0]
            avg_mg  = sum(margins)/len(margins) if margins else curr_margin
            norm_mg = avg_mg * d.revenue
            norm_rows.append(["Avg margin × revenue", _usd(norm_mg,0), _pct(avg_mg), f"Avg margin: {avg_mg:.2%}"])
            rec = norm_mg
        norm_rows.append(["ROA × assets", "N/A", "—", "Not provided"])

    h += _table(["Method","Earnings ($m)","Margin","Note"], norm_rows)
    h += _box(f"Recommended normalised earnings: <strong>{_usd(rec,0)}</strong> (average margin method)<br>"
              f"Current vs normalised: <strong>{(d.net_income/rec-1)*100:+.1f}%</strong> {'above' if d.net_income>rec else 'below'} long-run average." if rec != d.net_income else "")
    return h


# ── Data Audit ────────────────────────────────────────────────────────────────

def _render_audit(d, g_use=0, wacc_v=0, a=None):
    rows = [
        ["Company name",         d.name,                        "yfinance / EDGAR"],
        ["EBIT",                 _usd(d.ebit,0),                "EDGAR: OperatingIncomeLoss"],
        ["Interest expense",     _usd(d.interest_expense,0),    "EDGAR: InterestExpense"],
        ["Net income",           _usd(d.net_income,0),          "EDGAR: NetIncomeLoss"],
        ["Revenue",              _usd(d.revenue,0),             "EDGAR: Revenues"],
        ["EBITDA",               _usd(d.ebitda,0),              "Derived: EBIT + D&A"],
        ["Book debt",            _usd(d.book_debt,0),           "EDGAR: LongTermDebt + ShortTermBorrowings"],
        ["Book equity",          _usd(d.book_equity,0),         "EDGAR: StockholdersEquity"],
        ["Cash",                 _usd(d.cash,0),                "EDGAR: CashAndCashEquivalents"],
        ["Total assets",         _usd(d.total_assets,0),        "EDGAR: Assets"],
        ["CapEx",                _usd(d.capex,0),               "EDGAR: PaymentsToAcquirePropertyPlant"],
        ["Depreciation",         _usd(d.depreciation,0),        "EDGAR: DepreciationAndAmortization"],
        ["Net CapEx",            _usd(d.capex-d.depreciation,0),"Derived: CapEx − Depr"],
        ["ΔWorking Capital",     _usd(d.delta_wc,0),            "EDGAR: IncreaseDecreaseInOperatingCapital"],
        ["FCFF (current)",       _usd(d.fcff,0),                "Derived: NOPAT − Net CapEx − ΔWC"],
        ["Market cap",           _usd(d.equity_market_cap,0),   "yfinance info"],
        ["Beta (levered)",       f"{d.beta_levered:.3f}",        f"Source: {d.beta_source}"],
        ["Stock price",          f"${d.price:.2f}" if d.price else "N/A", "yfinance / manual"],
        ["Shares outstanding",   f"{d.shares:,.0f}m",           "EDGAR: WeightedAverageNumberOfDilutedSharesOutstanding"],
        ["EPS (trailing)",       f"${d.eps:.2f}" if d.eps else "N/A", "EDGAR: EarningsPerShareBasic"],
        ["Risk-free rate",       _pct(d.rf),                    "FRED DGS10"],
        ["Equity risk premium",  _pct(d.erp),                   "Damodaran (Jan 2026)"],
        ["Tax rate",             _pct(d.tax_rate),              "Derived: IncomeTaxExpense / PreTaxIncome"],
        ["Avg debt maturity",    f"{d.avg_debt_maturity:.0f} years", "EDGAR / default 5yr"],
        ["Firm type",            {1:"Large firm",2:"Small/risky",3:"Financial"}.get(d.firm_type,""), ""],
        ["Growth rate (FCFF)",   _pct(g_use) if g_use else "auto", "From growth module blend"],
        ["Stable WACC (TV)",     _pct(wacc_v*0.95) if wacc_v else "N/A", "WACC × 0.95 for terminal period"],
        ["Stable RIR (TV)",      f"{a.g_stable/a.stable_roc:.1%}" if a and a.stable_roc else "N/A",
         f"g/ROC = {a.g_stable:.2%}/{a.stable_roc:.2%}" if a else ""],
        ["Data source",          d.source, ""],
    ]
    err = _warn("Data warnings: " + " · ".join(d.fetch_errors[:4])) if d.fetch_errors else ""
    h = _section("Data Audit Trail", "All inputs used in this report — every value, its source, and formula role")
    h += err
    h += _table(["Input","Value","Source"], rows)
    h += f'<div style="font-size:0.8rem;color:#475569;margin-top:8px">Report: {datetime.now().strftime("%d %b %Y %H:%M UTC")} · Damodaran Investment Valuation 2nd Ed. (2002) · Spreads Jan-2026</div>'
    return h


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_report(d: CompanyData, a: Optional[ReportAssumptions] = None) -> str:
    if a is None: a = ReportAssumptions()
    errors = []

    # Module 01
    coc = None
    try:
        coc = full_cost_of_capital(
            ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=a.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=d.firm_type)
    except Exception as e: errors.append(f"CoC: {e}")

    wacc_v = coc.wacc_result.wacc if coc else 0.09
    ke_v   = coc.beta_result.ke   if coc else 0.10

    # Module 03
    g_result = tv_result = None
    try:
        g_result = estimate_growth(
            ebit=d.ebit, tax_rate=d.tax_rate,
            net_capex=d.capex-d.depreciation, delta_wc=d.delta_wc,
            book_equity=d.book_equity, book_debt=d.book_debt,
            net_income=d.net_income, dividends=0,
            historical_eps=d.historical_eps or None,
            historical_rev=d.historical_revenue or None)
        tv_result = terminal_value_gordon(max(d.fcff, 1), wacc_v, a.g_stable, a.stable_roc)
    except Exception as e: errors.append(f"Growth: {e}")

    g_use = a.g_high if a.g_high > 0 else max((g_result.recommended_growth if g_result else 0), 0.03)

    # Module 02
    fcff_result = None
    try:
        wc_pct   = d.delta_wc/d.revenue if d.revenue > 0 else 0.02
        # Fix 2: use market value of debt (from Module 01) not book debt.
        # This ensures r.value_per_share and the value bridge box agree exactly.
        # Per Damodaran Ch 15 p.375: equity = firm_value - MV(debt) + cash.
        mv_debt_for_fcff = coc.market_debt if coc and coc.market_debt > 0 else d.book_debt
        fcff_result = fcff_2stage(
            ebit=d.ebit, tax_rate=d.tax_rate, capex=d.capex, depreciation=d.depreciation,
            delta_wc=d.delta_wc, revenues=d.revenue,
            wacc_high=wacc_v, g_high=g_use, n_high=a.n_high,
            g_stable=a.g_stable, wacc_stable=wacc_v*0.95, stable_roc=a.stable_roc,
            wc_pct_rev=wc_pct, debt_mv=mv_debt_for_fcff, cash=d.cash, shares=d.shares)
    except Exception as e: errors.append(f"FCFF: {e}")

    # Module 04
    eq_m = fm = payout_high = None
    try:
        d_ratio   = d.book_debt/(d.book_equity+d.book_debt) if (d.book_equity+d.book_debt) else 0.2
        eq_reinv  = (1-d_ratio)*((d.capex-d.depreciation)+d.delta_wc)
        payout_high = max(0.0, min(0.95, 1-eq_reinv/d.net_income)) if d.net_income > 0 else 0.5
        payout_s  = min(0.80, payout_high*1.2)
        net_mg    = d.net_income/d.revenue if d.revenue > 0 else 0.10
        eq_m = justified_equity_multiples(
            g_high=g_use, payout_high=payout_high, ke_high=ke_v, n=a.n_high,
            g_stable=a.g_stable, payout_stable=payout_s, ke_stable=ke_v*0.9,
            net_margin=net_mg,
            book_equity_per_share=d.book_equity/d.shares if d.shares else 1,
            eps_next_year=d.eps*(1+g_use) if d.eps else 1,
            revenues_next_year=d.revenue/d.shares*(1+g_use) if d.shares else 0)
        rir_h = max(0.05, (d.capex-d.depreciation+d.delta_wc)/(d.ebit*(1-d.tax_rate))) if d.ebit else 0.4
        fm = justified_firm_multiples(
            g_high=g_use, rir_high=rir_h, wacc_high=wacc_v,
            margin_high=d.ebit*(1-d.tax_rate)/d.revenue if d.revenue else 0.15,
            n=a.n_high, g_stable=a.g_stable, rir_stable=a.g_stable/a.stable_roc,
            wacc_stable=wacc_v*0.95, margin_stable=net_mg, tax_rate=d.tax_rate,
            nopat_next_year=d.ebit*(1-d.tax_rate)*(1+g_use),
            invested_capital=d.book_equity+d.book_debt,
            revenues_next_year=d.revenue*(1+g_use))
    except Exception as e: errors.append(f"Multiples: {e}")

    # Module 05
    ocs = None
    try:
        if a.run_ocs and d.fcff > 0 and d.equity_market_cap > 0:
            ocs = optimal_capital_structure(
                ebitda=d.ebitda or d.ebit+d.depreciation, depreciation=d.depreciation,
                ebit=d.ebit, interest_expense=d.interest_expense, tax_rate=d.tax_rate,
                equity_mv=d.equity_market_cap, debt_mv=d.book_debt,
                beta_levered=d.beta_levered, rf=d.rf, erp=a.erp,
                fcff=d.fcff, g_stable=a.g_stable, firm_type=d.firm_type,
                apply_bankruptcy_costs=True,
                shares_outstanding=d.shares, current_price=d.price,
                cash=d.cash, company=d.name)
    except Exception as e: errors.append(f"OCS: {e}")

    # Render
    body  = _render_summary(d, coc, g_result, fcff_result, eq_m, fm, ocs)
    if errors: body += "".join(_warn(f"Module error: {e}") for e in errors)
    if coc:          body += _render_coc(d, coc)
    if g_result:     body += _render_growth(d, g_result, tv_result, coc)
    if fcff_result:  body += _render_fcff(d, fcff_result, d.price, coc.market_debt if coc else None)
    if eq_m or fm:   body += _render_multiples(d, eq_m, fm, coc, g_result, payout_high or 0.5)
    if ocs:          body += _render_ocs(d, ocs)
    if coc:          body += _render_special(d, coc, fcff_result)
    body += _render_audit(d, g_use, wacc_v, a)

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d.ticker} — Damodaran Valuation</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div class="wrap">{body}
<div style="margin-top:60px;padding-top:20px;border-top:1px solid #1e293b;font-size:0.75rem;color:#334155;text-align:center">
Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed., Wiley Finance, 2002 · Educational purposes only
</div></div></body></html>"""


if __name__ == "__main__":
    from data_fetcher import _make_placeholder
    d = _make_placeholder("META")
    d.ebitda = d.ebit + d.depreciation
    d.fcff   = d.ebit*(1-d.tax_rate) - (d.capex-d.depreciation) - d.delta_wc
    d.historical_eps     = [6.2, 9.5, 14.5, 19.8, 27.5]
    d.historical_revenue = [117929, 116609, 134902, 164501, 200966]
    d.source = "live"
    html = generate_report(d, ReportAssumptions())
    print(f"Size: {len(html):,} bytes")
    import re
    for tag in ["Executive Summary","Module 01","Module 02","Module 03",
                "Module 04","Module 05","Module 06","Data Audit"]:
        print(f"  {'✓' if tag in html else '✗'} {tag}")
    with open("/tmp/report_test.html","w") as f: f.write(html)
