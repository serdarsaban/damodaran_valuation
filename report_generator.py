"""
report_generator.py
===================
Generates a complete self-contained HTML report — identical in depth to
what the Streamlit pages show, not a summary.

Runs all 6 modules in full:
  Module 01 — Cost of Capital (full step-by-step)
  Module 02 — FCFF 2-stage (full year-by-year table)
  Module 03 — Growth (all 3 approaches + TV checks + sensitivity)
  Module 04 — Relative Valuation (equity + firm multiples + implied prices)
  Module 05 — Optimal Capital Structure (full sweep table + charts data)
  Module 06 — Special Cases (EVA, distressed, normalised earnings)
"""

from __future__ import annotations
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import sys
sys.path.insert(0, '/home/claude')

from data_fetcher import CompanyData
from cost_of_capital import full_cost_of_capital
from fcff_models import fcff_2stage
from growth_models import estimate_growth, terminal_value_gordon, benchmark_vs_industry
from relative_valuation import (justified_equity_multiples, justified_firm_multiples,
                                 score_multiple, INDUSTRY_MULTIPLES)
from optimal_capital_structure import optimal_capital_structure
from special_cases import eva_valuation, distressed_firm_value, default_probability_from_rating


@dataclass
class ReportAssumptions:
    g_high:         float = 0.0    # 0 = auto from growth module
    n_high:         int   = 5
    g_stable:       float = 0.03
    stable_roc:     float = 0.12
    payout_high:    float = 0.0    # 0 = auto FCFE/NI ratio
    payout_stable:  float = 0.0
    net_margin:     float = 0.0    # 0 = auto from live data
    erp:            float = 0.055
    run_ocs:        bool  = True


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _pct(v, d=2): return f"{v:.{d}%}" if v is not None else "N/A"
def _usd(v, d=0): return f"${v:,.{d}f}m" if v is not None else "N/A"
def _num(v, d=2): return f"{v:,.{d}f}" if v is not None else "N/A"
def _x(v, d=1):   return f"{v:.{d}f}×" if v is not None else "N/A"

def _sc(score):
    if score >= 7: return "#22c55e"
    if score >= 4: return "#f59e0b"
    return "#ef4444"

def _badge(score, text):
    c = _sc(score)
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:0.78rem;font-weight:500;background:{c}22;color:{c};border:1px solid {c}44">{score}/10 — {text}</span>'

def _section(title, subtitle=""):
    sub = f'<p style="color:#64748b;font-size:0.9rem;margin:4px 0 0">{subtitle}</p>' if subtitle else ""
    return f'<div style="margin:48px 0 20px;padding-bottom:12px;border-bottom:2px solid #1e3a5f"><h2 style="font-family:\'DM Serif Display\',serif;font-size:1.6rem;color:#f1f5f9;margin:0">{title}</h2>{sub}</div>'

def _subsection(title):
    return f'<h3 style="color:#e2e8f0;font-size:1.1rem;margin:24px 0 10px">{title}</h3>'

def _metrics(*items):
    def _card(m):
        l, v = m[0], m[1]
        note = m[2] if len(m) > 2 and m[2] else ""
        note_html = f'<div style="font-size:0.75rem;color:#64748b;margin-top:2px">{note}</div>' if note else ""
        return (f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;'
                f'padding:16px 20px;flex:1;min-width:130px">'
                f'<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;'
                f'color:#475569;margin-bottom:4px">{l}</div>'
                f'<div style="font-size:1.6rem;font-family:\'DM Serif Display\',serif;'
                f'color:#f1f5f9;letter-spacing:-0.5px">{v}</div>{note_html}</div>')
    cells = "".join(_card(m) for m in items)
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0">{cells}</div>'

def _formula(formula, note="", source=""):
    s = f'<div style="font-size:0.7rem;color:#475569;margin-top:8px">📚 {source}</div>' if source else ""
    n = f'<div style="color:#94a3b8;margin-top:6px;font-size:0.85rem">{note}</div>' if note else ""
    return f'<div style="background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:12px 0;font-family:monospace;font-size:0.88rem;color:#7dd3fc">{formula}{n}{s}</div>'

def _box(text, colour="#3b82f6"):
    return f'<div style="background:{colour}11;border-left:3px solid {colour};border-radius:0 8px 8px 0;padding:12px 16px;color:#cbd5e1;font-size:0.87rem;margin:10px 0;line-height:1.7">{text}</div>'

def _table(headers, rows, highlight=-1):
    th = "".join(f'<th style="padding:8px 12px;text-align:left;font-size:0.78rem;font-weight:500;color:#64748b;border-bottom:1px solid #1e293b">{h}</th>' for h in headers)
    tr = "".join(f'<tr style="background:{"#14532d22" if i==highlight else "#0f172a" if i%2==0 else "#111827"}">'+"".join(f'<td style="padding:8px 12px;font-size:0.85rem;color:#cbd5e1;border-bottom:1px solid #1e293b1a">{c}</td>' for c in row)+"</tr>" for i,row in enumerate(rows))
    return f'<table style="width:100%;border-collapse:collapse;margin:12px 0;border-radius:8px;overflow:hidden"><thead><tr style="background:#1e293b">{th}</tr></thead><tbody>{tr}</tbody></table>'

def _warn(text): return f'<div style="background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px 16px;color:#fde68a;font-size:0.85rem;margin:10px 0">⚠ {text}</div>'
def _ok(text):   return f'<div style="background:#14532d22;border:1px solid #22c55e44;border-radius:8px;padding:12px 16px;color:#86efac;font-size:0.85rem;margin:10px 0">✓ {text}</div>'


# ── Full section renderers ─────────────────────────────────────────────────────

def _render_coc(d, coc):
    dc=coc.debt_cost; br=coc.beta_result; wr=coc.wacc_result
    from cost_of_capital import _TABLE_NAMES
    html  = _section("Module 01 — Cost of Capital", "Ch 7–8 · ratings.xls · levbeta.xls · wacccalc.xls")
    html += _subsection(f"Step 1 — Synthetic Credit Rating [{_TABLE_NAMES.get(dc.firm_type,'Large firm')}]")
    html += _formula(f"ICR = EBIT / Interest = {d.ebit:,.0f} / {d.interest_expense:,.0f} = {dc.icr:.2f}×  →  {dc.rating}  →  spread {dc.company_spread:.2%}", source="Damodaran Ch 8 p.183; ratings.xls")
    html += _metrics(("ICR", f"{dc.icr:.2f}×" if dc.icr<999 else "∞"), ("Rating", dc.rating), ("Company Spread", _pct(dc.company_spread)), ("Pre-tax kd", _pct(dc.kd_pretax)), ("After-tax kd", _pct(dc.kd_aftertax)))
    html += _box(f"kd = rf + spread = {dc.rf:.2%} + {dc.company_spread:.2%}{(' + ' + _pct(dc.country_spread) + ' country') if dc.country_spread else ''} = <strong>{dc.kd_pretax:.2%}</strong>  →  after-tax = {dc.kd_pretax:.2%} × (1−{dc.tax_rate:.0%}) = <strong>{dc.kd_aftertax:.2%}</strong>")

    html += _subsection("Step 2 — Beta & Cost of Equity")
    html += _formula(f"β_u = {br.beta_levered_input:.3f} / [1 + (1−{br.tax_rate:.0%})×{br.current_de:.4f}] = {br.beta_unlevered:.3f}<br>ke = {br.rf:.2%} + {br.beta_relevered:.3f} × {br.erp:.2%} = {br.ke:.2%}", source="Damodaran Ch 8 p.170; levbeta.xls")
    html += _metrics(("Unlevered β", f"{br.beta_unlevered:.3f}"), ("Re-levered β", f"{br.beta_relevered:.3f}"), ("rf", _pct(br.rf)), ("ERP", _pct(br.erp)), ("Cost of Equity", _pct(br.ke)))

    html += _subsection("Step 3 — Market Value of Debt & WACC")
    html += _formula(f"MV(Debt) = {d.interest_expense:,.0f}×annuity({dc.kd_pretax:.2%},5) + {d.book_debt:,.0f}/(1+{dc.kd_pretax:.2%})⁵ = {coc.market_debt:,.0f}<br>WACC = {br.ke:.2%}×{wr.weight_equity:.0%} + {dc.kd_aftertax:.2%}×{wr.weight_debt:.0%} = {wr.wacc:.2%}", source="Damodaran Ch 8 p.194–195; wacccalc.xls")
    html += _metrics(("Book Debt", _usd(d.book_debt)), ("Market Debt", _usd(coc.market_debt)), ("Equity Weight", _pct(wr.weight_equity,0)), ("Debt Weight", _pct(wr.weight_debt,0)), ("WACC", _pct(wr.wacc)))
    return html


def _render_growth(d, g, tv):
    html  = _section("Module 03 — Growth & Terminal Value", "Ch 11–12 · chgrowth.xls")
    html += _subsection("Three Growth Approaches")
    html += _formula(f"g(firm) = ROC × RIR = {g.roc:.2%} × {g.reinvestment_rate:.2%} = {g.fundamental_growth_firm:.2%}<br>g(equity) = ROE × Retention = {g.roe:.2%} × {g.retention_ratio:.2%} = {g.fundamental_growth_equity:.2%}", source="Damodaran Ch 11 p.278")
    html += _table(["Approach","Growth Rate","Basis"],[
        ["Fundamental (firm)",   _pct(g.fundamental_growth_firm),   "ROC × Reinvestment Rate"],
        ["Fundamental (equity)", _pct(g.fundamental_growth_equity), "ROE × Retention Ratio"],
        ["Historical EPS CAGR",  _pct(g.historical_eps_cagr) if g.historical_eps_cagr else "N/A", "Geometric mean"],
        ["Analyst estimate",     _pct(g.analyst_growth) if g.analyst_growth else "N/A", "Consensus"],
        ["Recommended blend",    _pct(g.recommended_growth), g.recommended_basis],
    ], 4)
    html += _box(f"Recommended growth: <strong>{_pct(g.recommended_growth)}</strong> — {g.recommended_basis}")

    if tv:
        html += _subsection("Terminal Value Consistency Checks")
        for v in tv.checks.values():
            colour = "#22c55e" if v["pass"] else "#ef4444"
            html += f'<div style="padding:10px 14px;border-radius:6px;margin:6px 0;font-size:0.85rem;background:{colour}11;color:{colour}">{"✓" if v["pass"] else "✗"} <strong>{v["label"]}:</strong> {v["detail"]}</div>'

        html += _subsection("Terminal Value Sensitivity (±2pp around base case)")
        g_vals = sorted(set(k[0] for k in tv.sensitivity))
        r_vals = sorted(set(k[1] for k in tv.sensitivity))
        rows = []
        for g2 in g_vals:
            row = [f"{g2:.2%}"]
            for r2 in r_vals: row.append(f"${tv.sensitivity.get((g2,r2)):,.0f}" if tv.sensitivity.get((g2,r2)) else "—")
            rows.append(row)
        html += _table(["g \\ WACC"] + [f"{r2:.2%}" for r2 in r_vals], rows)
    return html


def _render_fcff(d, r):
    tv_pct = r.pv_terminal_value / r.value_of_firm if r.value_of_firm > 0 else 0
    html  = _section("Module 02 — Cash Flow Valuation (FCFF 2-stage)", "Ch 10, 15 · fcff2st.xls · fcffginzu.xlsx")
    html += _formula("FCFF = EBIT×(1−t) − Net_CapEx − ΔWC<br>Value_Firm = Σ PV(FCFF) + PV(TV)<br>Value_Equity = Value_Firm − Debt + Cash", source="Damodaran Ch 10 p.247; Ch 15 p.375")

    year_rows = [[str(row.year), _usd(row.ebit,0), _usd(row.nopat,0),
                  _usd(row.net_capex,0), _usd(row.delta_wc,0),
                  _pct(row.reinvestment_rate,0), _usd(row.fcff,0),
                  _pct(row.wacc), _usd(row.pv_fcff,0)] for row in r.yearly]
    html += _table(["Year","EBIT","NOPAT","Net CapEx","ΔWC","RIR","FCFF","WACC","PV(FCFF)"], year_rows)

    html += _metrics(
        ("PV FCFFs (1–n)", _usd(r.pv_fcff_highgrowth,0)),
        ("Terminal FCFF",  _usd(r.terminal_fcff,0)),
        ("Terminal Value", _usd(r.terminal_value,0)),
        ("PV Terminal",    _usd(r.pv_terminal_value,0), f"TV = {tv_pct:.0%} of firm"),
    )
    html += _box(
        f"PV FCFFs: <strong>{_usd(r.pv_fcff_highgrowth,0)}</strong><br>"
        f"+ PV Terminal: <strong>{_usd(r.pv_terminal_value,0)}</strong><br>"
        f"= Firm: <strong>{_usd(r.value_of_firm,0)}</strong><br>"
        f"− Debt: {_usd(r.debt_mv,0)} + Cash: {_usd(r.cash,0)}<br>"
        f"= Equity: <strong>{_usd(r.value_of_equity,0)}</strong> ÷ {r.shares:,.0f}m shares"
        f" = <strong style='color:#3b82f6;font-size:1.05rem'>${r.value_per_share:.2f} / share</strong>"
    )
    if tv_pct > 0.75: html += _warn(f"Terminal value is {tv_pct:.0%} of firm value — highly sensitive to WACC and g assumptions.")
    else: html += _ok(f"Terminal value dependency {tv_pct:.0%} — within acceptable range.")
    return html


def _render_multiples(d, eq_m, fm):
    html = _section("Module 04 — Relative Valuation", "Ch 17–21 · eqmult.xls · firmmult.xls")
    price = d.price or 0

    if eq_m:
        html += _subsection("Equity Multiples (2-stage DDM)")
        html += _formula("PE = PV(FCFE stream)/EPS₁    PBV = PE × ROE    PS = PE × net_margin    PEG = PE/(g×100)", source="Damodaran Ch 17–19; eqmult.xls")
        rows = [
            ["PE (forward)",  _x(eq_m.pe_forward),  f"${eq_m.implied_price_pe:.2f}" if eq_m.implied_price_pe else "N/A", f"{(eq_m.implied_price_pe/price-1)*100:+.1f}%" if eq_m.implied_price_pe and price else "—"],
            ["PE (trailing)", _x(eq_m.pe_trailing),  "—", "—"],
            ["PBV",           _x(eq_m.pbv,2),        f"${eq_m.implied_price_pbv:.2f}" if eq_m.implied_price_pbv else "N/A", f"{(eq_m.implied_price_pbv/price-1)*100:+.1f}%" if eq_m.implied_price_pbv and price else "—"],
            ["PS (forward)",  _x(eq_m.ps_forward,2), f"${eq_m.implied_price_ps:.2f}" if eq_m.implied_price_ps else "N/A", f"{(eq_m.implied_price_ps/price-1)*100:+.1f}%" if eq_m.implied_price_ps and price else "—"],
            ["PEG",           _x(eq_m.peg,2) if eq_m.peg else "N/A", "—", "—"],
        ]
        html += _table(["Multiple","Justified","Implied Price","vs Market"], rows)
        html += _box(f"ROE (high growth implied): {eq_m.roe_high:.2%} | ROE (stable): {eq_m.roe_stable:.2%}<br>PBV of {eq_m.pbv:.2f}× {'justified — ROE > ke' if eq_m.roe_high > eq_m.ke_high else 'unjustified — ROE < ke'}")

    if fm:
        html += _subsection("Firm Multiples (2-stage FCFF)")
        html += _formula("EV/EBIT_fwd = EV/NOPAT × (1−t)    EV/Sales = EV/NOPAT × margin    EV/IC = EV/NOPAT × ROIC", source="Damodaran Ch 20; firmmult.xls")
        rows = [
            ["EV/EBIT (forward)",  _x(fm.ev_ebit_forward),   _usd(fm.implied_ev_from_ebit,0) if fm.implied_ev_from_ebit else "N/A"],
            ["EV/EBIT (trailing)", _x(fm.ev_ebit_trailing),  "—"],
            ["EV/Sales (forward)", _x(fm.ev_sales_forward),  _usd(fm.implied_ev_from_sales,0) if fm.implied_ev_from_sales else "N/A"],
            ["EV/IC",              _x(fm.ev_ic),              _usd(fm.implied_ev_from_ic,0) if fm.implied_ev_from_ic else "N/A"],
        ]
        html += _table(["Multiple","Justified","Implied EV"], rows)
        html += _box(f"ROIC (high growth): {fm.roic_high:.2%} | ROIC (stable): {fm.roic_stable:.2%}<br>EV/IC = {fm.ev_ic:.2f}× — {'value creation: ROIC > WACC' if fm.roic_high > fm.wacc_high else 'value destruction: ROIC < WACC'}")
    return html


def _render_ocs(d, ocs):
    html  = _section("Module 05 — Optimal Capital Structure", "Ch 15 · capstru.xlsx")
    html += _metrics(
        ("Current D/(D+E)", _pct(ocs.current_debt_ratio,1)),
        ("Optimal D/(D+E)", _pct(ocs.optimal_debt_ratio,1)),
        ("Current WACC",    _pct(ocs.current_wacc)),
        ("Optimal WACC",    _pct(ocs.optimal_wacc), f"Δ = {(ocs.optimal_wacc-ocs.current_wacc)*100:+.2f}pp"),
        ("Value Gain",      _usd(ocs.value_gain,0)),
    )
    direction = "over-levered" if ocs.current_debt_ratio > ocs.optimal_debt_ratio else "under-levered"
    action = "reduce debt" if direction == "over-levered" else "issue debt and repurchase shares"
    html += _box(f"{d.name} is currently <strong>{direction}</strong>. Recommended: <strong>{action}</strong>.")

    opt_idx = next((i for i,r in enumerate(ocs.sweep) if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001), -1)
    rows = []
    for r in ocs.sweep:
        tag = " ◀ OPTIMAL" if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001 else (" ◀ current" if abs(r.debt_ratio-ocs.current_debt_ratio)<0.005 else "")
        rows.append([f"{r.debt_ratio:.0%}{tag}", r.rating, _pct(r.kd_pretax), _pct(r.ke), _pct(r.wacc), _usd(r.firm_value,0) if r.firm_value<1e12 else "∞"])
    html += _table(["D/(D+E)","Rating","kd","ke","WACC","Firm Value"], rows, opt_idx)
    return html


def _render_special(d, coc):
    wacc_val = coc.wacc_result.wacc if coc else 0.09
    ic = d.book_equity + d.book_debt
    nopat = d.ebit * (1 - d.tax_rate)
    roc = nopat / ic if ic > 0 else 0
    eva_curr = nopat - wacc_val * ic

    html  = _section("Module 06 — Special Cases", "Ch 21, 22, 30, 32 · fcffeva.xls · fcffsimpleginzu.xlsx")

    # EVA
    html += _subsection("EVA — Current Year")
    html += _formula(f"EVA = NOPAT − WACC × IC = {nopat:,.0f} − {wacc_val:.2%} × {ic:,.0f} = {eva_curr:,.0f}", source="Damodaran Ch 32 p.799; fcffeva.xls")
    html += _metrics(("NOPAT", _usd(nopat,0)), ("WACC Charge", _usd(wacc_val*ic,0)), ("EVA", _usd(eva_curr,0)), ("ROC", _pct(roc)), ("ROC − WACC", f"{(roc-wacc_val)*100:+.2f}pp"))
    html += (_ok(f"Positive EVA: {d.name} earns {roc:.2%} on capital vs {wacc_val:.2%} WACC — creating {(roc-wacc_val)*100:.2f}pp of value per year.")
             if eva_curr > 0 else
             _warn(f"Negative EVA: ROC of {roc:.2%} is below WACC of {wacc_val:.2%}. Growth is currently destroying value."))

    # Distress
    html += _subsection("Distress Probability (from Credit Rating)")
    rating = coc.debt_cost.rating if coc else "Baa2/BBB"
    rating_simple = "AAA" if "AAA" in rating else "AA" if "AA" in rating else "A" if "/A" in rating and "BBB" not in rating else "BBB" if "BBB" in rating else "BB" if "BB" in rating else "B" if "/B" in rating else "CCC/C"
    p5 = default_probability_from_rating(rating_simple, 5)
    gc_val = d.equity_market_cap + d.book_debt
    distress_val = d.book_debt * 0.6
    dist = distressed_firm_value(gc_val, d.book_debt, p5, distress_val, d.shares, d.cash)
    html += _table(["Item","Value"],[
        ["Synthetic rating", f"{rating} (→ {rating_simple} for Moody's lookup)"],
        ["5-year default probability", _pct(p5)],
        ["Going-concern equity value/share", f"${dist.value_per_share_gc:.2f}"],
        ["Distress-adjusted equity value/share", f"${dist.value_per_share_adjusted:.2f}"],
        ["Value haircut from distress risk", f"{(1-dist.value_per_share_adjusted/dist.value_per_share_gc)*100:.1f}%" if dist.value_per_share_gc > 0 else "N/A"],
    ])

    # Earnings normalisation
    if d.historical_eps:
        html += _subsection("Earnings Normalisation")
        margins = [e / r for e, r in zip(d.historical_eps, d.historical_revenue) if r > 0] if d.historical_revenue and len(d.historical_revenue) == len(d.historical_eps) else []
        avg_margin = sum(margins)/len(margins) if margins else d.net_income/d.revenue if d.revenue > 0 else 0
        norm_earnings = avg_margin * d.revenue
        curr_margin = d.net_income / d.revenue if d.revenue > 0 else 0
        html += _table(["Method","Normalised Earnings","vs Current"],[
            ["Current (reported)", _usd(d.net_income,0), "—"],
            ["Avg historical margin × revenue", _usd(norm_earnings,0), f"{(norm_earnings/d.net_income-1)*100:+.1f}%" if d.net_income else "—"],
        ])
        if abs(norm_earnings - d.net_income) / d.net_income > 0.15 if d.net_income else False:
            html += _warn(f"Current net income ({_pct(curr_margin)} margin) differs from normalised ({_pct(avg_margin)} avg margin) by more than 15%. Consider using normalised earnings.")
    return html


def _render_cover(d, coc, g, fcff, eq_m, fm, a):
    date = datetime.now().strftime("%d %B %Y")
    price = d.price or 0
    wacc_str = _pct(coc.wacc_result.wacc) if coc else "N/A"
    ke_str   = _pct(coc.beta_result.ke)   if coc else "N/A"
    g_str    = _pct(g.recommended_growth) if g else "N/A"

    implied = {}
    if fcff and fcff.value_per_share: implied["FCFF (2-stage DCF)"] = fcff.value_per_share
    if eq_m and eq_m.implied_price_pe: implied["PE multiple"] = eq_m.implied_price_pe
    if eq_m and eq_m.implied_price_pbv: implied["PBV multiple"] = eq_m.implied_price_pbv
    if fm and fm.implied_ev_from_ebit:
        eq = fm.implied_ev_from_ebit - d.book_debt + d.cash
        implied["EV/EBIT multiple"] = eq/d.shares if d.shares>0 else 0
    if fm and fm.implied_ev_from_sales:
        eq = fm.implied_ev_from_sales - d.book_debt + d.cash
        implied["EV/Sales multiple"] = eq/d.shares if d.shares>0 else 0

    avg = sum(implied.values())/len(implied) if implied else 0
    premium = (price/avg - 1) if avg > 0 and price > 0 else None
    sent = "Potentially undervalued" if premium and premium < -0.15 else ("Potentially overvalued" if premium and premium > 0.15 else "Broadly fairly valued")
    sent_col = "#22c55e" if "under" in sent else ("#ef4444" if "over" in sent else "#f59e0b")

    impl_rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#94a3b8;font-size:0.85rem">{k}</td>'
        f'<td style="padding:6px 12px;color:#f1f5f9;font-size:0.9rem;font-weight:500">${v:.2f}</td>'
        f'<td style="padding:6px 12px;font-size:0.85rem;color:{"#86efac" if v>price else "#fca5a5"}">'
        f'{"↑" if v>price else "↓"} {abs(v/price-1)*100:.1f}% {"upside" if v>price else "downside"}</td></tr>'
        for k,v in implied.items() if v>0 and price>0
    ) if price else ""

    return f'''
<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);border-radius:16px;padding:48px;margin-bottom:40px">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:3px;color:#3b82f6;margin-bottom:8px">Damodaran Investment Valuation Toolkit</div>
  <h1 style="font-family:'DM Serif Display',serif;font-size:2.8rem;color:#f1f5f9;margin:0 0 4px;letter-spacing:-1px">{d.name}</h1>
  <div style="font-size:1rem;color:#64748b;margin-bottom:4px">{d.ticker} · {date} · Data: {d.source}</div>
  <div style="font-size:0.8rem;color:#475569">Based on: Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed. · Spreads: Jan 2026</div>
</div>

<div style="margin:40px 0 20px;padding-bottom:12px;border-bottom:2px solid #1e3a5f">
  <h2 style="font-family:'DM Serif Display',serif;font-size:1.6rem;color:#f1f5f9;margin:0">Executive Summary</h2>
</div>

{_metrics(("Current Price", f"${price:.2f}" if price else "N/A"), ("Avg Implied Value", f"${avg:.2f}" if avg else "N/A", f"{premium*100:+.1f}% vs price" if premium is not None else ""), ("WACC", wacc_str), ("Cost of Equity", ke_str), ("Recommended Growth", g_str))}

<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;margin:16px 0">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:12px">Implied Value by Method</div>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Method</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Implied Price</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">vs Market</th>
    </tr></thead>
    <tbody>{impl_rows}</tbody>
  </table>
  <div style="margin-top:12px;padding:10px 14px;background:{sent_col}22;border-radius:6px;color:{sent_col};font-size:0.88rem;font-weight:500">{sent}</div>
</div>'''


def _render_audit(d):
    rows = [
        ["Company name",        d.name,                     "yfinance info"],
        ["EBIT",                _usd(d.ebit,0),              "yfinance financials"],
        ["Interest expense",    _usd(d.interest_expense,0),  "yfinance financials"],
        ["Net income",          _usd(d.net_income,0),        "yfinance financials"],
        ["Revenue",             _usd(d.revenue,0),           "yfinance financials"],
        ["EBITDA",              _usd(d.ebitda,0),            "yfinance derived"],
        ["Book debt",           _usd(d.book_debt,0),         "yfinance balance_sheet"],
        ["Book equity",         _usd(d.book_equity,0),       "yfinance balance_sheet"],
        ["Cash",                _usd(d.cash,0),              "yfinance balance_sheet"],
        ["Total assets",        _usd(d.total_assets,0),      "yfinance balance_sheet"],
        ["CapEx",               _usd(d.capex,0),             "yfinance cashflow"],
        ["Depreciation",        _usd(d.depreciation,0),      "yfinance cashflow"],
        ["Net CapEx",           _usd(d.capex-d.depreciation,0), "derived: CapEx − Depr"],
        ["ΔWorking Capital",    _usd(d.delta_wc,0),          "yfinance cashflow"],
        ["FCFF (current)",      _usd(d.fcff,0),              "derived: NOPAT − Net CapEx − ΔWC"],
        ["Market cap",          _usd(d.equity_market_cap,0), "yfinance info"],
        ["Beta (levered)",      f"{d.beta_levered:.3f}",     "yfinance info"],
        ["Stock price",         f"${d.price:.2f}" if d.price else "N/A", "yfinance info"],
        ["Shares outstanding",  f"{d.shares:,.0f}m",         "yfinance info"],
        ["EPS (trailing)",      f"${d.eps:.2f}" if d.eps else "N/A", "yfinance info"],
        ["Risk-free rate",      _pct(d.rf),                  "FRED DGS10"],
        ["Equity risk premium", _pct(d.erp),                 "Damodaran (Jan 2026)"],
        ["Tax rate",            _pct(d.tax_rate),            "yfinance derived"],
        ["Avg debt maturity",   f"{d.avg_debt_maturity:.0f} years", "EDGAR / default"],
        ["Firm type",           {1:"Large firm",2:"Small/risky",3:"Financial"}.get(d.firm_type,""), ""],
        ["Data source",         d.source,                    ""],
    ]
    err = f'<div style="background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px;color:#fde68a;font-size:0.85rem;margin:10px 0">⚠ Data warnings: {" · ".join(d.fetch_errors[:4])}</div>' if d.fetch_errors else ""
    return (_section("Data Audit Trail", "All inputs used in this report — every value, its source, and how it flows into calculations")
            + err + _table(["Input","Value","Source"], rows)
            + f'<div style="font-size:0.8rem;color:#475569;margin-top:8px">Report generated: {datetime.now().strftime("%d %b %Y %H:%M UTC")} · Methodology: Damodaran, Investment Valuation 2nd Ed. (2002) · Spreads: Jan-2026 vintage</div>')


def generate_report(d: CompanyData, a: Optional[ReportAssumptions] = None) -> str:
    if a is None: a = ReportAssumptions()
    errors = []

    # Module 01
    coc = None
    try:
        coc = full_cost_of_capital(ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=a.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=d.firm_type)
    except Exception as e: errors.append(f"CoC: {e}")

    wacc_v = coc.wacc_result.wacc if coc else 0.09
    ke_v   = coc.beta_result.ke   if coc else 0.10

    # Module 03: Growth
    g_result = tv_result = None
    try:
        g_result = estimate_growth(ebit=d.ebit, tax_rate=d.tax_rate,
            net_capex=d.capex-d.depreciation, delta_wc=d.delta_wc,
            book_equity=d.book_equity, book_debt=d.book_debt,
            net_income=d.net_income, dividends=0,
            historical_eps=d.historical_eps or None,
            historical_rev=d.historical_revenue or None)
        tv_result = terminal_value_gordon(max(d.fcff,1), wacc_v, a.g_stable, a.stable_roc)
    except Exception as e: errors.append(f"Growth: {e}")

    g_rec = g_result.recommended_growth if g_result else (a.g_high or 0.10)
    g_use = a.g_high if a.g_high > 0 else max(g_rec, 0.03)

    # Module 02: FCFF
    fcff_result = None
    try:
        wc_pct = d.delta_wc / d.revenue if d.revenue > 0 else 0.02
        fcff_result = fcff_2stage(
            ebit=d.ebit, tax_rate=d.tax_rate, capex=d.capex, depreciation=d.depreciation,
            delta_wc=d.delta_wc, revenues=d.revenue,
            wacc_high=wacc_v, g_high=g_use, n_high=a.n_high,
            g_stable=a.g_stable, wacc_stable=wacc_v*0.95, stable_roc=a.stable_roc,
            wc_pct_rev=wc_pct, debt_mv=d.book_debt, cash=d.cash, shares=d.shares)
    except Exception as e: errors.append(f"FCFF: {e}")

    # Module 04: Multiples
    eq_m = fm = None
    try:
        d_ratio = d.book_debt/(d.book_equity+d.book_debt) if (d.book_equity+d.book_debt)>0 else 0.2
        eq_reinv = (1-d_ratio)*((d.capex-d.depreciation)+d.delta_wc)
        payout_h = a.payout_high if a.payout_high > 0 else max(0.0, min(0.95, 1.0 - eq_reinv/d.net_income)) if d.net_income>0 else 0.5
        payout_s = a.payout_stable if a.payout_stable > 0 else min(0.80, payout_h*1.2)
        net_mg   = a.net_margin if a.net_margin > 0 else d.net_income/d.revenue if d.revenue>0 else 0.10
        eq_m = justified_equity_multiples(
            g_high=g_use, payout_high=payout_h, ke_high=ke_v, n=a.n_high,
            g_stable=a.g_stable, payout_stable=payout_s, ke_stable=ke_v*0.9,
            net_margin=net_mg,
            book_equity_per_share=d.book_equity/d.shares if d.shares>0 else 1,
            eps_next_year=d.eps*(1+g_use) if d.eps else 1,
            revenues_next_year=d.revenue/d.shares*(1+g_use) if d.shares>0 else 0)
        rir_h = max(0.05, (d.capex-d.depreciation+d.delta_wc)/(d.ebit*(1-d.tax_rate))) if d.ebit>0 else 0.4
        fm = justified_firm_multiples(
            g_high=g_use, rir_high=rir_h, wacc_high=wacc_v,
            margin_high=d.ebit*(1-d.tax_rate)/d.revenue if d.revenue>0 else 0.15,
            n=a.n_high, g_stable=a.g_stable, rir_stable=a.g_stable/a.stable_roc,
            wacc_stable=wacc_v*0.95, margin_stable=net_mg, tax_rate=d.tax_rate,
            nopat_next_year=d.ebit*(1-d.tax_rate)*(1+g_use),
            invested_capital=d.book_equity+d.book_debt,
            revenues_next_year=d.revenue*(1+g_use))
    except Exception as e: errors.append(f"Multiples: {e}")

    # Module 05: OCS
    ocs = None
    try:
        if a.run_ocs and d.fcff > 0:
            ocs = optimal_capital_structure(
                ebitda=d.ebitda or d.ebit+d.depreciation, depreciation=d.depreciation, ebit=d.ebit,
                interest_expense=d.interest_expense, tax_rate=d.tax_rate,
                equity_mv=d.equity_market_cap, debt_mv=d.book_debt,
                beta_levered=d.beta_levered, rf=d.rf, erp=a.erp,
                fcff=d.fcff, g_stable=a.g_stable, firm_type=d.firm_type,
                apply_bankruptcy_costs=True,
                shares_outstanding=d.shares, current_price=d.price,
                cash=d.cash, company=d.name)
    except Exception as e: errors.append(f"OCS: {e}")

    # Render
    body = _render_cover(d, coc, g_result, fcff_result, eq_m, fm, a)
    if errors: body += "".join(_warn(f"Module error: {e}") for e in errors)
    if coc:        body += _render_coc(d, coc)
    if g_result:   body += _render_growth(d, g_result, tv_result)
    if fcff_result:body += _render_fcff(d, fcff_result)
    if eq_m or fm: body += _render_multiples(d, eq_m, fm)
    if ocs:        body += _render_ocs(d, ocs)
    if coc:        body += _render_special(d, coc)
    body += _render_audit(d)

    return f'''<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d.ticker} — Damodaran Valuation</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}} body{{background:#0a0f1e;color:#cbd5e1;font-family:'DM Sans',sans-serif;font-size:15px;line-height:1.6;margin:0;padding:0}}
.container{{max-width:1000px;margin:0 auto;padding:48px 32px}} h1,h2,h3{{font-family:'DM Serif Display',serif}}
@media print{{body{{background:white;color:#1a1a1a}}.container{{padding:20px}}}}
</style></head><body><div class="container">
{body}
<div style="margin-top:60px;padding-top:20px;border-top:1px solid #1e293b;font-size:0.75rem;color:#334155;text-align:center">
Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed., Wiley Finance, 2002 · For educational purposes only
</div></div></body></html>'''


if __name__ == "__main__":
    from data_fetcher import _make_placeholder
    d = _make_placeholder("AAPL")
    d.ebitda = d.ebit + d.depreciation
    d.fcff = d.ebit*(1-d.tax_rate) - (d.capex-d.depreciation) - d.delta_wc
    d.historical_eps = [3.5, 4.2, 5.0, 6.1, 7.4]
    html = generate_report(d)
    with open("/tmp/test_report.html","w") as f: f.write(html)
    print(f"OK — {len(html):,} bytes")
    for s in ["Module 01","Module 02","Module 03","Module 04","Module 05","Module 06","Data Audit"]:
        print(f"  {'✓' if s in html else '✗'} {s}")
